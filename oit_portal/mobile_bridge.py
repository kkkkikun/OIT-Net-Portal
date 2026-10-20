"""移动端网络探测桥接。

只向 UI/嵌入层暴露稳定、脱敏的探测和单次登录结果；capture 与守护能力不在这里实现。
"""

from __future__ import annotations

from collections.abc import Iterable

import requests

from .auth.eportal import EportalAdapter
from .auth.flow import AuthFlow, FlowOutcome
from .config import Config
from .log import get_logger
from .mobile_sso import MobileSsoAdapter
from .probe import ProbeStatus, probe as probe_network

logger = get_logger()

_STATUS_HINTS = {
    ProbeStatus.ONLINE: ("ONLINE", "网络已连接"),
    ProbeStatus.CAPTIVE: ("CAPTIVE", "需要完成校园网认证"),
    ProbeStatus.OFFLINE: ("OFFLINE", "当前无可用网络"),
}
_UNKNOWN_RESULT = {"status": "UNKNOWN", "hint": "网络状态暂时不可用"}
_CLOSED_RESULT = {"status": "UNKNOWN", "hint": "探测桥接已关闭"}
_LOGIN_HINTS = {
    FlowOutcome.ALREADY_ONLINE: ("ALREADY_ONLINE", "网络已在线"),
    FlowOutcome.LOGGED_IN: ("LOGGED_IN", "登录成功"),
    FlowOutcome.NO_NETWORK: ("NO_NETWORK", "当前无可用网络"),
    FlowOutcome.NEED_CREDENTIALS: ("NEED_CREDENTIALS", "需要更新账号或密码"),
    FlowOutcome.CAPTCHA_REQUIRED: ("CAPTCHA_REQUIRED", "需要人工完成验证码"),
    FlowOutcome.LOGIN_REJECTED: ("LOGIN_REJECTED", "账号或密码被拒绝"),
    FlowOutcome.FAILED: ("FAILED", "登录失败，请稍后重试"),
}
_LOGIN_FAILED_RESULT = {"outcome": "FAILED", "hint": "登录失败，请稍后重试"}
_LOGIN_CLOSED_RESULT = {"outcome": "FAILED", "hint": "桥接已关闭，未执行登录"}


class MobileProbeBridge:
    """可注入 Session 的非交互式探测接口。

    外部传入的 Session 由调用方管理；桥接自行创建的 Session 会禁用环境代理，
    并由 close() 负责释放。
    """

    def __init__(self, cfg: Config, session: requests.Session | None = None):
        self._cfg = cfg
        self._owns_session = session is None
        self._session = requests.Session() if session is None else session
        self._closed = False
        if self._owns_session:
            self._session.headers["User-Agent"] = cfg.advanced.user_agent
            self._session.trust_env = False

    def probe(self) -> dict[str, str]:
        """执行一次探测。返回值永不包含 URL、页面内容、凭据或原始异常。"""
        if self._closed:
            return dict(_CLOSED_RESULT)
        try:
            result = probe_network(self._session, self._cfg)
        except Exception:  # noqa: BLE001 - 桥接边界统一脱敏，不泄露底层细节
            logger.warning("移动端探测桥接异常，已返回 UNKNOWN")
            return dict(_UNKNOWN_RESULT)
        status, hint = _STATUS_HINTS.get(result.status, ("UNKNOWN", "网络状态暂时不可用"))
        return {"status": status, "hint": hint}

    def login_once(self, *, allow_password: bool = True) -> dict[str, str]:
        """显式执行一次认证流程，不启用会话落盘或后台循环。"""
        if self._closed:
            return dict(_LOGIN_CLOSED_RESULT)
        try:
            flow = AuthFlow(
                self._session,
                self._cfg,
                sso=MobileSsoAdapter(self._session, self._cfg),
                eportal=EportalAdapter(self._session, self._cfg,
                                       apply_protocol_overrides=False),
                session_path=None,
            )
            result = flow.ensure_online(allow_password=allow_password)
        except Exception as exc:  # noqa: BLE001 - 桥接边界统一脱敏，不泄露底层细节
            logger.warning("移动端登录桥接异常（%s），已返回 FAILED", type(exc).__name__)
            return dict(_LOGIN_FAILED_RESULT)
        outcome, hint = _LOGIN_HINTS.get(
            getattr(result, "outcome", None),
            ("FAILED", "登录失败，请稍后重试"),
        )
        return {"outcome": outcome, "hint": hint}

    def close(self) -> None:
        """关闭自有 Session；多次调用安全，外部注入的 Session 不会被关闭。"""
        if self._closed:
            return
        self._closed = True
        if not self._owns_session:
            return
        try:
            self._session.close()
        except Exception:  # noqa: BLE001 - 关闭失败不影响调用方生命周期
            logger.warning("移动端探测 Session 关闭异常")

    def __enter__(self) -> "MobileProbeBridge":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()


def probe_status(cfg: Config, session: requests.Session | None = None) -> dict[str, str]:
    """一次性探测便捷接口；注入的 Session 仍由调用方负责关闭。"""
    with MobileProbeBridge(cfg, session=session) as bridge:
        return bridge.probe()


def create_mobile_bridge(username: str, password: str, *,
                         probe_urls: Iterable[str] | None = None,
                         session: requests.Session | None = None) -> MobileProbeBridge:
    """用基础参数创建内存配置的移动桥接，不读取外部配置文件或环境变量。"""
    cfg = Config(username=_require_credential(username),
                 password=_require_credential(password))
    urls = _copy_probe_urls(probe_urls)
    if urls is not None:
        cfg.probe.urls = urls
    return MobileProbeBridge(cfg, session=session)


def _require_credential(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("账号或密码参数无效")
    return value


def _copy_probe_urls(probe_urls: Iterable[str] | None) -> list[str] | None:
    if probe_urls is None:
        return None
    if isinstance(probe_urls, (str, bytes)):
        raise ValueError("探测地址参数无效")
    try:
        urls = list(probe_urls)
    except TypeError as exc:
        raise ValueError("探测地址参数无效") from exc
    if not urls:
        raise ValueError("探测地址参数无效")
    cleaned = []
    for url in urls:
        if not isinstance(url, str) or not url.strip():
            raise ValueError("探测地址参数无效")
        cleaned.append(url.strip())
    return cleaned


__all__ = ["MobileProbeBridge", "create_mobile_bridge", "probe_status"]
