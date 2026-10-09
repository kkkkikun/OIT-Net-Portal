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


def test_scan_login_endpoints_inline_scripts(fake_session, cfg):
    """Vue SPA 的登录调用常在内联脚本里：无需外链 JS 也应扫出接口。"""
    from oit_portal.capture import scan_login_endpoints
    page = (
        '<div id="app"></div><script>'
        'doLogin(){ axios.post("/auth/oauth/login", {username: this.u, '
        "password: this.$encrypt(this.p)}).then(r=>{location.href=r.data.redirect})}"
        "</script>"
    )
    candidates, evidence, js_dump = scan_login_endpoints(fake_session, cfg,
                                                          "http://sso.example/", page)
    assert "/auth/oauth/login" in candidates
    assert any("axios.post" in e for e in evidence)
    # 完整内联脚本应当原样落入「页面/JS 摘要」
    assert any("axios.post" in d for d in js_dump)


def test_scan_login_endpoints_external_js(fake_session, cfg):
    from oit_portal.capture import scan_login_endpoints
    page = ('<script src="/static/framework/vue.min.js"></script>'
            '<script src="/static/auth/login.js"></script>')
    fake_session.add(lambda u, m: u.endswith("/static/auth/login.js"),
                     FakeResponse(200, text='api.post("/api/v1/ssoLogin",{u:u,p:p});'))
    fake_session.add(lambda u, m: u.endswith("vue.min.js"),
                     FakeResponse(200, text="/* vue framework */"))
    candidates, evidence, js_dump = scan_login_endpoints(fake_session, cfg,
                                                          "http://sso.example/login", page)
    assert "/api/v1/ssoLogin" in candidates
    assert any("ssoLogin" in e for e in evidence)
    # 外链 JS 首部写入摘要
    assert any("/static/auth/login.js" in d for d in js_dump)


def test_scan_login_endpoints_falls_back_to_heuristics(fake_session, cfg):
    """JS 扫描无果时追加启发式候选，并标注「启发式兜底」字样。"""
    from oit_portal.capture import scan_login_endpoints
    # 完全没有 login/token/doLogin 关键字的页面
    page = '<div id="app"><script>var x = 1;</script></div>'
    candidates, _evidence, js_dump = scan_login_endpoints(
        fake_session, cfg, "http://sso.example/authorize", page)
    # 启发式候选应当全部在列
    assert "/auth/oauth/token" in candidates
    assert "/auth/oauth/login" in candidates
    assert "/auth/widget" in candidates  # 轻鸥栈式 widget 控制器
    # 摘要里明确说明这是兜底
    assert any("启发式兜底" in d for d in js_dump)


def test_scan_login_endpoints_jquery_patterns(fake_session, cfg):
    """jQuery 风格登录调用：$.post / $.ajax / $.zytec.* 都能命中，并保留 query string。"""
    from oit_portal.capture import scan_login_endpoints
    page = (
        '<script src="/static/auth/common.js"></script>'
    )
    fake_session.add(lambda u, m: u.endswith("/static/auth/common.js"),
                     FakeResponse(200, text=(
                         '$.zytec.bind_submit = function(){\n'
                         '  $.ajax({url:"/auth/widget?layer=login&widget=Login&action=submit",\n'
                         '         type:"POST", data:$(this).serialize()});\n'
                         '};\n'
                         '$.post("/api/v1/login", {u:u,p:p});'
                     )))
    candidates, evidence, _js_dump = scan_login_endpoints(
        fake_session, cfg, "http://sso.example/authorize", page)
    # scan 应当保留 query string（widget 控制器需要三参数才能匹配）
    assert "/auth/widget?layer=login&widget=Login&action=submit" in candidates
    assert any("jQuery" in e for e in evidence)


def test_scan_login_endpoints_full_auth_js_dump(fake_session, cfg):
    """auth/* JS 文件在报告中应当全文写入摘要（bind_submit 定义藏在里面）。"""
    from oit_portal.capture import scan_login_endpoints
    page = '<script src="/static/auth/common.js"></script>'
    body = ("$.zytec.bind_submit = function(){\n"
            "  return '/auth/widget?layer=login&action=submit';\n"
            "};\n") * 5  # 让文件足够长以验证全文而非 800 字符截断
    fake_session.add(lambda u, m: u.endswith("/static/auth/common.js"),
                     FakeResponse(200, text=body))
    _candidates, _evidence, js_dump = scan_login_endpoints(
        fake_session, cfg, "http://sso.example/authorize", page)
    # 找到 auth/* 全文写入行
    full_dumps = [d for d in js_dump if "全文" in d]
    assert full_dumps, f"应至少有一个 auth/* JS 全文；实际摘要：{js_dump}"
    # 验证文件长度大于 800 字符（否则全文测试无意义）
    assert any(f"({len(body)} 字节，全文)" in d for d in full_dumps)


def test_scan_login_endpoints_detects_token_field_hints(fake_session, cfg):
    """页面内联 JS 里出现 fingerprint/verify_token 等动态 token 字段名时写入摘要。"""
    from oit_portal.capture import scan_login_endpoints
    page = ('<script>'
            'var app = new Vue({'
            '  data:{verify_token:"", verify_code:"", username:"", password_:"", fingerprint:""}'
            '});'
            '</script>')
    _candidates, _evidence, js_dump = scan_login_endpoints(
        fake_session, cfg, "http://sso.example/authorize", page)
    # 应当探测到 fingerprint / verify_token / verify_code
    fields_line = next((d for d in js_dump if "动态 token 字段名" in d), "")
    assert "fingerprint" in fields_line
    assert "verify_token" in fields_line
    assert "verify_code" in fields_line


def test_scan_login_endpoints_heuristic_supplements_base_path(fake_session, cfg):
    """用户学校实测：页面只引用了 slider verify URL（被过滤），scan 找不到登录端点；
    启发式列表必须把 /auth/widget 和它的 query 变体都补上。"""
    from oit_portal.capture import scan_login_endpoints
    # 模拟页面只暴露了 slider verify 接口（不是登录目标）
    page = ('<script>'
            'window.sliderVerify({id:"slider-verify",'
            'get_api:"/auth/widget?layer=image_verify&widget=Slider&action=get_verify&type=login_image_verify"});'
            '</script>')
    candidates, _evidence, js_dump = scan_login_endpoints(
        fake_session, cfg, "http://sso.example/oauth/authorize", page)
    # 启发式应当把 /auth/widget 和它的 query 变体全部补上
    assert "/auth/widget" in candidates
    assert "/auth/widget?layer=login&widget=Login&action=submit" in candidates
    assert "/auth/widget?layer=user&widget=User&action=login" in candidates
    # 摘要里说明是「scan 没找到、启发式补充」
    assert any("启发式" in d for d in js_dump)
    # slider URL 不应作为登录候选（被 widget=Slider / get_verify 过滤）
    assert not any(c.startswith("/auth/widget?")
                   and ("Slider" in c or "image_verify" in c or "get_verify" in c)
                   for c in candidates)


def test_looks_like_spa_catchall():
    """POST 命中 SPA 路由兜底检测：响应 HTML 首段与登录页显著相似。"""
    from oit_portal.capture import _looks_like_spa_catchall
    login_page = "<!doctype html><html><head><script>var a=1;</script>" + ("x" * 200)
    same = FakeResponse(200, text=login_page,
                       headers={"Content-Type": "text/html; charset=utf-8"})
    different = FakeResponse(200, text='{"error":"密码错误"}',
                             headers={"Content-Type": "application/json"})
    form_in_body = FakeResponse(200,
                                text="<html><body><form><input type='password'></form></body></html>",
                                headers={"Content-Type": "text/html"})
    assert _looks_like_spa_catchall(same, login_page) is True
    assert _looks_like_spa_catchall(different, login_page) is False
    assert _looks_like_spa_catchall(form_in_body, login_page) is True


def test_extract_vue_templates_extracts_inline_components():
    """Vue 2 组件模板 <script type='text/x-template'> 应被提取到报告。"""
    from oit_portal.capture import _extract_vue_templates
    html = (
        '<div id="login-form-template-wrap"></div>'
        '<script type="text/x-template" id="login-form-template">'
        '<form action="/auth/widget?layer=user&widget=Account&action=login" method="post">'
        '<input name="username"><input type="password" name="password">'
        '</form>'
        '</script>'
    )
    templates = _extract_vue_templates(html)
    assert len(templates) == 1
    tid, body = templates[0]
    assert tid == "login-form-template"
    assert "/auth/widget?layer=user&widget=Account&action=login" in body
    assert '<input name="username"' in body


def test_extract_vue_templates_handles_id_first_attribute_order():
    """Vue 模板 <script id='...' type='...'> id 在前也应被提取。"""
    from oit_portal.capture import _extract_vue_templates
    html = (
        '<script id="tpl" type="text/x-template"><p>hi</p></script>'
    )
    templates = _extract_vue_templates(html)
    assert ("tpl", "<p>hi</p>") in templates


def test_analyze_form_form_without_action_defaults_to_page_url(cfg, fake_session):
    """用户学校实测：<form method=POST> 无 action 属性 → endpoint 应回退到当前页 URL。

    浏览器原生行为：表单无 action 时 POST 到当前 URL。
    """
    from oit_portal.capture import analyze_form

    page_url = ("http://open.oit.edu.cn:8090/auth/oauth/authorize"
                "?response_type=code&client_id=b50"
                "&redirect_uri=http%3A%2F%2F172.16.11.54%2Feportal%2Flogin_sso.jsp")
    html = (
        '<form method="POST" id="normal_login_form">'
        '  <input v-model="username" id="username" name="username" type="text" placeholder="工号">'
        '  <input v-model="password_" id="password_" :type="passwordType" placeholder="密码">'
        '  <input name="password" type="hidden" v-model="password">'
        '  <input type="hidden" name="fingerprint"/>'
        '  <input type="hidden" name="__token__" value="550b3d92549b791a351f8fdcae939d1a"/>'
        '</form>'
        '<script>'
        '  key = CryptoJS.enc.Utf8.parse("550b3d92549b791a351f8fdcae939d1a".substr(0,16));'
        '  iv = key;'
        '  CryptoJS.AES.encrypt("x", key, {iv: iv, mode: CryptoJS.mode.CBC,'
        '                                padding: CryptoJS.pad.ZeroPadding});'
        '</script>'
    )
    info = analyze_form(fake_session, cfg, page_url, html)
    # 关键：表单无 action，endpoint 应当回退到 page_url（带原始 query string）
    assert info.endpoint == page_url
    # 字段都被收集
    assert info.inputs["username"] == ""
    assert info.inputs["password"] == ""
    assert info.inputs["__token__"] == "550b3d92549b791a351f8fdcae939d1a"
    assert info.inputs["fingerprint"] == ""
    # 用户名 / 密码字段从 hidden 输入识别出来
    assert info.username_field == "username"
    # 关键：password 字段是隐藏的（type="hidden"），但 wizard 应当按 name="password" 识别
    assert info.password_field == "password"
    # AES key 从内联脚本被识别
    assert info.aes_key == "550b3d92549b791a"
    assert info.aes_iv == "550b3d92549b791a"
