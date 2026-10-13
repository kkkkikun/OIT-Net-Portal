"""守护进程的 WiFi SSID watcher（Termux 专用）。"""

from __future__ import annotations

import json
import threading
import time
from unittest import mock

import pytest

from oit_portal.config import Config
from oit_portal.daemon import _read_current_ssid, _wifi_ssid_watcher

from conftest import make_config


# ── _read_current_ssid ──────────────────────────────────────


def test_read_ssid_returns_none_outside_termux(monkeypatch):
    """非 Termux 环境（无 TERMUX_VERSION env）→ 返回 None，feature gate 关闭。"""
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.delenv("PREFIX", raising=False)
    assert _read_current_ssid() is None


def test_read_ssid_parses_termux_output(monkeypatch):
    """Termux 下 termux-wifi-connectioninfo 输出 JSON，提取 ssid 字段。"""
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    fake_out = mock.Mock(returncode=0, stdout=json.dumps({"ssid": "eduroam"}))
    with mock.patch("oit_portal.daemon.subprocess.run", return_value=fake_out):
        assert _read_current_ssid() == "eduroam"


def test_read_ssid_handles_command_missing(monkeypatch):
    """未装 termux-api → subprocess 抛 FileNotFoundError → 返回 None。"""
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    with mock.patch("oit_portal.daemon.subprocess.run",
                    side_effect=FileNotFoundError):
        assert _read_current_ssid() is None


def test_read_ssid_handles_timeout(monkeypatch):
    """termux-api 卡住 → TimeoutExpired → 返回 None。"""
    import subprocess
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    with mock.patch("oit_portal.daemon.subprocess.run",
                    side_effect=subprocess.TimeoutExpired("termux-wifi-connectioninfo", 2.0)):
        assert _read_current_ssid() is None


# ── _wifi_ssid_watcher ──────────────────────────────────────


def test_watcher_signals_event_on_ssid_match(monkeypatch):
    """SSID 匹配配置时触发 on_campus_connected.set()。"""
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    cfg = make_config(probe={"wifi_ssid": "eduroam"})

    stop = threading.Event()
    on_campus = threading.Event()

    # 第一次返回 target SSID，第二次返回其他 SSID
    outputs = [
        mock.Mock(returncode=0, stdout=json.dumps({"ssid": "eduroam"})),
        mock.Mock(returncode=0, stdout=json.dumps({"ssid": "other-wifi"})),
    ]
    with mock.patch("oit_portal.daemon.subprocess.run", side_effect=outputs):
        watcher = threading.Thread(
            target=_wifi_ssid_watcher, args=(cfg, stop, on_campus), daemon=True)
        watcher.start()
        # 等触发
        assert on_campus.wait(timeout=2.0)
        # 让 watcher 跑两轮然后停
        time.sleep(0.1)
        stop.set()
        watcher.join(timeout=2.0)


def test_watcher_skipped_when_ssid_not_configured(monkeypatch):
    """wifi_ssid 为空字符串 → watcher 直接 return（不开线程，no-op）。"""
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    cfg = make_config(probe={"wifi_ssid": ""})

    stop = threading.Event()
    on_campus = threading.Event()
    with mock.patch("oit_portal.daemon.subprocess.run") as fake_run:
        _wifi_ssid_watcher(cfg, stop, on_campus)
        # 不应调用 subprocess.run
        assert fake_run.call_count == 0
        assert not on_campus.is_set()
