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
            else:
                self._redirect(authorize)
        elif "/auth/oauth/authorize2" in path:
            STATE["sso"] = True
            self._redirect(code_url)
        elif "/auth/oauth/authorize" in path:
            if STATE.get("sso"):  # 会话复用直接发码
                self._redirect(code_url)
            else:
                self._redirect(f"{self.base}/login")
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
        body = self.rfile.read(length).decode("utf-8")
        if self.path.startswith("/do_login"):
            ok = (f"username={USER}" in body and f"password={PASSWORD}" in body
                  and f"lt={LT_TOKEN}" in body)
            if ok:
                self._redirect(f"{self.base}/auth/oauth/authorize2?c=1")
            else:
                self._page("账号或密码错误")
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
