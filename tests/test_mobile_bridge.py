"""移动端探测桥接：稳定 dict、敏感字段隔离与 Session 生命周期。"""

import requests

from oit_portal.mobile_bridge import MobileProbeBridge, probe_status

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
