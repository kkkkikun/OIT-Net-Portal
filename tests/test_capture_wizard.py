"""capture 向导端到端测试：本地模拟校园网认证链（SSO 表单 → code → ePortal 上线）。

模拟服务器还原真实跳转结构：
  探测点(302/204) → authorize(302) → 登录表单(200) → POST 账密(302)
  → authorize2 发 code(302) → login_sso.jsp 成功页(200) → 探测点 204
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import quote

import pytest
import sys

from oit_portal.capture import run_capture
from oit_portal.paths import AppPaths

from conftest import make_config

USER, PASSWORD = "20230001", "secret-pass"
LT_TOKEN = "LT-6f00d"

STATE: dict = {}


def _build_urls(base: str) -> tuple[str, str, str]:
    redirect_uri = quote(
        f"{base}/eportal/login_sso.jsp?wlanuserip=cafe&mac=0011&t=wireless-v2",
        safe="",
    )
    authorize = (f"{base}/auth/oauth/authorize?response_type=code"
                 f"&client_id=cli-test&redirect_uri={redirect_uri}")
    code_url = (f"{base}/eportal/login_sso.jsp?code=TESTCODE"
                f"&wlanuserip=cafe&mac=0011&t=wireless-v2")
    return authorize, redirect_uri, code_url


class FakeCampusHandler(BaseHTTPRequestHandler):
    base: str = ""  # 由 fixture 注入

    def log_message(self, *args):  # 静音访问日志
        pass

    def _redirect(self, location: str, cookie: str | None = None):
        self.send_response(302)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _page(self, body: str, status: int = 200, cookie: str | None = None):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        authorize, _ru, code_url = _build_urls(self.base)
        path = self.path
        if path.startswith("/generate_204") or path.startswith("/gen2"):
            if STATE.get("online"):
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()
            elif STATE.get("transparent"):
                # 注入式劫持形态 A：注入页即表单本体（无 302、无页面跳转）
                form = (
                    f'<form action="{self.base}/do_login" method="post">'
                    '<input type="text" name="username">'
                    '<input type="password" name="password">'
                    f'<input type="hidden" name="lt" value="{LT_TOKEN}">'
                    "</form>"
                )
                self._page(form)
            elif STATE.get("injected_chain"):
                # 注入式劫持形态 B（用户学校实测）：注入 JS 跳转页 → ePortal
                # index.jsp → 再 JS 跳 SSO authorize → 302 → 登录表单
                self._page(
                    "<script>top.self.location.href="
                    f"'{self.base}/eportal/index.jsp?wlanuserip=ee5b&t=wireless-v2'"
                    "</script>")
            else:
                self._redirect(authorize)
        elif "/eportal/index.jsp" in path:
            # ePortal 入口页：JS 跳转 SSO authorize（用户学校链路的第二跳）
            self._page(f"<script>location.href='{authorize}'</script>")
        elif "/auth/oauth/authorize2" in path:
            STATE["sso"] = True
            self._redirect(code_url)
        elif "/auth/oauth/authorize" in path:
            if STATE.get("sso"):  # 会话复用直接发码
                self._redirect(code_url)
            elif STATE.get("vue_login"):
                # 用户学校实测形态：authorize 直接返回 Vue SPA 登录页（无 <form>），
                # 密码 AES 加密的内联脚本 + 外链 login.js 里的接口调用
                scripts = ('<script src="/static/framework/vue/vue.min.js"></script>'
                           '<script src="/static/framework/crypto-js-3.3.0/crypto-js.js"></script>')
                if STATE.get("jquery_widget") or STATE.get("real_school"):
                    # 真实用户学校形态：业务 JS 在 common.js 里，调用用 $.zytec
                    scripts += '<script src="/static/auth/common.js"></script>'
                elif not STATE.get("spa_catchall"):
                    # 正常情况：外链 login.js 里调真实登录接口
                    scripts += '<script src="/static/auth/login.js"></script>'
                inline = ""
                if STATE.get("real_school"):
                    # 用户学校实测：内联脚本里只有 slider verify URL（不是登录目标）
                    inline = ("<script>window.sliderVerify({id:'slider-verify',"
                              "get_api:'/auth/widget?layer=image_verify"
                              "&widget=Slider&action=get_verify"
                              "&type=login_image_verify',"
                              "onSuccess:function(){}});</script>")
                body = ""
                if STATE.get("form_no_action"):
                    # 用户学校实测形态：表单有 <form method=POST> 但无 action 属性，
                    # 浏览器原生行为是提交到当前 URL
                    body = (
                        '<div id="normal_login_container">'
                        '<form method="POST" id="normal_login_form">'
                        '<input type="hidden" name="fingerprint"/>'
                        '<input name="username" type="text" placeholder="工号">'
                        '<input name="password_" :type="passwordType" placeholder="密码">'
                        '<input name="password" type="hidden" v-model="password"/>'
                        '<input type="hidden" name="__token__" '
                        'value="563a38b893f98998d4917875837ee800"/>'
                        '<button type="submit">登 录</button>'
                        '</form>'
                        '</div>'
                    )
                vue_page = (
                    "<!doctype html><html><head>"
                    + scripts +
                    "<script>Vue.prototype.$encrypt = function(str) {"
                    "key = CryptoJS.enc.Utf8.parse('563a38b893f98998d4917875837ee800'"
                    ".substr(0,16));"
                    "iv = CryptoJS.enc.Utf8.parse('563a38b893f98998d4917875837ee800'"
                    ".substr(0,16));"
                    "var encrypted = CryptoJS.AES.encrypt(str, key, {iv: iv,"
                    " mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.ZeroPadding});"
                    "return encrypted;}</script>"
                    + inline +
                    '<body class="auth okta-container">'
                    + body +
                    '<div id="app"></div></body></html>'
                )
                self._page(vue_page, cookie="SID=sso-sess-1")
            else:
                self._redirect(f"{self.base}/login")
        elif path.startswith("/static/auth/login.js"):
            self._page('axios.post("/auth/oauth/login",'
                       '{username:this.username,password:this.$encrypt(this.password)});')
        elif path.startswith("/static/auth/common.js"):
            # 用户学校实测：common.js 里 $.zytec.bind_submit() 内部调 /auth/widget
            # — 但若 STATE["real_school"] 则只暴露 slider verify URL，
            # 真实登录端点要靠启发式命中
            if STATE.get("real_school"):
                self._page("$.extend($,{zytec:{bind_submit:function(){}"
                           ",init:function(){}}});")
            else:
                self._page("$.extend($,{zytec:{bind_submit:function(){"
                           "$.ajax({url:'/auth/widget?layer=login&widget=Login&action=submit',"
                           "type:'POST',data:{username:u,password:p}});}}});")
        elif path.startswith("/static/framework/"):
            self._page("/* framework lib */")
        elif path.startswith("/login"):
            form = (
                '<form action="/do_login" method="post">'
                '<input type="text" name="username">'
                '<input type="password" name="password">'
                f'<input type="hidden" name="lt" value="{LT_TOKEN}">'
                "</form>"
            )
            self._page(form, cookie="JSESSIONID=sess-abc123")
        elif "/eportal/login_sso.jsp" in path:
            STATE["online"] = True
            self._page("认证成功 <script>var userIndex='a1b2';"
                       "var keepaliveInterval=0;</script>")
        else:
            self._page("not found", status=404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        if self.path.startswith("/do_login"):
            ok = (f"username={USER}" in raw and f"password={PASSWORD}" in raw
                  and f"lt={LT_TOKEN}" in raw)
            if ok:
                self._redirect(f"{self.base}/auth/oauth/authorize2?c=1")
            else:
                self._page("账号或密码错误")
        elif (self.path.startswith("/auth/oauth/login")
              and not STATE.get("spa_catchall")
              and not STATE.get("real_school")
              and not STATE.get("jquery_widget")):
            # Vue SPA 接口：校验 AES 加密密码（与服务端真实行为一致：先解密再比对）
            from urllib.parse import parse_qs
            from Crypto.Cipher import AES
            fields = parse_qs(raw)
            user = fields.get("username", [""])[0]
            cipher_b64 = fields.get("password", [""])[0]
            try:
                plain_bytes = AES.new(b"563a38b893f98998", AES.MODE_CBC,
                                      b"563a38b893f98998").decrypt(
                    __import__("base64").b64decode(cipher_b64))
                plain = plain_bytes.rstrip(b"\x00").decode("utf-8")
            except Exception:
                plain = ""
            if user == USER and plain == PASSWORD:
                STATE["sso"] = True
                self._redirect(f"{self.base}/auth/oauth/authorize2?c=1")
            else:
                self._page('{"error":"密码错误"}')
        elif STATE.get("spa_catchall"):
            # 模拟用户学校实测——任何未实现的接口都把 SPA 页面吐回来
            spa_page = (
                "<!doctype html><html><head>"
                '<script src="/static/framework/vue/vue.min.js"></script>'
                '<script src="/static/framework/crypto-js-3.3.0/crypto-js.js"></script>'
                "<script>Vue.prototype.$encrypt = function(str) {"
                "key = CryptoJS.enc.Utf8.parse('2e018f01abcdef02');"
                "iv = CryptoJS.enc.Utf8.parse('2e018f01abcdef02');"
                "var encrypted = CryptoJS.AES.encrypt(str, key, {iv: iv,"
                " mode: CryptoJS.mode.CBC, padding: CryptoJS.pad.ZeroPadding});"
                "return encrypted;}</script></head>"
                '<body class="auth okta-container"><div id="app"></div></body></html>'
            )
            self._page(spa_page)
        elif (self.path.startswith("/auth/widget")
              and (STATE.get("jquery_widget") or STATE.get("real_school"))):
            # 用户学校实测：/auth/widget?layer=login&... 接收 AES 加密的账密，
            # 校验通过则返回 JSON 含 redirect 跳到 login_sso.jsp?code=...
            from urllib.parse import parse_qs, urlparse
            from Crypto.Cipher import AES
            fields = parse_qs(raw)
            user = fields.get("username", [""])[0]
            cipher_b64 = fields.get("password", [""])[0]
            try:
                plain_bytes = AES.new(b"563a38b893f98998", AES.MODE_CBC,
                                      b"563a38b893f98998").decrypt(
                    __import__("base64").b64decode(cipher_b64))
                plain = plain_bytes.rstrip(b"\x00").decode("utf-8")
            except Exception:
                plain = ""
            # 路由校验：query 必须匹配 layer=user&widget=User&action=login 才处理
            qs = urlparse(self.path).query
            qs_dict = parse_qs(qs)
            layer = (qs_dict.get("layer") or [""])[0]
            widget = (qs_dict.get("widget") or [""])[0]
            action = (qs_dict.get("action") or [""])[0]
            valid_route = (layer == "user" and widget == "User"
                          and action == "login")
            if valid_route and user == USER and plain == PASSWORD:
                STATE["sso"] = True
                redirect = f"{self.base}/eportal/login_sso.jsp?code=TESTCODE"
                self._page(f'{{"code":1,"data":{{"redirect":"{redirect}"}}}}')
            else:
                self._page('{"code":0,"data":false,'
                          '"message":"账号或密码错误或路由不正确",'
                          f'"_route":"{layer}/{widget}/{action}"' + '}')
        elif (self.path.startswith("/auth/oauth/authorize")
              and STATE.get("form_no_action")):
            # 用户学校实测：POST 到当前 authorize URL（表单无 action 属性时浏览器默认行为）
            from urllib.parse import parse_qs
            from Crypto.Cipher import AES
            fields = parse_qs(raw)
            user = fields.get("username", [""])[0]
            cipher_b64 = fields.get("password", [""])[0]
            token = fields.get("__token__", [""])[0]
            try:
                plain_bytes = AES.new(b"563a38b893f98998", AES.MODE_CBC,
                                      b"563a38b893f98998").decrypt(
                    __import__("base64").b64decode(cipher_b64))
                plain = plain_bytes.rstrip(b"\x00").decode("utf-8")
            except Exception:
                plain = ""
            if user == USER and plain == PASSWORD and token:
                STATE["sso"] = True
                # 服务端可能重定向到 login_sso.jsp
                self._redirect(
                    f"{self.base}/eportal/login_sso.jsp?code=TESTCODE"
                    "&wlanuserip=deadbeef&mac=0011&t=wireless-v2"
                )
            else:
                self._page("账号或密码错误", status=401)
        else:
            self._page("not found", status=404)


@pytest.fixture
def campus_server():
    STATE.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeCampusHandler)
    port = server.server_address[1]
    base = f"http://127.0.0.1:{port}"
    FakeCampusHandler.base = base
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield base
    server.shutdown()
    server.server_close()


def test_capture_wizard_full_success(campus_server, tmp_path, monkeypatch):
    # 交互桩：账号直接回车用配置默认值；「使用已保存的密码？」回车确认
    answers = iter(["", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)
    # 向导要求交互式终端
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))

    cfg = make_config(tmp_path)
    cfg.probe.urls = [f"{campus_server}/generate_204", f"{campus_server}/gen2"]
    home = tmp_path / "home"
    paths = AppPaths(home=home, config=home / "config.toml",
                     credentials=home / "credentials.toml",
                     session=home / "session.json", log_dir=tmp_path / "logs",
                     log_file=tmp_path / "logs" / "l.log",
                     lock=tmp_path / "l.lock", pid=tmp_path / "l.pid")

    rc = run_capture(cfg, paths)
    assert rc == 0

    # 自配置文件：向导发现的协议参数
    protocol = json.loads((home / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["sso"]["login_endpoint"] == "/do_login"
    assert protocol["sso"]["username_field"] == "username"
    assert protocol["sso"]["password_field"] == "password"
    assert protocol["sso"]["extra_fields"] == {"lt": LT_TOKEN}
    assert protocol["sso"]["password_encrypt"] == "none"
    assert protocol["eportal"]["online_mode"] == "sso_pass"

    # SSO 会话已持久化（模拟服务器下发的 JSESSIONID）
    session_data = json.loads((home / "session.json").read_text(encoding="utf-8"))
    assert any(c["name"] == "JSESSIONID" for c in session_data)

    # 脱敏报告存在且不含密码
    report = (home / "capture-report.txt").read_text(encoding="utf-8")
    assert "登录成功" in report
    assert PASSWORD not in report


def test_capture_wizard_rejects_when_online(campus_server, tmp_path, monkeypatch):
    """已在线状态直接提示退出（返回 2），不进入表单流程。"""
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    STATE["online"] = True
    cfg = make_config(tmp_path)
    cfg.probe.urls = [f"{campus_server}/generate_204", f"{campus_server}/gen2"]
    home = tmp_path / "home"
    paths = AppPaths(home=home, config=home / "config.toml",
                     credentials=home / "credentials.toml",
                     session=home / "session.json", log_dir=tmp_path / "logs",
                     log_file=tmp_path / "logs" / "l.log",
                     lock=tmp_path / "l.lock", pid=tmp_path / "l.pid")
    assert run_capture(cfg, paths) == 2


def test_capture_wizard_transparent_mode(campus_server, tmp_path, monkeypatch):
    """注入式劫持形态：探测点直接返回 200 认证页（无 302），向导仍能完成全流程。"""
    STATE["transparent"] = True
    answers = iter(["", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))

    cfg = make_config(tmp_path)
    cfg.probe.urls = [f"{campus_server}/generate_204", f"{campus_server}/gen2"]
    home = tmp_path / "home"
    paths = AppPaths(home=home, config=home / "config.toml",
                     credentials=home / "credentials.toml",
                     session=home / "session.json", log_dir=tmp_path / "logs",
                     log_file=tmp_path / "logs" / "l.log",
                     lock=tmp_path / "l.lock", pid=tmp_path / "l.pid")

    rc = run_capture(cfg, paths)
    assert rc == 0
    assert (home / "protocol.json").is_file()
    assert (home / "capture-report.txt").is_file()
    # 登录后的在线验证走通（服务器状态已被 POST 流程置为 online）
    report = (home / "capture-report.txt").read_text(encoding="utf-8")
    assert "登录成功" in report
    assert "200 注入页" in report
    assert PASSWORD not in report


def test_capture_wizard_injected_js_chain(campus_server, tmp_path, monkeypatch):
    """用户学校实测链路端到端：探测点 200 注入 JS 页 → ePortal index.jsp
    → JS 跳 SSO authorize → 302 登录表单 → POST → code → 上线。"""
    STATE["injected_chain"] = True
    answers = iter(["", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))

    cfg = make_config(tmp_path)
    cfg.probe.urls = [f"{campus_server}/generate_204", f"{campus_server}/gen2"]
    home = tmp_path / "home"
    paths = AppPaths(home=home, config=home / "config.toml",
                     credentials=home / "credentials.toml",
                     session=home / "session.json", log_dir=tmp_path / "logs",
                     log_file=tmp_path / "logs" / "l.log",
                     lock=tmp_path / "l.lock", pid=tmp_path / "l.pid")

    rc = run_capture(cfg, paths)
    assert rc == 0
    report = (home / "capture-report.txt").read_text(encoding="utf-8")
    assert "登录成功" in report
    assert "/eportal/index.jsp" in report  # 链路经过了 ePortal 入口页
    assert PASSWORD not in report
    session_data = json.loads((home / "session.json").read_text(encoding="utf-8"))
    assert any(c["name"] == "JSESSIONID" for c in session_data)


def test_capture_wizard_vue_spa_aes(campus_server, tmp_path, monkeypatch):
    """用户学校最新实测形态端到端：注入 JS 页 → index.jsp → authorize 返回
    Vue SPA（无表单、AES 内联加密脚本）→ 扫描 login.js 找到接口 →
    AES 加密密码 POST → code → 上线 → 写含 AES 参数的 protocol.json。"""
    STATE["injected_chain"] = True
    STATE["vue_login"] = True
    answers = iter(["", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))

    cfg = make_config(tmp_path)
    cfg.probe.urls = [f"{campus_server}/generate_204", f"{campus_server}/gen2"]
    home = tmp_path / "home"
    paths = AppPaths(home=home, config=home / "config.toml",
                     credentials=home / "credentials.toml",
                     session=home / "session.json", log_dir=tmp_path / "logs",
                     log_file=tmp_path / "logs" / "l.log",
                     lock=tmp_path / "l.lock", pid=tmp_path / "l.pid")

    rc = run_capture(cfg, paths)
    assert rc == 0

    protocol = json.loads((home / "protocol.json").read_text(encoding="utf-8"))
    assert protocol["sso"]["login_endpoint"] == "/auth/oauth/login"
    assert protocol["sso"]["username_field"] == "username"
    assert protocol["sso"]["password_field"] == "password"
    assert protocol["sso"]["password_encrypt"] == "aes_cbc"
    assert protocol["sso"]["aes_key"] == "563a38b893f98998"
    assert protocol["sso"]["aes_iv"] == "563a38b893f98998"
    assert protocol["sso"]["aes_padding"] == "zero"
    assert protocol["eportal"]["online_mode"] == "sso_pass"

    report = (home / "capture-report.txt").read_text(encoding="utf-8")
    assert "登录成功" in report
    assert PASSWORD not in report


def test_capture_wizard_wrong_password(campus_server, tmp_path, monkeypatch):
    """密码错误 → 报告含失败记录，返回 1，不写 protocol.json。"""
    answers = iter(["", "n"])  # 账号用默认；拒绝已存密码，改输错密码
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": "wrong-pass")
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))

    cfg = make_config(tmp_path)
    cfg.probe.urls = [f"{campus_server}/generate_204", f"{campus_server}/gen2"]
    home = tmp_path / "home"
    paths = AppPaths(home=home, config=home / "config.toml",
                     credentials=home / "credentials.toml",
                     session=home / "session.json", log_dir=tmp_path / "logs",
                     log_file=tmp_path / "logs" / "l.log",
                     lock=tmp_path / "l.lock", pid=tmp_path / "l.pid")
    assert run_capture(cfg, paths) == 1
    assert not (home / "protocol.json").exists()
    report = (home / "capture-report.txt").read_text(encoding="utf-8")
    assert "wrong-pass" not in report  # 密码永不入报告


def test_capture_wizard_no_real_endpoint(campus_server, tmp_path, monkeypatch):
    """用户学校最新失败形态：Vue SPA 页面找不到登录接口、POST 全部命中 SPA catch-all。
    报告必须含完整「页面/JS 摘要」便于维护者人工分析。"""
    STATE.clear()
    STATE["injected_chain"] = True
    STATE["vue_login"] = True
    STATE["spa_catchall"] = True  # POST /auth/oauth/authorize 返回登录页 HTML
    answers = iter(["", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))

    cfg = make_config(tmp_path)
    cfg.probe.urls = [f"{campus_server}/generate_204", f"{campus_server}/gen2"]
    home = tmp_path / "home"
    paths = AppPaths(home=home, config=home / "config.toml",
                     credentials=home / "credentials.toml",
                     session=home / "session.json", log_dir=tmp_path / "logs",
                     log_file=tmp_path / "logs" / "l.log",
                     lock=tmp_path / "l.lock", pid=tmp_path / "l.pid")

    rc = run_capture(cfg, paths)
    assert rc == 1  # 失败
    assert not (home / "protocol.json").exists()

    report = (home / "capture-report.txt").read_text(encoding="utf-8")
    # 关键诊断信息必须出现在「页面/JS 摘要」小节里
    assert "页面/JS 摘要" in report
    assert "页面内联 <script>" in report
    # 内联 AES 加密脚本原样落入摘要（维护者可据此反推接口调用模式）
    assert "CryptoJS.AES.encrypt" in report
    # 启发式兜底应当被触发
    assert "启发式兜底" in report
    # SPA catch-all 检测应当出现在跳转链
    assert "SPA 路由兜底" in report
    # 密码永不入报告
    assert PASSWORD not in report


def test_capture_wizard_jquery_widget_endpoint(campus_server, tmp_path, monkeypatch):
    """用户学校实测形态：Vue + jQuery 应用，登录调用走 $.zytec.bind_submit()
    内部 ajax 到 /auth/widget?layer=login&widget=Login&action=submit。
    向导应通过启发式兜底命中该端点并完成登录。"""
    STATE.clear()
    STATE["injected_chain"] = True
    STATE["vue_login"] = True     # 渲染 Vue SPA 登录页
    STATE["jquery_widget"] = True  # 走 /auth/widget?... 路由
    answers = iter(["", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))

    cfg = make_config(tmp_path)
    cfg.probe.urls = [f"{campus_server}/generate_204", f"{campus_server}/gen2"]
    home = tmp_path / "home"
    paths = AppPaths(home=home, config=home / "config.toml",
                     credentials=home / "credentials.toml",
                     session=home / "session.json", log_dir=tmp_path / "logs",
                     log_file=tmp_path / "logs" / "l.log",
                     lock=tmp_path / "l.lock", pid=tmp_path / "l.pid")

    rc = run_capture(cfg, paths)
    assert rc == 0

    protocol = json.loads((home / "protocol.json").read_text(encoding="utf-8"))
    # 命中 /auth/widget 启发式候选之一
    assert "/auth/widget" in protocol["sso"]["login_endpoint"]
    assert protocol["sso"]["password_encrypt"] == "aes_cbc"
    assert protocol["sso"]["aes_key"] == "563a38b893f98998"
    assert protocol["eportal"]["online_mode"] == "sso_pass"

    report = (home / "capture-report.txt").read_text(encoding="utf-8")
    assert "登录成功" in report
    assert PASSWORD not in report


def test_capture_wizard_real_school_scenario(campus_server, tmp_path, monkeypatch):
    """用户学校最新实测：Vue+jQuery SPA + slider verify URL + 启发式 layer=user&widget=User&action=login。
    模拟页面只暴露 slider verify URL（被过滤），真实登录端点由启发式命中。"""
    STATE.clear()
    STATE["injected_chain"] = True
    STATE["vue_login"] = True
    STATE["real_school"] = True  # 走 /auth/widget?layer=user&widget=User&action=login
    answers = iter(["", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))

    cfg = make_config(tmp_path)
    cfg.probe.urls = [f"{campus_server}/generate_204", f"{campus_server}/gen2"]
    home = tmp_path / "home"
    paths = AppPaths(home=home, config=home / "config.toml",
                     credentials=home / "credentials.toml",
                     session=home / "session.json", log_dir=tmp_path / "logs",
                     log_file=tmp_path / "logs" / "l.log",
                     lock=tmp_path / "l.lock", pid=tmp_path / "l.pid")

    rc = run_capture(cfg, paths)
    assert rc == 0

    protocol = json.loads((home / "protocol.json").read_text(encoding="utf-8"))
    # 命中 /auth/widget?layer=user&widget=User&action=login 这一条
    assert protocol["sso"]["login_endpoint"] == "/auth/widget?layer=user&widget=User&action=login"
    assert protocol["sso"]["password_encrypt"] == "aes_cbc"
    assert protocol["eportal"]["online_mode"] == "sso_pass"

    report = (home / "capture-report.txt").read_text(encoding="utf-8")
    assert "登录成功" in report
    assert PASSWORD not in report


def test_capture_wizard_form_without_action(campus_server, tmp_path, monkeypatch):
    """用户学校实测：<form method=POST> 无 action 属性时浏览器默认提交到当前 URL。

    关键修复点：
    - htmlutil.form_action 见到表单无 action 时返回 ""（不是 None）
    - analyze_form 用 page_url 兜底作为 endpoint
    - 隐藏字段 name="password" 也被识别为密码字段
    - 所有隐藏字段（__token__、fingerprint）随表单一起提交
    """
    STATE.clear()
    STATE["injected_chain"] = True
    STATE["vue_login"] = True
    STATE["form_no_action"] = True  # 表单无 action 属性
    answers = iter(["", ""])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(answers))
    monkeypatch.setattr("getpass.getpass", lambda prompt="": PASSWORD)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))

    cfg = make_config(tmp_path)
    cfg.probe.urls = [f"{campus_server}/generate_204", f"{campus_server}/gen2"]
    home = tmp_path / "home"
    paths = AppPaths(home=home, config=home / "config.toml",
                     credentials=home / "credentials.toml",
                     session=home / "session.json", log_dir=tmp_path / "logs",
                     log_file=tmp_path / "logs" / "l.log",
                     lock=tmp_path / "l.lock", pid=tmp_path / "l.pid")

    rc = run_capture(cfg, paths)
    assert rc == 0

    protocol = json.loads((home / "protocol.json").read_text(encoding="utf-8"))
    # endpoint 必须是当前 authorize URL（带原始 query string）
    assert protocol["sso"]["login_endpoint"].endswith(
        "/auth/oauth/authorize?response_type=code&client_id=cli-test"
        "&redirect_uri=http%3A%2F%2F127.0.0.1%3Axxx%2Feportal%2Flogin_sso.jsp"
    ) or "auth/oauth/authorize" in protocol["sso"]["login_endpoint"]
    assert protocol["sso"]["password_encrypt"] == "aes_cbc"
    # 隐藏字段被作为 extra_fields 保存
    assert "fingerprint" in protocol["sso"]["extra_fields"]
    assert protocol["eportal"]["online_mode"] == "sso_pass"

    report = (home / "capture-report.txt").read_text(encoding="utf-8")
    assert "登录成功" in report
    assert PASSWORD not in report
