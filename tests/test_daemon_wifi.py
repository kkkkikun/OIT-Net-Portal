"""守护进程的 WiFi SSID watcher（Termux / Linux）与单实例锁契约。"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from unittest import mock

import pytest

from oit_portal.config import Config
from oit_portal.daemon import (
    SingleInstanceLock,
    _is_linux,
    _read_current_ssid,
    _ssid_probe_supported,
    _wifi_ssid_watcher,
    run_daemon,
)
from oit_portal.paths import AppPaths

from conftest import make_config


# ── _read_current_ssid ──────────────────────────────────────


def test_read_ssid_returns_none_on_unsupported_platform(monkeypatch):
    """不支持的平台（如 darwin，无 TERMUX env）→ 返回 None，且不调用任何命令。"""
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.delenv("PREFIX", raising=False)
    monkeypatch.setattr("sys.platform", "darwin")
    with mock.patch("oit_portal.daemon.subprocess.run") as fake_run:
        assert _read_current_ssid() is None
        fake_run.assert_not_called()


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


# ── _read_current_ssid：Linux 分支（nmcli → iwgetid）────────


def _as_linux(monkeypatch):
    """构造纯 Linux 环境：清 Termux env、强制 sys.platform。"""
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.delenv("PREFIX", raising=False)
    monkeypatch.setattr("sys.platform", "linux")


def test_read_ssid_linux_nmcli_success(monkeypatch):
    """nmcli 输出 yes:SSID 行 → 取活动 SSID。"""
    _as_linux(monkeypatch)
    fake_out = mock.Mock(returncode=0, stdout="no:home-wifi\nyes:eduroam\n")
    with mock.patch("oit_portal.daemon.subprocess.run", return_value=fake_out) as fake_run:
        assert _read_current_ssid() == "eduroam"
        assert fake_run.call_args[0][0] == \
            ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"]


def test_read_ssid_linux_nmcli_ssid_with_colon(monkeypatch):
    """SSID 含冒号时只切第一个冒号（partition），剩余原样保留。"""
    _as_linux(monkeypatch)
    fake_out = mock.Mock(returncode=0, stdout="yes:my:net\n")
    with mock.patch("oit_portal.daemon.subprocess.run", return_value=fake_out):
        assert _read_current_ssid() == "my:net"


def test_read_ssid_linux_iwgetid_fallback(monkeypatch):
    """nmcli 不存在（未装 NetworkManager）→ 兜底 iwgetid。"""
    _as_linux(monkeypatch)
    fake_out = mock.Mock(returncode=0, stdout="eduroam\n")
    with mock.patch("oit_portal.daemon.subprocess.run",
                    side_effect=[FileNotFoundError, fake_out]) as fake_run:
        assert _read_current_ssid() == "eduroam"
        assert fake_run.call_args_list[1][0][0] == ["iwgetid", "-r"]


def test_read_ssid_linux_no_active_ssid(monkeypatch):
    """nmcli 无活动连接且 iwgetid 为空 → None。"""
    _as_linux(monkeypatch)
    nmcli_out = mock.Mock(returncode=0, stdout="no:home-wifi\nno:other\n")
    iw_out = mock.Mock(returncode=0, stdout="")
    with mock.patch("oit_portal.daemon.subprocess.run",
                    side_effect=[nmcli_out, iw_out]):
        assert _read_current_ssid() is None


def test_read_ssid_linux_commands_missing(monkeypatch):
    """nmcli / iwgetid 都不存在 → None，不抛异常。"""
    _as_linux(monkeypatch)
    with mock.patch("oit_portal.daemon.subprocess.run",
                    side_effect=[FileNotFoundError, FileNotFoundError]):
        assert _read_current_ssid() is None


def test_read_ssid_linux_nmcli_timeout_falls_through(monkeypatch):
    """nmcli 卡住超时 → 不短路，继续尝试 iwgetid。"""
    _as_linux(monkeypatch)
    iw_out = mock.Mock(returncode=0, stdout="eduroam\n")
    with mock.patch("oit_portal.daemon.subprocess.run",
                    side_effect=[subprocess.TimeoutExpired("nmcli", 2.0), iw_out]):
        assert _read_current_ssid() == "eduroam"


def test_read_ssid_termux_env_does_not_enter_linux_branch(monkeypatch):
    """Termux 的 sys.platform 也是 linux，必须优先判 Termux 且不调 nmcli。"""
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    monkeypatch.setattr("sys.platform", "linux")
    fake_out = mock.Mock(returncode=0,
                         stdout=json.dumps({"ssid": "eduroam"}))
    with mock.patch("oit_portal.daemon.subprocess.run", return_value=fake_out) as fake_run:
        assert _read_current_ssid() == "eduroam"
        assert fake_run.call_count == 1
        assert fake_run.call_args[0][0] == ["termux-wifi-connectioninfo"]


# ── _ssid_probe_supported / _is_linux ───────────────────────


def test_ssid_probe_supported_linux(monkeypatch):
    _as_linux(monkeypatch)
    assert _is_linux() is True
    assert _ssid_probe_supported() is True


def test_ssid_probe_supported_termux_env_on_linux(monkeypatch):
    """Termux 的 Python sys.platform 也是 linux——env 优先，不算纯 Linux。"""
    monkeypatch.setenv("TERMUX_VERSION", "0.118")
    monkeypatch.setattr("sys.platform", "linux")
    assert _is_linux() is False
    assert _ssid_probe_supported() is True  # Termux 自身支持


def test_ssid_probe_unsupported_platform(monkeypatch):
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.delenv("PREFIX", raising=False)
    monkeypatch.setattr("sys.platform", "darwin")
    assert _is_linux() is False
    assert _ssid_probe_supported() is False


# ── run_daemon 单实例锁契约 ─────────────────────────────────


def test_run_daemon_lock_conflict_returns_zero(tmp_path):
    """锁冲突返回 0 而非 1：systemd Restart=on-failure 下退出码 1 会被
    当崩溃无限重启；「已有实例在跑」对服务管理器而言目标已达成。"""
    paths = AppPaths(
        home=tmp_path,
        config=tmp_path / "config.toml",
        credentials=tmp_path / "credentials.toml",
        session=tmp_path / "session.json",
        log_dir=tmp_path / "logs",
        log_file=tmp_path / "logs" / "oit-portal.log",
        lock=tmp_path / "oit-portal.lock",
        pid=tmp_path / "oit-portal.pid",
    )
    first = SingleInstanceLock(paths.lock)
    assert first.acquire()
    try:
        assert run_daemon(make_config(tmp_path), paths) == 0
    finally:
        first.release()


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
