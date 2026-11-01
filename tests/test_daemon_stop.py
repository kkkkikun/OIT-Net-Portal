"""`oit-portal stop` 的幂等语义。

背景（2026-11-01，在用户自己的中文 Windows 上实测托盘安装时暴露）：
`scripts/install_windows_tray.ps1` 会先尽力停掉旧 daemon：

    & $Python -m oit_portal.cli stop 2>$null | Out-Null

在一台**从没跑过 daemon** 的新机器上，`stop_daemon` 找不到 pid 文件，
于是按 ERROR 级别打日志并 `return 1`。而 `oit_portal.log` 的控制台
handler 默认写 **stderr**，Windows PowerShell 5.1 在 `$ErrorActionPreference = "Stop"`
下会把原生命令的 stderr 输出当成终止错误 —— **安装脚本在第 2 步就被打断，
托盘根本没启动**。

语义上，「停一个本来就没在跑的东西」应当是**成功**（幂等），
和 `systemctl stop` 对未激活单元返回 0 一致。
"""

from __future__ import annotations

from pathlib import Path

from oit_portal.daemon import stop_daemon
from oit_portal.paths import AppPaths


def _paths(tmp_path: Path) -> AppPaths:
    home = tmp_path / "oit-portal"
    return AppPaths(
        home=home,
        config=home / "config.toml",
        credentials=home / "credentials.toml",
        session=home / "session.json",
        log_dir=home / "logs",
        log_file=home / "logs" / "oit-portal.log",
        lock=tmp_path / "oit-portal.lock",
        pid=tmp_path / "oit-portal.pid",
    )


def test_stop_without_pid_file_is_idempotent_success(tmp_path: Path) -> None:
    """没有 pid 文件 = 没有 daemon 在跑：stop 必须返回 0，不能报错。"""
    paths = _paths(tmp_path)
    assert not paths.pid.exists()

    assert stop_daemon(paths) == 0


def test_stop_with_unreadable_pid_file_is_also_success(tmp_path: Path) -> None:
    """pid 文件存在但内容不是数字，同样按「没有在跑」处理。"""
    paths = _paths(tmp_path)
    paths.pid.write_text("not-a-pid", encoding="ascii")

    assert stop_daemon(paths) == 0


def test_stop_reports_missing_daemon_without_error_level(tmp_path: Path, caplog) -> None:
    """「没有 daemon 在跑」是正常状态，不能用 ERROR 级别打日志。"""
    paths = _paths(tmp_path)

    with caplog.at_level("DEBUG", logger="oit_portal"):
        stop_daemon(paths)

    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert not errors, f"不应产生 ERROR 日志：{[r.getMessage() for r in errors]}"
