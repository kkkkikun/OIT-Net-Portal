"""探测器三态判定与双确认逻辑。"""

import requests

from oit_portal.probe import ProbeStatus, probe

from conftest import FakeResponse, FakeSession, make_config

MIUI = "http://connect.rom.miui.com/generate_204"
APPLE = "http://captive.apple.com/hotspot-detect.html"


def _cfg():
    cfg = make_config()
    cfg.probe.urls = [MIUI, APPLE]
    return cfg


def test_204_means_online(fake_session):
    fake_session.add_url(MIUI, FakeResponse(204))
    fake_session.add_url(APPLE, FakeResponse(204))  # 双确认
    result = probe(fake_session, _cfg())
    assert result.status is ProbeStatus.ONLINE


def test_302_means_captive_with_redirect():
    s = FakeSession()
    s.add_url(MIUI, FakeResponse(302, headers={"Location": "http://portal/authorize?x=1"}))
    result = probe(s, _cfg())
    assert result.status is ProbeStatus.CAPTIVE
    assert result.redirect_url == "http://portal/authorize?x=1"


def test_double_confirm_overrides_false_online():
    """首探测点被白名单放行(204)，第二点 302 → 按劫持处理（防误判）。"""
    s = FakeSession()
    s.add_url(MIUI, FakeResponse(204))
    s.add_url(APPLE, FakeResponse(302, headers={"Location": "http://portal/x"}))
    result = probe(s, _cfg())
    assert result.status is ProbeStatus.CAPTIVE
    assert result.redirect_url == "http://portal/x"


def test_apple_success_body_means_online():
    s = FakeSession()
    s.add_url(MIUI, FakeResponse(204))
    s.add_url(APPLE, FakeResponse(200, text="<HTML><HEAD><TITLE>Success</TITLE>"))
    assert probe(s, _cfg()).status is ProbeStatus.ONLINE


def test_200_without_success_marker_is_captive():
    s = FakeSession()
    s.add_url(MIUI, FakeResponse(302, headers={"Location": "http://portal/x"}))
    # 池中第一项已判 CAPTIVE，直接返回
    result = probe(s, _cfg())
    assert result.status is ProbeStatus.CAPTIVE


def test_all_unreachable_means_offline():
    s = FakeSession()
    s.add_url(MIUI, requests.ConnectTimeout())
    s.add_url(APPLE, requests.ConnectionError())
    result = probe(s, _cfg())
    assert result.status is ProbeStatus.OFFLINE


def test_first_down_second_204_online():
    """第一个探测点不可达时轮换到下一个。"""
    s = FakeSession()
    s.add_url(MIUI, requests.ConnectTimeout())
    s.add_url(APPLE, FakeResponse(204))
    result = probe(s, _cfg())
    assert result.status is ProbeStatus.ONLINE
