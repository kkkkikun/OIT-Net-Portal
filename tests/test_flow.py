"""认证状态机：会话复用/账密/验证码/被拒/上线未确认 全分支回放。"""

import pytest

from oit_portal.auth import sso as sso_mod
from oit_portal.auth.eportal import EportalAdapter
from oit_portal.auth.flow import AuthFlow, FlowOutcome
from oit_portal.auth.sso import SsoAdapter
from oit_portal.probe import ProbeResult, ProbeStatus

from conftest import (AUTHORIZE_URL, EPORTAL_CODE_URL, FakeResponse,
                      FakeSession, make_config)

SUCCESS_PAGE = (
    "<html><body>认证成功！<script>var userIndex='aabb0011';"
    "var keepaliveInterval=0;</script></body></html>"
)


def _captured_defaults(monkeypatch, *, login_endpoint="/auth/user/login",
                       has_captcha=False):
    """每个用例独立设定 CAPTURED（避免用例间串扰）。"""
    monkeypatch.setattr(sso_mod.CAPTURED, "login_endpoint", login_endpoint)
    monkeypatch.setattr(sso_mod.CAPTURED, "has_captcha", has_captcha)
    monkeypatch.setattr(sso_mod.CAPTURED, "password_encrypt", "none")


def _flow(session, cfg, prober):
    return AuthFlow(session, cfg, sso=SsoAdapter(session, cfg),
                    eportal=EportalAdapter(session, cfg), prober=prober)


def test_already_online(cfg):
    flow = _flow(FakeSession(), cfg, lambda: ProbeResult(ProbeStatus.ONLINE))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.ALREADY_ONLINE


def test_no_network(cfg):
    flow = _flow(FakeSession(), cfg, lambda: ProbeResult(ProbeStatus.OFFLINE))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.NO_NETWORK


def test_session_reuse_full_path(cfg, fake_session, monkeypatch):
    """会话复用：authorize 直接 302 发 code → ePortal 上线 → 复测在线。"""
    _captured_defaults(monkeypatch)
    states = iter([
        ProbeResult(ProbeStatus.CAPTIVE, redirect_url=AUTHORIZE_URL),  # 初始探测
        ProbeResult(ProbeStatus.ONLINE),                              # 上线后确认
    ])
    fake_session.add_url(AUTHORIZE_URL, FakeResponse(
        302, headers={"Location": EPORTAL_CODE_URL}))
    fake_session.add_url(EPORTAL_CODE_URL, FakeResponse(200, text=SUCCESS_PAGE))

    flow = _flow(fake_session, cfg, lambda: next(states))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.LOGGED_IN
    assert result.via == "session_reuse"
    assert result.user_index == "aabb0011"
    # 全程无 POST（零密码）
    assert all(m == "GET" for m, _ in fake_session.calls)


def test_password_login_path(cfg, fake_session, monkeypatch):
    """账密路径：authorize 落表单 → POST 登录 → 302 链出 code → ePortal 上线。"""
    _captured_defaults(monkeypatch, login_endpoint="/auth/user/login")
    states = iter([
        ProbeResult(ProbeStatus.CAPTIVE, redirect_url=AUTHORIZE_URL),
        ProbeResult(ProbeStatus.ONLINE),
    ])
    # GET authorize 的前两次（try_session + login_password 预取）都返回登录表单，
    # 登录 POST 后的第三次才 302 发 code
    fake_session.add(lambda u, m: m == "GET" and u == AUTHORIZE_URL,
                     FakeResponse(200, text="<form><input name=password>"),
                     FakeResponse(200, text="<form><input name=password>"),
                     FakeResponse(302, headers={"Location": EPORTAL_CODE_URL}))
    # 2) POST /auth/user/login → 302 回 authorize
    fake_session.add(lambda u, m: m == "POST" and u.endswith("/auth/user/login"),
                     FakeResponse(302, headers={"Location": AUTHORIZE_URL}))
    fake_session.add_url(EPORTAL_CODE_URL, FakeResponse(200, text=SUCCESS_PAGE))

    flow = _flow(fake_session, cfg, lambda: next(states))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.LOGGED_IN
    assert result.via == "password"
    # POST 的表单里携带了用户名与密码
    post_calls = [u for m, u in fake_session.calls if m == "POST"]
    assert post_calls and post_calls[0].endswith("/auth/user/login")


def test_login_rejected(cfg, fake_session, monkeypatch):
    _captured_defaults(monkeypatch, login_endpoint="/auth/user/login")
    fake_session.add_url(AUTHORIZE_URL, FakeResponse(200, text="<input name=password>"))
    fake_session.add(lambda u, m: m == "POST",
                     FakeResponse(200, text='{"msg":"账号或密码错误"}'))

    flow = AuthFlow(fake_session, cfg, sso=SsoAdapter(fake_session, cfg),
                    eportal=EportalAdapter(fake_session, cfg),
                    prober=lambda: ProbeResult(ProbeStatus.CAPTIVE,
                                               redirect_url=AUTHORIZE_URL))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.LOGIN_REJECTED


def test_captcha_blocks_silent_login(cfg, fake_session, monkeypatch):
    _captured_defaults(monkeypatch, has_captcha=True)
    fake_session.add_url(AUTHORIZE_URL, FakeResponse(200, text="<input name=password>"))
    flow = _flow(fake_session, cfg,
                 lambda: ProbeResult(ProbeStatus.CAPTIVE, redirect_url=AUTHORIZE_URL))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.CAPTCHA_REQUIRED


def test_missing_endpoint_reports_protocol_gap(cfg, fake_session, monkeypatch):
    """login_endpoint 未填充（仍在抓包阶段）时给出明确指引而非崩溃。"""
    _captured_defaults(monkeypatch, login_endpoint="<CAPTURE:C2.1>")
    fake_session.add_url(AUTHORIZE_URL, FakeResponse(200, text="<input name=password>"))
    flow = _flow(fake_session, cfg,
                 lambda: ProbeResult(ProbeStatus.CAPTIVE, redirect_url=AUTHORIZE_URL))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.FAILED
    assert "抓包" in result.detail


def test_eportal_success_but_verify_fails(cfg, fake_session, monkeypatch):
    """ePortal 响应成功标记，但二次探测仍被劫持 → 判 FAILED 触发退避。"""
    _captured_defaults(monkeypatch)
    states = iter([
        ProbeResult(ProbeStatus.CAPTIVE, redirect_url=AUTHORIZE_URL),
        ProbeResult(ProbeStatus.CAPTIVE, redirect_url=AUTHORIZE_URL),  # 复测仍未过
    ])
    fake_session.add_url(AUTHORIZE_URL, FakeResponse(
        302, headers={"Location": EPORTAL_CODE_URL}))
    fake_session.add_url(EPORTAL_CODE_URL, FakeResponse(200, text=SUCCESS_PAGE))

    flow = _flow(fake_session, cfg, lambda: next(states))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.FAILED


def test_direct_form_login_no_code(cfg, fake_session, monkeypatch):
    """「表单直登」学校：POST 登录无 code 跳转，直接 200 成功页 → 复测在线。"""
    _captured_defaults(monkeypatch, login_endpoint="/auth/user/login")
    states = iter([
        ProbeResult(ProbeStatus.CAPTIVE, redirect_url=AUTHORIZE_URL),
        ProbeResult(ProbeStatus.ONLINE),
    ])
    fake_session.add(lambda u, m: m == "GET" and u == AUTHORIZE_URL,
                     FakeResponse(200, text="<form><input name=password>"),
                     FakeResponse(200, text="<form><input name=password>"))
    fake_session.add(lambda u, m: m == "POST" and u.endswith("/auth/user/login"),
                     FakeResponse(200, text="认证成功 userIndex='ff00'"))
    flow = _flow(fake_session, cfg, lambda: next(states))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.LOGGED_IN
    assert result.via == "password"


def test_dynamic_aes_key_refresh(cfg, fake_session, monkeypatch):
    """AES 密钥动态（实测每页一变）：登录时以当次登录页内联 key 加密，
    protocol.json 里存的旧 key 不参与本次加密。"""
    from oit_portal.auth.sso import _aes_encrypt
    _captured_defaults(monkeypatch, login_endpoint="/auth/oauth/login")
    monkeypatch.setattr(sso_mod.CAPTURED, "password_encrypt", "aes_cbc")
    monkeypatch.setattr(sso_mod.CAPTURED, "aes_key", "0000000000000000")  # 过期旧 key
    monkeypatch.setattr(sso_mod.CAPTURED, "aes_iv", "0000000000000000")

    fresh_key = "aaaabbbbccccdddd"  # 当次登录页下发的新 key
    vue_page = (
        "<script>var k=CryptoJS.enc.Utf8.parse('" + fresh_key + "');"
        "var e=CryptoJS.AES.encrypt(str,k,{mode:CryptoJS.mode.CBC,"
        "padding:CryptoJS.pad.ZeroPadding});</script>"
        "<div id='app'>Vue SPA 登录页（无 form）</div>"
    )
    states = iter([
        ProbeResult(ProbeStatus.CAPTIVE, redirect_url=AUTHORIZE_URL),
        ProbeResult(ProbeStatus.ONLINE),
    ])
    fake_session.add(lambda u, m: m == "GET" and u == AUTHORIZE_URL,
                     FakeResponse(200, text=vue_page),
                     FakeResponse(200, text=vue_page))
    fake_session.add(lambda u, m: m == "POST" and u.endswith("/auth/oauth/login"),
                     FakeResponse(302, headers={"Location": EPORTAL_CODE_URL}))
    fake_session.add_url(EPORTAL_CODE_URL, FakeResponse(200, text=SUCCESS_PAGE))

    flow = _flow(fake_session, cfg, lambda: next(states))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.LOGGED_IN
    assert result.via == "password"

    # POST 的密码必须用「当次页面的新 key」加密，而不是存量旧 key
    post_url, post_data = fake_session.posts[0]
    assert post_url.endswith("/auth/oauth/login")
    expected = _aes_encrypt("secret-pass", fresh_key, fresh_key, "aes_cbc", "zero")
    assert post_data["password"] == expected


def test_need_credentials_when_no_password(cfg, fake_session, monkeypatch):
    _captured_defaults(monkeypatch)
    cfg.password = None
    cfg.username = None
    fake_session.add_url(AUTHORIZE_URL, FakeResponse(200, text="<input name=password>"))
    flow = _flow(fake_session, cfg,
                 lambda: ProbeResult(ProbeStatus.CAPTIVE, redirect_url=AUTHORIZE_URL))
    result = flow.ensure_online()
    assert result.outcome is FlowOutcome.NEED_CREDENTIALS
