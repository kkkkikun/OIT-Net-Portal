"""认证数据模型与异常。加密参数（wlanuserip 等 hex）一律原样透传，不做解读。"""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit


class AuthError(Exception):
    """认证流程错误基类。retryable 标记是否值得退避重试。"""

    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class PortalUnreachable(AuthError):
    """认证服务器不可达（WiFi 掉了 / 服务维护）。"""

    def __init__(self, message: str = "认证服务器不可达"):
        super().__init__(message, retryable=True)


class LoginRejected(AuthError):
    """账号或密码被拒绝。"""

    def __init__(self, message: str = "账号或密码错误"):
        super().__init__(message, retryable=False)


class CaptchaRequired(AuthError):
    """登录需要验证码，无法静默自动登录。"""

    def __init__(self, message: str = "登录页要求验证码，需人工介入"):
        super().__init__(message, retryable=False)


class ProtocolMismatch(AuthError):
    """响应与预期协议不符（协议变更或抓包数据尚未填充）。"""

    def __init__(self, message: str):
        super().__init__(message, retryable=False)


@dataclass(frozen=True)
class PortalChallenge:
    """一次登录挑战：从 AC 302 Location 中解析出的当次参数。"""

    authorize_url: str            # 完整 authorize URL（SSO 入口）
    client_id: str
    eportal_base: str             # 如 http://172.16.11.54
    eportal_querystring: str      # login_sso.jsp 的原始查询串（加密 hex 原样透传）

    @classmethod
    def from_redirect(cls, location: str | None) -> "PortalChallenge":
        if not location:
            raise ProtocolMismatch(
                "探测到劫持但无 302 Location（200 注入式认证页），无法解析 OAuth 挑战"
            )
        parts = urlsplit(location)
        qs = parse_qs(parts.query)
        try:
            client_id = qs["client_id"][0]
            redirect_uri = qs["redirect_uri"][0]
        except KeyError as exc:
            raise ProtocolMismatch(
                f"302 Location 缺少预期参数 {exc}：{location[:200]}"
            ) from exc
        rp = urlsplit(redirect_uri)
        if not rp.netloc:
            raise ProtocolMismatch(f"redirect_uri 无主机名：{redirect_uri[:200]}")
        base = f"{rp.scheme}://{rp.netloc}"
        querystring = rp.query  # 原样保留（含加密参数与 t=wireless-v2）
        return cls(
            authorize_url=location,
            client_id=client_id,
            eportal_base=base,
            eportal_querystring=querystring,
        )

    def eportal_sso_url(self, code: str) -> str:
        """带 code 的 login_sso.jsp 完整 URL（U3 抓包前预设：GET 该地址即完成上线）。"""
        sep = "&" if self.eportal_querystring else ""
        return f"{self.eportal_base}/eportal/login_sso.jsp?code={code}{sep}{self.eportal_querystring}"


@dataclass(frozen=True)
class AuthCode:
    code: str
    obtained_via: str = "password"  # "session_reuse" | "password"


@dataclass
class OnlineResult:
    success: bool
    message: str = ""
    user_index: str | None = None          # <CAPTURE:C-5> 成功页 userIndex
    keepalive_interval: int | None = None  # <CAPTURE:C-5> keepaliveInterval
    mode: str = ""                         # sso_pass | interface_do
    raw: str = field(default="", repr=False)  # 响应体片段（排障用，注意勿含敏感信息）
