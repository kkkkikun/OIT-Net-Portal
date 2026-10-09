"""认证状态机编排（协议无关）。

flow 对 adapter 的调用顺序、失败处理、重试决策在此写死；
协议细节全部下沉到 sso.py / eportal.py 的 CAPTURED 常量块。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from ..config import Config
from ..log import fingerprint, get_logger
from ..probe import ProbeResult, ProbeStatus, probe
from . import session_store
from .eportal import EportalAdapter
from .models import (AuthCode, CaptchaRequired, LoginRejected, PortalChallenge,
                     ProtocolMismatch)
from .sso import SsoAdapter

logger = get_logger()


class FlowOutcome(enum.Enum):
    ALREADY_ONLINE = "already_online"   # 本来就在线
    LOGGED_IN = "logged_in"             # 本次成功上线
    NO_NETWORK = "no_network"           # 无网络，只探测不登录
    NEED_CREDENTIALS = "need_credentials"  # 会话失效且无账密可用
    CAPTCHA_REQUIRED = "captcha_required"  # 需要验证码，转人工
    LOGIN_REJECTED = "login_rejected"   # 账密被拒
    FAILED = "failed"                   # 其他失败（协议/网络/上线未确认）


@dataclass
class FlowResult:
    outcome: FlowOutcome
    detail: str = ""
    via: str = ""           # session_reuse | password
    user_index: str | None = None
    keepalive_interval: int | None = None


class AuthFlow:
    def __init__(self, session: requests.Session, cfg: Config,
                 sso: SsoAdapter | None = None,
                 eportal: EportalAdapter | None = None,
                 prober: Callable[[], ProbeResult] | None = None,
                 session_path: Path | None = None):
        self.session = session
        self.cfg = cfg
        self.sso = sso or SsoAdapter(session, cfg)
        self.eportal = eportal or EportalAdapter(session, cfg)
        self._prober = prober or (lambda: probe(session, cfg))
        self._session_path = session_path

    # ── 主入口 ───────────────────────────────────────────────

    def ensure_online(self, *, allow_password: bool = True) -> FlowResult:
        pr = self._prober()
        if pr.status is ProbeStatus.ONLINE:
            return FlowResult(FlowOutcome.ALREADY_ONLINE, detail=str(pr))
        if pr.status is ProbeStatus.OFFLINE:
            return FlowResult(FlowOutcome.NO_NETWORK, detail=str(pr))

        # CAPTIVE：进入登录流程
        if pr.redirect_url:
            try:
                challenge = PortalChallenge.from_redirect(pr.redirect_url)
            except ProtocolMismatch as exc:
                return FlowResult(FlowOutcome.FAILED, detail=str(exc))
        else:
            # 注入式劫持：穿过注入页/JS 跳转链寻找 OAuth 授权入口
            from ..discover import follow_entry
            try:
                entry = follow_entry(self.session, self.cfg, [],
                                     page_url=pr.probe_url, page_body=pr.body)
                challenge = entry.challenge
            except Exception:  # noqa: BLE001 - 发现失败按无挑战处理
                challenge = None
            if challenge is None:
                return FlowResult(
                    FlowOutcome.FAILED,
                    detail="注入式认证页链路中未找到 OAuth 授权入口，"
                           "请运行 oit-portal capture 完成协议适配")

        logger.info("捕获登录挑战 client_id=%s… eportal=%s",
                    challenge.client_id[:8], challenge.eportal_base)

        auth = self._obtain_code(challenge, allow_password=allow_password)
        if isinstance(auth, FlowResult):  # 失败分支的哨兵返回
            return auth

        try:
            result = self.eportal.online(auth, challenge)
        except Exception as exc:  # noqa: BLE001 - PortalUnreachable/ProtocolMismatch 统一兜底
            return self._persist_session(FlowResult(FlowOutcome.FAILED,
                                                    detail=f"ePortal 上线异常: {exc}"))

        if not result.success:
            return self._persist_session(FlowResult(
                FlowOutcome.FAILED, detail=f"ePortal 未确认上线：{result.message}",
                user_index=result.user_index,
                keepalive_interval=result.keepalive_interval))

        # 二次探测确认（防「响应成功但仍被劫持」）
        verify = self._prober()
        outcome = (FlowOutcome.LOGGED_IN if verify.status is ProbeStatus.ONLINE
                   else FlowOutcome.FAILED)
        detail = f"via={auth.obtained_via}" if outcome is FlowOutcome.LOGGED_IN \
            else f"上线后复测未通过（{verify}）"
        fr = FlowResult(outcome, detail=detail, via=auth.obtained_via,
                        user_index=result.user_index,
                        keepalive_interval=result.keepalive_interval)
        return self._persist_session(fr)

    # ── 内部步骤 ─────────────────────────────────────────────

    def _obtain_code(self, challenge: PortalChallenge,
                     *, allow_password: bool) -> AuthCode | FlowResult:
        """策略 A 会话复用 → 策略 B 账密。返回 AuthCode 或失败哨兵 FlowResult。"""
        try:
            auth = self.sso.try_session(challenge)
        except Exception as exc:  # noqa: BLE001
            return FlowResult(FlowOutcome.FAILED, detail=f"SSO 会话探测异常: {exc}")
        if auth is not None:
            return auth

        if not allow_password:
            return FlowResult(FlowOutcome.NEED_CREDENTIALS,
                              detail="会话失效且本次不允许账密登录")
        if not self.cfg.username or not self.cfg.password:
            logger.warning("缺少账密（username=%s, password=%s）",
                           self.cfg.username, fingerprint(self.cfg.password))
            return FlowResult(FlowOutcome.NEED_CREDENTIALS,
                              detail="会话失效且未配置账号/密码")
        try:
            return self.sso.login_password(challenge, self.cfg.username,
                                           self.cfg.password)
        except Exception as exc:  # noqa: BLE001
            if isinstance(exc, CaptchaRequired):
                return FlowResult(FlowOutcome.CAPTCHA_REQUIRED, detail=str(exc))
            if isinstance(exc, LoginRejected):
                return FlowResult(FlowOutcome.LOGIN_REJECTED, detail=str(exc))
            return FlowResult(FlowOutcome.FAILED, detail=f"SSO 登录异常: {exc}")

    def _persist_session(self, result: FlowResult) -> FlowResult:
        """登录成功才持久化 cookie；失败清空（避免坏会话反复复用）。"""
        if self._session_path is None:
            return result
        if result.outcome in (FlowOutcome.LOGGED_IN, FlowOutcome.ALREADY_ONLINE):
            session_store.save(self.session, self._session_path)
        elif result.outcome in (FlowOutcome.LOGIN_REJECTED, FlowOutcome.CAPTCHA_REQUIRED,
                                FlowOutcome.NEED_CREDENTIALS):
            session_store.clear(self._session_path)
        return result
