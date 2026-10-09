"""SSO 适配器（open.oit.edu.cn:8090 OAuth2 统一认证）。

═══════════════════════════════════════════════════════════════════
★ <CAPTURE> 隔离区：阶段 0 抓包后只改下方 CAPTURED 常量块 ★
  对应 docs/protocol-notes.md 的 C2 小节，逐项填好后本文件无需再动。
═══════════════════════════════════════════════════════════════════
两种策略：
  A 会话复用（try_session）：带持久化 cookie GET authorize，
    若 SSO 会话有效则直接 302 携带 code，全程零密码；
  B 账密登录（login_password）：提交表单换取 code。
"""

from __future__ import annotations

import base64
import binascii
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import requests

from ..config import Config
from ..log import get_logger
from .models import (AuthCode, AuthError, CaptchaRequired, LoginRejected,
                     PortalChallenge, PortalUnreachable, ProtocolMismatch)

logger = get_logger()

CAPTURED = SimpleNamespace(
    # ── C2.1 登录表单提交端点（相对或绝对 URL；抓包后填，如 "/auth/user/login"）──
    login_endpoint="<CAPTURE:C2.1>",
    # ── C2.2/C2.4 字段名与隐藏字段 ──
    username_field="username",
    password_field="password",
    extra_fields={},               # 表单 hidden 字段，如 {"lt": "...", "execution": "e1s1"}
    # ── C2.6 密码前端加密："none" | "rsa" ──
    password_encrypt="none",
    rsa_public_key="<CAPTURE:C2.6>",   # password_encrypt=rsa 时必填（PEM 或 base64 DER）
    # ── C2.5 验证码 ──
    has_captcha=False,
    # 登录表单页的 HTML 特征（用于区分「需要账密」和「直接发 code」）
    form_marker="password",
    # 登录失败响应特征（C2.7）：命中即判定账密被拒
    reject_markers=["密码错误", "账号或密码", "incorrect", "failed"],
)

_MAX_HOPS = 8
_REDIRECT_CODES = (301, 302, 303, 307, 308)


def _is_captured(value: str) -> bool:
    return "<CAPTURE" in value


class SsoAdapter:
    def __init__(self, session: requests.Session, cfg: Config):
        self.session = session
        self.cfg = cfg
        self.base = f"http://{cfg.advanced.eportal_host}"  # 仅占位，真正 base 来自 challenge

    # ── 内部工具 ──────────────────────────────────────────────

    def _get(self, url: str, **kwargs) -> requests.Response:
        try:
            return self.session.get(url, allow_redirects=False,
                                    timeout=self.cfg.advanced.timeout_sec, **kwargs)
        except requests.RequestException as exc:
            raise PortalUnreachable(f"请求失败 {url[:120]}: {type(exc).__name__}") from exc

    def _follow(self, url: str) -> tuple[requests.Response, str | None]:
        """手动跟随 30x，直到：拿到带 code 的跳转 / 返回 200 / 跳数耗尽。

        返回 (最终响应, 携带 code 的 Location 或 None)。
        """
        current = url
        for _ in range(_MAX_HOPS):
            resp = self._get(current)
            if resp.status_code in _REDIRECT_CODES:
                location = resp.headers.get("Location", "")
                if not location:
                    break
                if self._extract_code(location) is not None:
                    return resp, location
                current = self._absolutize(current, location)
                continue
            break
        return resp, None

    @staticmethod
    def _absolutize(base: str, location: str) -> str:
        if urlsplit(location).netloc:
            return location
        parts = urlsplit(base)
        return f"{parts.scheme}://{parts.netloc}{location}"

    @staticmethod
    def _extract_code(url: str) -> str | None:
        qs = parse_qs(urlsplit(url).query)
        for key in ("code",):
            if key in qs and qs[key][0]:
                return qs[key][0]
        return None

    def _looks_like_form(self, resp: requests.Response) -> bool:
        head = resp.text[:8192]
        if CAPTURED.form_marker and CAPTURED.form_marker in head:
            return True
        return "<form" in head.lower()

    def _transform_password(self, raw: str) -> str:
        if CAPTURED.password_encrypt == "none":
            return raw
        if CAPTURED.password_encrypt == "rsa":
            if _is_captured(CAPTURED.rsa_public_key):
                raise ProtocolMismatch("rsa_public_key 尚未填充（protocol-notes C2.6）")
            return _rsa_encrypt(raw, CAPTURED.rsa_public_key)
        raise ProtocolMismatch(f"未知加密方式 {CAPTURED.password_encrypt}")

    # ── 策略 A：会话复用 ─────────────────────────────────────

    def try_session(self, challenge: PortalChallenge) -> AuthCode | None:
        """SSO cookie 有效则免密拿 code；需要表单则返回 None。"""
        resp, code_location = self._follow(challenge.authorize_url)
        if code_location:
            code = self._extract_code(code_location)
            logger.info("SSO 会话复用成功，免密获得 code")
            return AuthCode(code=code, obtained_via="session_reuse")
        if self._looks_like_form(resp):
            logger.info("SSO 会话无效或不存在，需要账密登录")
            return None
        raise ProtocolMismatch(
            f"authorize 响应异常：HTTP {resp.status_code}，既非 code 跳转也非登录表单"
        )

    # ── 策略 B：账密登录 ─────────────────────────────────────

    def login_password(self, challenge: PortalChallenge,
                       username: str, password: str) -> AuthCode:
        if _is_captured(CAPTURED.login_endpoint):
            raise ProtocolMismatch(
                "SSO 登录端点尚未填充（protocol-notes C2.1）——"
                "请先完成 docs/capture-guide.md 阶段 0 抓包"
            )
        if CAPTURED.has_captcha:
            raise CaptchaRequired()

        # 1) 先 GET authorize 走到登录表单页（拿表单 cookie / hidden 字段上下文）
        resp, code_location = self._follow(challenge.authorize_url)
        if code_location:  # 万一表单页阶段就免密通过了
            return AuthCode(code=self._extract_code(code_location),
                            obtained_via="session_reuse")

        # 2) POST 账密（端点为相对路径时基于表单页 URL 解析）
        endpoint = CAPTURED.login_endpoint
        if not urlsplit(endpoint).netloc:
            endpoint = self._absolutize(resp.url or challenge.authorize_url, endpoint)
        form = {
            CAPTURED.username_field: username,
            CAPTURED.password_field: self._transform_password(password),
            **dict(CAPTURED.extra_fields),
        }
        logger.info("提交 SSO 账密登录（密码加密=%s）", CAPTURED.password_encrypt)
        try:
            post = self.session.post(endpoint, data=form, allow_redirects=False,
                                     timeout=self.cfg.advanced.timeout_sec)
        except requests.RequestException as exc:
            raise PortalUnreachable(f"登录请求失败: {type(exc).__name__}") from exc

        # 3) 结果判定：302 链出 code = 成功；200 + 拒绝特征 = 账密错误
        if post.status_code in _REDIRECT_CODES:
            location = post.headers.get("Location", "")
            if not location:
                raise ProtocolMismatch("登录响应 30x 但无 Location")
            _, code_location = self._follow(self._absolutize(endpoint, location))
            if code_location:
                logger.info("账密登录成功，获得 code")
                return AuthCode(code=self._extract_code(code_location),
                                obtained_via="password")
            raise ProtocolMismatch("登录后跳转链中未发现 code 参数")
        body = post.text[:4096]
        for marker in CAPTURED.reject_markers:
            if marker in body:
                raise LoginRejected(f"SSO 拒绝登录（命中标记「{marker}」）")
        raise ProtocolMismatch(
            f"登录响应异常：HTTP {post.status_code}，无拒绝标记也无 code 跳转"
        )


def _rsa_encrypt(raw: str, public_key: str) -> str:
    """RSA 加密（PKCS1_v1_5，与常见 jsencrypt 前端一致），输出 base64。"""
    try:
        from Crypto.Cipher import PKCS1_v1_5
        from Crypto.PublicKey import RSA
    except ImportError as exc:
        raise ProtocolMismatch(
            "需要 pycryptodome 才能复现 RSA 密码加密：pip install pycryptodome"
        ) from exc
    key = RSA.import_key(public_key)
    cipher = PKCS1_v1_5.new(key)
    try:
        encrypted = cipher.encrypt(raw.encode("utf-8"))
        return base64.b64encode(encrypted).decode("ascii")
    except (ValueError, binascii.Error) as exc:
        raise ProtocolMismatch(f"RSA 加密失败（公钥格式?）: {exc}") from exc
