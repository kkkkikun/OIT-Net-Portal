from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from oit_portal.config import Config, load_config, save_network_settings
from oit_portal.network import (SourceAddressAdapter, create_session,
                                physical_source_ip, validate_source_ip)


def completed(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, returncode=returncode)


def test_linux_source_ip_prefers_physical_default_route(monkeypatch):
    interfaces = [
        {"ifname": "tun0", "flags": ["UP"], "addr_info": [
            {"family": "inet", "scope": "global", "local": "10.8.0.2"}]},
        {"ifname": "wlan0", "flags": ["UP"], "addr_info": [
            {"family": "inet", "scope": "global", "local": "172.18.10.25"}]},
    ]

    def run(command, **_kwargs):
        if "address" in command:
            return completed(json.dumps(interfaces))
        return completed(json.dumps([{"dev": "tun0"}, {"dev": "wlan0"}]))

    monkeypatch.setattr("oit_portal.network.subprocess.run", run)
    monkeypatch.setattr("oit_portal.network.sys.platform", "linux")
    assert physical_source_ip() == "172.18.10.25"


def test_windows_source_ip_ignores_vpn_and_virtual_adapters(monkeypatch):
    output = """Ethernet adapter Clash:\n   IPv4 Address. . . . . . . . . . . : 10.0.0.2\n   Default Gateway . . . . . . . . . : 10.0.0.1\n\nWireless LAN adapter Wi-Fi:\n   IPv4 Address. . . . . . . . . . . : 172.18.20.30\n   Default Gateway . . . . . . . . . : 172.18.20.1\n"""
    monkeypatch.setattr("oit_portal.network.subprocess.run",
                        lambda *_args, **_kwargs: completed(output))
    monkeypatch.setattr("oit_portal.network.sys.platform", "win32")
    assert physical_source_ip() == "172.18.20.30"


def test_session_binds_both_http_and_https(monkeypatch):
    cfg = Config()
    cfg.advanced.bypass_vpn = True
    cfg.advanced.direct_source_ip = "172.18.1.20"
    session = create_session(cfg)
    try:
        assert session.trust_env is False
        for scheme in ("http://", "https://"):
            adapter = session.get_adapter(scheme + "example.test")
            assert isinstance(adapter, SourceAddressAdapter)
            assert adapter.poolmanager.connection_pool_kw["source_address"] == ("172.18.1.20", 0)
    finally:
        session.close()


def test_session_auto_detection_failure_preserves_normal_session(monkeypatch):
    cfg = Config()
    cfg.advanced.bypass_vpn = True
    monkeypatch.setattr("oit_portal.network.physical_source_ip", lambda: None)
    session = create_session(cfg)
    assert type(session.get_adapter("http://example.test")).__name__ == "HTTPAdapter"


def test_invalid_manual_source_ip_is_rejected():
    with pytest.raises(ValueError):
        validate_source_ip("127.0.0.1")
    cfg = Config()
    cfg.advanced.bypass_vpn = True
    cfg.advanced.direct_source_ip = "not-an-ip"
    with pytest.raises(ValueError):
        create_session(cfg)


def test_save_network_settings_preserves_other_config(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[advanced]\ntimeout_sec = 9\n\n[probe]\nonline_interval_sec = 77\n', encoding="utf-8")
    save_network_settings(config, True, "172.18.1.20")
    cfg = load_config(config, tmp_path / "credentials.toml")
    assert cfg.advanced.bypass_vpn is True
    assert cfg.advanced.direct_source_ip == "172.18.1.20"
    assert cfg.advanced.timeout_sec == 9
    assert cfg.probe.online_interval_sec == 77


def test_save_network_settings_rejects_invalid_ip(tmp_path):
    with pytest.raises(ValueError):
        save_network_settings(tmp_path / "config.toml", True, "127.0.0.1")
    assert not (tmp_path / "config.toml").exists()
