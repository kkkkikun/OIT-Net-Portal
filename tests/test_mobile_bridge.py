"""移动端探测桥接：稳定 dict、敏感字段隔离与 Session 生命周期。"""

from types import SimpleNamespace

import pytest
import requests

from oit_portal.auth.flow import FlowOutcome, FlowResult
from oit_portal.config import DEFAULT_PROBE_URLS
from oit_portal.mobile_bridge import (MobileProbeBridge, create_mobile_bridge,
                                      probe_status)

from conftest import FakeResponse, FakeSession, make_config


MIUI = "http://connect.rom.miui.com/generate_204"
APPLE = "http://captive.apple.com/hotspot-detect.html"


def _cfg():
    cfg = make_config()
    cfg.probe.urls = [MIUI, APPLE]
    return cfg


class ClosableFakeSession(FakeSession):
    def __init__(self):
        super().__init__()
        self.trust_env = True
        self.close_count = 0

    def close(self):
        self.close_count += 1


class FalsyClosableFakeSession(ClosableFakeSession):
    def __bool__(self):
        return False


def test_probe_bridge_maps_online_to_stable_safe_dict():
    session = FakeSession()
    session.add_url(MIUI, FakeResponse(204))
    session.add_url(APPLE, FakeResponse(204))

    result = MobileProbeBridge(_cfg(), session=session).probe()

    assert result == {"status": "ONLINE", "hint": "网络已连接"}


def test_probe_bridge_hides_captive_redirect_and_challenge_data():
    session = FakeSession()
    session.add_url(
        MIUI,
        FakeResponse(302, headers={
            "Location": "http://portal.example/authorize?code=secret-code&token=secret-token"
        }),
    )

    result = MobileProbeBridge(_cfg(), session=session).probe()

    assert result == {"status": "CAPTIVE", "hint": "需要完成校园网认证"}
    assert "secret-code" not in repr(result)
    assert "secret-token" not in repr(result)


def test_probe_bridge_maps_unreachable_probe_to_offline():
    session = FakeSession()
    session.add_url(MIUI, requests.ConnectTimeout("http://private.example?token=secret"))
    session.add_url(APPLE, requests.ConnectionError("http://private.example?token=secret"))

    result = MobileProbeBridge(_cfg(), session=session).probe()

    assert result == {"status": "OFFLINE", "hint": "当前无可用网络"}
    assert "secret" not in repr(result)


def test_probe_bridge_sanitizes_unexpected_errors():
    session = FakeSession()
    session.add_url(MIUI, RuntimeError("password=secret-pass&cookie=secret-cookie"))

    result = MobileProbeBridge(_cfg(), session=session).probe()

    assert result == {"status": "UNKNOWN", "hint": "网络状态暂时不可用"}
    assert "secret-pass" not in repr(result)
    assert "secret-cookie" not in repr(result)


def test_owned_session_is_direct_and_closed_once(monkeypatch):
    created = []

    def make_session():
        session = ClosableFakeSession()
        created.append(session)
        return session

    monkeypatch.setattr("oit_portal.mobile_bridge.requests.Session", make_session)
    cfg = _cfg()
    bridge = MobileProbeBridge(cfg)

    session = created[0]
    assert session.trust_env is False
    assert session.headers["User-Agent"] == cfg.advanced.user_agent

    bridge.close()
    bridge.close()

    assert session.close_count == 1
    assert bridge.probe() == {"status": "UNKNOWN", "hint": "探测桥接已关闭"}


def test_injected_session_is_not_closed_or_reconfigured():
    session = ClosableFakeSession()
    session.add_url(MIUI, FakeResponse(204))
    session.add_url(APPLE, FakeResponse(204))
    bridge = MobileProbeBridge(_cfg(), session=session)

    bridge.close()

    assert session.trust_env is True
    assert session.close_count == 0
    assert session.calls == []
    assert bridge.probe() == {"status": "UNKNOWN", "hint": "探测桥接已关闭"}


def test_false_valued_injected_session_is_used_and_not_closed(monkeypatch):
    created = []

    def make_session():
        session = ClosableFakeSession()
        created.append(session)
        return session

    monkeypatch.setattr("oit_portal.mobile_bridge.requests.Session", make_session)
    session = FalsyClosableFakeSession()
    session.add_url(MIUI, FakeResponse(204))
    session.add_url(APPLE, FakeResponse(204))
    bridge = MobileProbeBridge(_cfg(), session=session)

    result = bridge.probe()
    bridge.close()

    assert created == []
    assert result["status"] == "ONLINE"
    assert session.trust_env is True
    assert session.close_count == 0
    assert session.calls == [("GET", MIUI), ("GET", APPLE)]


def test_probe_status_convenience_uses_injected_session_without_closing_it():
    session = ClosableFakeSession()
    session.add_url(MIUI, FakeResponse(204))
    session.add_url(APPLE, FakeResponse(204))

    result = probe_status(_cfg(), session=session)

    assert result["status"] == "ONLINE"
    assert session.close_count == 0
    assert session.calls == [("GET", MIUI), ("GET", APPLE)]


def _install_auth_flow(monkeypatch, result):
    calls = []

    class FakeAuthFlow:
        def __init__(self, session, cfg, **kwargs):
            calls.append({
                "session": session,
                "cfg": cfg,
                "kwargs": kwargs,
            })

        def ensure_online(self, *, allow_password):
            calls[0]["allow_password"] = allow_password
            if isinstance(result, BaseException):
                raise result
            return result

    monkeypatch.setattr("oit_portal.mobile_bridge.AuthFlow", FakeAuthFlow)
    return calls


@pytest.mark.parametrize(
    ("flow_outcome", "expected"),
    [
        (FlowOutcome.ALREADY_ONLINE, ("ALREADY_ONLINE", "网络已在线")),
        (FlowOutcome.LOGGED_IN, ("LOGGED_IN", "登录成功")),
        (FlowOutcome.NO_NETWORK, ("NO_NETWORK", "当前无可用网络")),
        (FlowOutcome.NEED_CREDENTIALS, ("NEED_CREDENTIALS", "需要更新账号或密码")),
        (FlowOutcome.CAPTCHA_REQUIRED, ("CAPTCHA_REQUIRED", "需要人工完成验证码")),
        (FlowOutcome.LOGIN_REJECTED, ("LOGIN_REJECTED", "账号或密码被拒绝")),
        (FlowOutcome.FAILED, ("FAILED", "登录失败，请稍后重试")),
    ],
)
def test_login_once_maps_all_flow_outcomes(monkeypatch, flow_outcome, expected):
    sensitive_result = FlowResult(
        outcome=flow_outcome,
        detail="url=secret-url&cookie=secret-cookie",
        via="password",
        user_index="secret-user-index",
    )
    calls = _install_auth_flow(monkeypatch, sensitive_result)

    result = MobileProbeBridge(_cfg(), session=FakeSession()).login_once()

    assert result == {"outcome": expected[0], "hint": expected[1]}
    assert "secret-url" not in repr(result)
    assert "secret-cookie" not in repr(result)
    assert "secret-user-index" not in repr(result)
    assert calls[0]["kwargs"]["session_path"] is None


def test_login_once_forwards_allow_password_without_persistence(monkeypatch):
    session = ClosableFakeSession()
    cfg = _cfg()
    calls = _install_auth_flow(monkeypatch, FlowResult(FlowOutcome.NO_NETWORK))
    bridge = MobileProbeBridge(cfg, session=session)

    result = bridge.login_once(allow_password=False)
    bridge.close()

    assert result == {"outcome": "NO_NETWORK", "hint": "当前无可用网络"}
    assert calls[0]["session"] is session
    assert calls[0]["cfg"] is cfg
    assert calls[0]["kwargs"]["session_path"] is None
    assert calls[0]["allow_password"] is False
    assert session.trust_env is True
    assert session.close_count == 0


def test_login_once_sanitizes_unknown_result(monkeypatch):
    _install_auth_flow(monkeypatch, SimpleNamespace(
        outcome=object(),
        detail="redirect=secret-url",
        user_index="secret-user-index",
    ))

    result = MobileProbeBridge(_cfg(), session=FakeSession()).login_once()

    assert result == {"outcome": "FAILED", "hint": "登录失败，请稍后重试"}
    assert "secret-url" not in repr(result)
    assert "secret-user-index" not in repr(result)


def test_login_once_sanitizes_internal_exception(monkeypatch):
    _install_auth_flow(
        monkeypatch,
        RuntimeError("password=secret-pass&code=secret-code"),
    )

    result = MobileProbeBridge(_cfg(), session=FakeSession()).login_once()

    assert result == {"outcome": "FAILED", "hint": "登录失败，请稍后重试"}
    assert "secret-pass" not in repr(result)
    assert "secret-code" not in repr(result)


def test_login_once_does_not_authenticate_after_close(monkeypatch):
    calls = _install_auth_flow(monkeypatch, FlowResult(FlowOutcome.LOGGED_IN))
    bridge = MobileProbeBridge(_cfg(), session=ClosableFakeSession())
    bridge.close()

    result = bridge.login_once()

    assert result == {"outcome": "FAILED", "hint": "桥接已关闭，未执行登录"}
    assert calls == []


def test_login_once_uses_owned_session_and_closes_it(monkeypatch):
    created = []

    def make_session():
        session = ClosableFakeSession()
        created.append(session)
        return session

    monkeypatch.setattr("oit_portal.mobile_bridge.requests.Session", make_session)
    calls = _install_auth_flow(monkeypatch, FlowResult(FlowOutcome.ALREADY_ONLINE))
    bridge = MobileProbeBridge(_cfg())

    result = bridge.login_once()
    bridge.close()
    bridge.close()

    session = created[0]
    assert result == {"outcome": "ALREADY_ONLINE", "hint": "网络已在线"}
    assert calls[0]["session"] is session
    assert session.trust_env is False
    assert session.close_count == 1


def test_create_mobile_bridge_builds_in_memory_config(monkeypatch):
    monkeypatch.setenv("OIT_PORTAL_USERNAME", "unexpected-env-user")
    monkeypatch.setenv("OIT_PORTAL_PASSWORD", "unexpected-env-password")

    bridge = create_mobile_bridge(
        username="factory-user",
        password="factory-password",
        session=FakeSession(),
    )

    cfg = bridge._cfg
    assert cfg.username == "factory-user"
    assert cfg.password == "factory-password"
    assert cfg.config_path is None
    assert cfg.credentials_path is None
    assert cfg.probe.urls == DEFAULT_PROBE_URLS
    assert cfg.probe.urls is not DEFAULT_PROBE_URLS


def test_create_mobile_bridge_copies_probe_urls():
    urls = [MIUI, APPLE]
    bridge = create_mobile_bridge("user", "password", probe_urls=urls,
                                  session=FakeSession())

    urls.append("http://changed.example/probe")

    assert bridge._cfg.probe.urls == [MIUI, APPLE]


@pytest.mark.parametrize(
    ("username", "password"),
    [
        (None, "password"),
        ("", "password"),
        ("   ", "password"),
        ("user", None),
        ("user", ""),
        ("user", "   "),
    ],
)
def test_create_mobile_bridge_rejects_invalid_credentials_safely(username, password):
    with pytest.raises(ValueError, match="账号或密码参数无效") as exc_info:
        create_mobile_bridge(username, password, session=FakeSession())

    assert str(exc_info.value) == "账号或密码参数无效"


@pytest.mark.parametrize(
    "probe_urls",
    [
        [],
        ["http://valid.example/probe", "   "],
        ["http://valid.example/probe", 42],
        "http://valid.example/probe",
    ],
)
def test_create_mobile_bridge_rejects_invalid_probe_urls_safely(probe_urls):
    with pytest.raises(ValueError, match="探测地址参数无效") as exc_info:
        create_mobile_bridge("user", "password", probe_urls=probe_urls,
                             session=FakeSession())

    assert str(exc_info.value) == "探测地址参数无效"


def test_create_mobile_bridge_owns_and_closes_created_session(monkeypatch):
    created = []

    def make_session():
        session = ClosableFakeSession()
        created.append(session)
        return session

    monkeypatch.setattr("oit_portal.mobile_bridge.requests.Session", make_session)

    bridge = create_mobile_bridge("user", "password")
    bridge.close()
    bridge.close()

    session = created[0]
    assert session.trust_env is False
    assert session.close_count == 1


def test_create_mobile_bridge_preserves_injected_session_ownership():
    session = ClosableFakeSession()
    session.add_url(MIUI, FakeResponse(204))
    session.add_url(APPLE, FakeResponse(204))

    bridge = create_mobile_bridge("user", "password", probe_urls=[MIUI, APPLE],
                                  session=session)
    result = bridge.probe()
    bridge.close()

    assert result == {"status": "ONLINE", "hint": "网络已连接"}
    assert session.trust_env is True
    assert session.close_count == 0


def test_create_mobile_bridge_reuses_login_once(monkeypatch):
    session = ClosableFakeSession()
    calls = _install_auth_flow(monkeypatch, FlowResult(FlowOutcome.NEED_CREDENTIALS))
    bridge = create_mobile_bridge("user", "password", session=session)

    result = bridge.login_once(allow_password=False)
    bridge.close()

    assert result == {"outcome": "NEED_CREDENTIALS", "hint": "需要更新账号或密码"}
    assert calls[0]["cfg"].username == "user"
    assert calls[0]["allow_password"] is False
    assert calls[0]["kwargs"]["session_path"] is None
    assert session.close_count == 0
