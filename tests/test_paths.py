"""路径解析：跨平台路径、便携模式、Termux 状态目录修复。"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from oit_portal.paths import resolve_paths, is_termux


def test_termux_uses_home_logs_not_xdg_state(monkeypatch, tmp_path):
    """Termux 状态目录修复：必须用 ~/.config/oit-portal/logs/，不能用 ~/.local/state/。

    部分 Termux 环境 `~/.local/` 在 pkg/python 安装后权限受限，
    导致 PermissionError 让 daemon/wizard 直接崩。集中目录规避此坑。
    """
    home = tmp_path / ".config" / "oit-portal"
    monkeypatch.setenv("OIT_PORTAL_HOME", str(home))
    monkeypatch.setenv("TERMUX_VERSION", "0.118")  # 触发 is_termux() == True
    # 即便用户显式设置 XDG_STATE_HOME 也要忽略（按"集中放"的设计）
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / ".local" / "state"))

    paths = resolve_paths()

    assert paths.log_dir == home / "logs"
    assert paths.log_file == home / "logs" / "oit-portal.log"
    # 不能误落到 XDG_STATE_HOME 默认路径
    assert ".local" not in str(paths.log_dir)


def test_non_termux_uses_home_logs(monkeypatch, tmp_path):
    """非 Termux 平台：日志同样在 home/logs/。"""
    home = tmp_path / "oit-portal-home"
    monkeypatch.setenv("OIT_PORTAL_HOME", str(home))
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.delenv("PREFIX", raising=False)

    paths = resolve_paths()

    assert paths.log_dir == home / "logs"
    assert paths.log_file == home / "logs" / "oit-portal.log"
    assert paths.config == home / "config.toml"
    assert paths.credentials == home / "credentials.toml"
    assert paths.session == home / "session.json"
