"""入口链路发现：页面级跳转识别 + 挑战提取。"""

from oit_portal.auth.models import PortalChallenge
from oit_portal.discover import follow_entry, looks_authorize, redirect_target

from conftest import AUTHORIZE_URL, FakeResponse, FakeSession, make_config

INJECTED_JS = ("<script>top.self.location.href="
               "'http://172.16.11.54/eportal/index.jsp?wlanuserip=ee5b&t=wireless-v2'"
               "</script>")
META_REFRESH = '<meta http-equiv="refresh" content="0;url=http://portal/next">'
JS_REPLACE = "<script>location.replace('http://portal/alt')</script>"
FORM_PAGE = '<form action="/login"><input name="username"><input type="password" name="pwd"></form>'


def test_redirect_target_js_location():
    assert redirect_target(INJECTED_JS) == \
        "http://172.16.11.54/eportal/index.jsp?wlanuserip=ee5b&t=wireless-v2"


def test_redirect_target_meta_refresh():
    assert redirect_target(META_REFRESH) == "http://portal/next"


def test_redirect_target_location_replace():
    assert redirect_target(JS_REPLACE) == "http://portal/alt"


def test_redirect_target_none_on_form_page():
    assert redirect_target(FORM_PAGE) is None


def test_looks_authorize():
    assert looks_authorize(AUTHORIZE_URL)
    assert not looks_authorize("http://172.16.11.54/eportal/index.jsp?wlanuserip=x")
    assert not looks_authorize("http://example.com/")


def test_follow_entry_injected_js_chain(cfg, fake_session):
    """用户学校实测链路：注入 JS 页 → index.jsp(JS 跳 SSO) → 302 → 登录表单。"""
    hops: list[str] = []
    fake_session.add(lambda u, m: "/eportal/index.jsp" in u,
                     FakeResponse(200, text=f"<script>location.href='{AUTHORIZE_URL}'</script>"))
    fake_session.add(lambda u, m: "oauth/authorize" in u,
                     FakeResponse(302, headers={"Location": "http://open.oit.edu.cn:8090/auth/login"}))
    fake_session.add(lambda u, m: u.endswith("/auth/login"),
                     FakeResponse(200, text=FORM_PAGE))

    entry = follow_entry(fake_session, cfg, hops,
                         page_url="http://connect.rom.miui.com/generate_204",
                         page_body=INJECTED_JS)

    assert entry.challenge is not None
    assert entry.challenge.client_id == "b50485d1-test"
    assert entry.final_url.endswith("/auth/login")
    assert "<form" in entry.resp.text
    # 链路记录完整：注入页跳转 → index → authorize → login
    assert any("页面跳转" in h for h in hops)
    assert len([h for h in hops if h.startswith("GET")]) == 3


def test_follow_entry_302_mode(cfg, fake_session):
    """302 劫持模式：从 redirect_url 出发，跟 30x 到表单页。"""
    hops: list[str] = []
    fake_session.add(lambda u, m: "oauth/authorize" in u,
                     FakeResponse(302, headers={"Location": "http://sso/login"}))
    fake_session.add(lambda u, m: u == "http://sso/login",
                     FakeResponse(200, text=FORM_PAGE))

    entry = follow_entry(fake_session, cfg, hops, redirect_url=AUTHORIZE_URL)
    assert isinstance(entry.challenge, PortalChallenge)
    assert entry.final_url == "http://sso/login"


def test_follow_entry_stops_on_form_no_follow(cfg, fake_session):
    """表单页不跟页面内可能误匹配的 JS（有 <form> 即停）。"""
    hops: list[str] = []
    page = FORM_PAGE + "<script>var s='location.href=x'</script>"
    entry = follow_entry(fake_session, cfg, hops,
                         page_url="http://p/", page_body=page)
    assert entry.challenge is None
    assert entry.final_url == "http://p/"
    assert fake_session.calls == []  # 未发起任何请求
