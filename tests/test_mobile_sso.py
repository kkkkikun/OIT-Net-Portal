"""移动端首次 SSO 表单登录的离线运行测试。"""

import pytest

from oit_portal.auth import eportal as eportal_mod
from oit_portal.auth import sso as sso_mod
from oit_portal.auth.eportal import EportalAdapter
from oit_portal.auth.models import PortalChallenge
from oit_portal.auth.sso import SsoAdapter, _aes_encrypt
from oit_portal.mobile_bridge import MobileProbeBridge
from oit_portal.mobile_sso import MobileSsoAdapter

from conftest import (AUTHORIZE_URL, EPORTAL_CODE_URL, FakeResponse,
                      FakeSession, make_config)


MIUI = "http://connect.rom.miui.com/generate_204"
APPLE = "http://captive.apple.com/hotspot-detect.html"
AES_SOURCE = "aaaabbbbccccddddaaaabbbbccccdddd"
AES_KEY = "aaaabbbbccccdddd"


def _cfg():
    cfg = make_config()
    cfg.probe.urls = [MIUI, APPLE]
    return cfg


def _form_html(*, action=None, method="POST", aes=True, captcha=False,
               username=True, script=None):
    action_attr = f' action="{action}"' if action is not None else ""
    if script is None:
        script = ""
        if aes:
            script = (
                "<script>"
                "key=CryptoJS.enc.Utf8.parse('" + AES_SOURCE + "'.substr(0,16));"
                "iv=CryptoJS.enc.Utf8.parse('" + AES_SOURCE + "'.substr(0,16));"
                "CryptoJS.AES.encrypt(str,key,{iv:iv,mode:CryptoJS.mode.CBC,"
                "padding:CryptoJS.pad.ZeroPadding});"
                "</script>"
            )
    username_input = '<input name="username" type="text">' if username else ""
    captcha_input = '<input name="captcha" type="text">' if captcha else ""
    return (
        script
        + f'<form method="{method}"{action_attr}>'
        + '<input type="hidden" name="fingerprint" value="">'
        + '<input type="hidden" name="_endpoint" value="http://untrusted.example/steal">'
        + f'<input type="hidden" name="__token__" value="{AES_SOURCE}">'
        + username_input
        + '<input name="password" type="hidden" value="">'
        + captcha_input
        + "</form>"
    )


def _aes_script(options: str, *, key_source=AES_SOURCE, iv_source=AES_SOURCE) -> str:
    return (
        "<script>"
        "key=CryptoJS.enc.Utf8.parse('" + key_source + "'.substr(0,16));"
        "iv=CryptoJS.enc.Utf8.parse('" + iv_source + "'.substr(0,16));"
        "CryptoJS.AES.encrypt(str,key,{" + options + "});"
        "</script>"
    )


def _session_for_form(html: str, *, post_url=AUTHORIZE_URL):
    session = FakeSession()
    session.add_url(
        MIUI,
        FakeResponse(302, headers={"Location": AUTHORIZE_URL}),
        FakeResponse(204),
    )
    session.add_url(APPLE, FakeResponse(204))
    session.add(lambda url, method: method == "POST" and url == post_url,
                FakeResponse(302, headers={"Location": AUTHORIZE_URL}))
    session.add(lambda url, method: method == "GET" and url == AUTHORIZE_URL,
                FakeResponse(200, text=html, url=AUTHORIZE_URL),
                FakeResponse(200, text=html, url=AUTHORIZE_URL),
                FakeResponse(302, headers={"Location": EPORTAL_CODE_URL}))
    session.add_url(EPORTAL_CODE_URL, FakeResponse(200, text="认证成功"))
    return session


def _block_overrides(monkeypatch):
    calls = []

    def record(namespace, section, *args, **kwargs):
        calls.append(section)
        raise AssertionError("移动端不应读取协议覆盖")

    monkeypatch.setattr(sso_mod, "apply_overrides", record)
    monkeypatch.setattr(eportal_mod, "apply_overrides", record)
    return calls


def test_mobile_adapter_direct_actionless_form_posts_dynamic_aes():
    session = _session_for_form(_form_html())
    adapter = MobileSsoAdapter(session, _cfg())

    challenge = PortalChallenge.from_redirect(AUTHORIZE_URL)
    assert adapter.try_session(challenge) is None
    auth = adapter.login_password(challenge, "20230001", "secret-pass")

    assert auth.code == "CODE123", session.calls
    post_url, payload = session.posts[0]
    assert post_url == AUTHORIZE_URL
    assert payload["password"] == _aes_encrypt(
        "secret-pass", AES_KEY, AES_KEY, "aes_cbc", "zero")


def test_mobile_actionless_form_posts_full_authorize_url_with_dynamic_aes(monkeypatch):
    override_calls = _block_overrides(monkeypatch)
    session = _session_for_form(_form_html())

    result = MobileProbeBridge(_cfg(), session=session).login_once()

    assert result == {"outcome": "LOGGED_IN", "hint": "登录成功"}
    assert override_calls == []
    post_url, payload = session.posts[0]
    assert post_url == AUTHORIZE_URL
    assert payload["username"] == "20230001"
    assert payload["password"] == _aes_encrypt(
        "secret-pass", AES_KEY, AES_KEY, "aes_cbc", "zero")
    assert payload["__token__"] == AES_SOURCE
    assert payload["fingerprint"] == ""
    assert "password_" not in payload


def test_mobile_relative_action_uses_standard_url_resolution(monkeypatch):
    _block_overrides(monkeypatch)
    action = "/mobile/login?from=form"
    expected = "http://open.oit.edu.cn:8090/mobile/login?from=form"
    session = _session_for_form(_form_html(action=action), post_url=expected)

    result = MobileProbeBridge(_cfg(), session=session).login_once()

    assert result["outcome"] == "LOGGED_IN"
    assert session.posts[0][0] == expected


def test_mobile_explicit_ecb_zero_padding_still_uses_encryption(monkeypatch):
    _block_overrides(monkeypatch)
    script = _aes_script("mode:CryptoJS.mode.ECB,padding:CryptoJS.pad.ZeroPadding")
    session = _session_for_form(_form_html(script=script))

    result = MobileProbeBridge(_cfg(), session=session).login_once()

    assert result["outcome"] == "LOGGED_IN"
    payload = session.posts[0][1]
    assert payload["password"] == _aes_encrypt(
        "secret-pass", AES_KEY, AES_KEY, "aes_ecb", "zero")


@pytest.mark.parametrize(
    "html",
    [
        _form_html(action="http://untrusted.example/login"),
        _form_html(method="GET"),
        _form_html(username=False),
        "<script>CryptoJS.AES.encrypt(str,key)</script>" + _form_html(aes=False),
        "<div id='app'>CryptoJS.AES.encrypt</div>",
    ],
)
def test_mobile_form_fail_closed_paths_do_not_send_password(monkeypatch, html):
    _block_overrides(monkeypatch)
    session = _session_for_form(html)

    result = MobileProbeBridge(_cfg(), session=session).login_once()

    assert result["outcome"] == "FAILED"
    assert session.posts == []


def test_mobile_captcha_form_does_not_send_password(monkeypatch):
    _block_overrides(monkeypatch)
    session = _session_for_form(_form_html(captcha=True))

    result = MobileProbeBridge(_cfg(), session=session).login_once()

    assert result["outcome"] == "CAPTCHA_REQUIRED"
    assert session.posts == []


@pytest.mark.parametrize(
    "html",
    [
        _form_html(aes=False),
        _form_html(aes=False,
                   script='<script src="/static/auth/login.js"></script>'),
        _form_html(script=_aes_script(
            "iv:iv,padding:CryptoJS.pad.ZeroPadding")),
        _form_html(script=_aes_script(
            "iv:iv,mode:CryptoJS.mode.CBC")),
        _form_html(script=_aes_script(
            "mode:CryptoJS.mode.CBC,padding:CryptoJS.pad.ZeroPadding")),
        _form_html(script=_aes_script(
            "iv:iv,mode:CryptoJS.mode.CFB,padding:CryptoJS.pad.ZeroPadding")),
        _form_html(script=_aes_script(
            "iv:iv,mode:CryptoJS.mode.CBC,padding:CryptoJS.pad.Pkcs5")),
        _form_html(script=_aes_script(
            "iv:iv,mode:CryptoJS.mode.CBC,padding:CryptoJS.pad.ZeroPadding",
            key_source="short")),
        _form_html(script=_aes_script(
            "iv:iv,mode:CryptoJS.mode.CBC,padding:CryptoJS.pad.ZeroPadding",
            iv_source="short-iv")),
    ],
)
def test_mobile_uncertain_encryption_never_posts_password(monkeypatch, html):
    _block_overrides(monkeypatch)
    session = _session_for_form(html)

    result = MobileProbeBridge(_cfg(), session=session).login_once()

    assert result["outcome"] == "FAILED"
    assert session.posts == []


def test_default_adapters_still_apply_protocol_overrides(monkeypatch):
    calls = []

    def record(namespace, section, *args, **kwargs):
        calls.append(section)
        return []

    monkeypatch.setattr(sso_mod, "apply_overrides", record)
    monkeypatch.setattr(eportal_mod, "apply_overrides", record)

    SsoAdapter(FakeSession(), _cfg())
    EportalAdapter(FakeSession(), _cfg())

    assert calls == ["sso", "eportal"]
