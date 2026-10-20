"""移动端首装场景的 SSO HTML 表单适配器。

仅在用户显式提交凭据后解析当前登录页；不读取 protocol.json，不写协议配置，
也不向多个候选端点试发凭据。
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import requests

from . import htmlutil
from .auth.models import (AuthCode, CaptchaRequired, LoginRejected,
                          PortalChallenge, PortalUnreachable, ProtocolMismatch)
from .auth.sso import _REDIRECT_CODES, SsoAdapter, _aes_encrypt
from .config import Config
from .log import get_logger

logger = get_logger()

_MAX_FORM_BYTES = 65536
_REJECT_MARKERS = ("密码错误", "账号或密码", "incorrect", "failed")
_USERNAME_HINTS = ("user", "account", "username", "xh", "stu", "login")
_ALLOWED_SCHEMES = {"http", "https"}


@dataclass(frozen=True)
class _MobileForm:
    endpoint: str
    username_field: str
    password_field: str
    hidden_fields: dict[str, str]


class MobileSsoAdapter(SsoAdapter):
    """从当次 HTML 表单发现提交目标的移动端适配器。"""

    def __init__(self, session: requests.Session, cfg: Config):
        super().__init__(session, cfg, apply_protocol_overrides=False)

    def login_password(self, challenge: PortalChallenge,
                       username: str, password: str) -> AuthCode:
        resp, code_location = self._follow(challenge.authorize_url)
        if code_location:
            return AuthCode(code=self._extract_code(code_location),
                            obtained_via="session_reuse")

        page_url = resp.url or challenge.authorize_url
        html = resp.text[:_MAX_FORM_BYTES]
        parsed_form = _parse_form(html, page_url, challenge.authorize_url)
        form = dict(parsed_form.hidden_fields)
        form[parsed_form.username_field] = username
        form[parsed_form.password_field] = _transform_password(password, html)

        logger.info("提交移动端 SSO 表单登录（目标与 authorize 同源）")
        try:
            post = self.session.post(parsed_form.endpoint, data=form,
                                     allow_redirects=False,
                                     timeout=self.cfg.advanced.timeout_sec)
        except requests.RequestException as exc:
            raise PortalUnreachable(f"登录请求失败: {type(exc).__name__}") from exc

        final = post
        code_location = None
        if post.status_code in _REDIRECT_CODES:
            location = post.headers.get("Location", "")
            if not location:
                raise ProtocolMismatch("登录响应 30x 但无 Location")
            final, code_location = self._follow(self._absolutize(page_url, location))
        body = final.text[:4096]
        for marker in _REJECT_MARKERS:
            if marker in body:
                raise LoginRejected("SSO 拒绝登录")
        if code_location:
            return AuthCode(code=self._extract_code(code_location),
                            obtained_via="password")
        return AuthCode(code="", obtained_via="password")


def _parse_form(html: str, page_url: str, authorize_url: str) -> _MobileForm:
    if htmlutil.looks_like_captcha(html)[0]:
        raise CaptchaRequired()
    tags = list(htmlutil.FORM_RE.finditer(html))
    if len(tags) != 1:
        raise ProtocolMismatch("移动端仅支持唯一且明确的 HTML 登录表单")
    method = (htmlutil.attr(tags[0].group(0), "method") or "GET").lower()
    if method != "post":
        raise ProtocolMismatch("登录表单不是 POST 方法")

    action = htmlutil.form_action(html)
    if action is None:
        raise ProtocolMismatch("页面没有可提交的 HTML 登录表单")
    endpoint = page_url if action == "" else urljoin(page_url, action)
    _require_same_origin(endpoint, authorize_url)

    inputs = htmlutil.inputs(html)
    username_field = _username_field(inputs)
    password_field = _password_field(inputs)
    if not username_field or not password_field:
        raise ProtocolMismatch("登录表单缺少明确的账号或密码字段")

    hidden_fields = {}
    for name, value, itype in inputs:
        if itype == "hidden" and name not in (username_field, password_field):
            hidden_fields[name] = value
    return _MobileForm(endpoint=endpoint, username_field=username_field,
                       password_field=password_field, hidden_fields=hidden_fields)


def _username_field(inputs: list[tuple[str, str, str]]) -> str | None:
    excluded = {"hidden", "submit", "button", "checkbox", "radio"}
    visible = [name for name, _value, itype in inputs
               if itype not in excluded and not htmlutil.CAPTCHA_NAME_RE.search(name)]
    hinted = [name for name in visible
              if any(hint in name.lower() for hint in _USERNAME_HINTS)]
    if hinted:
        return hinted[0]
    if len(visible) == 1:
        return visible[0]
    for name, _value, itype in inputs:
        if any(hint in name.lower() for hint in _USERNAME_HINTS):
            return name
    return None


def _password_field(inputs: list[tuple[str, str, str]]) -> str | None:
    for name, _value, itype in inputs:
        if itype == "password":
            return name
    for name, _value, itype in inputs:
        low = name.lower()
        if itype == "hidden" and (low == "password" or low.endswith("password")
                                  or low == "pwd"):
            return name
    return None


def _transform_password(password: str, html: str) -> str:
    aes = htmlutil.find_aes(html)
    if aes:
        mode = "aes_ecb" if aes.get("mode") == "ECB" else "aes_cbc"
        return _aes_encrypt(password, aes["key"], aes["iv"], mode,
                            aes.get("padding", "zero"))
    if htmlutil.has_aes_hint(html) or htmlutil.has_rsa_hint(html):
        raise ProtocolMismatch("检测到密码前端加密，但当次参数无法安全解析")
    return password


def _require_same_origin(endpoint: str, authorize_url: str) -> None:
    if _origin(endpoint) != _origin(authorize_url):
        raise ProtocolMismatch("登录表单提交目标与 authorize 来源不一致")


def _origin(url: str) -> tuple[str, str, int]:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ProtocolMismatch("登录表单地址无法安全解析") from exc
    scheme = parts.scheme.lower()
    if scheme not in _ALLOWED_SCHEMES or not parts.hostname:
        raise ProtocolMismatch("登录表单地址不是可信 HTTP 来源")
    return scheme, parts.hostname.lower(), port or (443 if scheme == "https" else 80)
