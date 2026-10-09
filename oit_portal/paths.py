"""跨平台路径解析。

优先级：环境变量 OIT_PORTAL_HOME > 便携模式（可执行文件/源码根目录存在 config.toml）
> 平台默认（Windows %APPDATA%\\oit-portal，其余 ~/.config/oit-portal）。
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "oit-portal"


def is_termux() -> bool:
    """是否运行在 Termux 环境。"""
    return "TERMUX_VERSION" in os.environ or "com.termux" in os.environ.get("PREFIX", "")


def _default_home() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / "AppData" / "Roaming" / APP_NAME
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / APP_NAME


def _portable_home() -> Path | None:
    """便携模式：exe 或源码根目录与 config.toml 同目录。"""
    candidates: list[Path] = [Path(sys.executable).resolve().parent]
    if not getattr(sys, "frozen", False):
        candidates.append(Path(__file__).resolve().parent.parent)
    for d in candidates:
        if (d / "config.toml").is_file():
            return d
    return None


def _tmp_dir() -> Path:
    # Termux 下 tempfile.gettempdir() 指向 $PREFIX/tmp（应用私有），Windows 指向 %TEMP%
    return Path(tempfile.gettempdir())


@dataclass(frozen=True)
class AppPaths:
    home: Path
    config: Path
    credentials: Path
    session: Path
    log_dir: Path
    log_file: Path
    lock: Path
    pid: Path


def resolve_paths() -> AppPaths:
    env = os.environ.get("OIT_PORTAL_HOME")
    home = Path(env).expanduser() if env else (_portable_home() or _default_home())
    if is_termux():
        # Termux：配置在 ~/.config，状态（日志）遵循 XDG_STATE
        state = Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state"))) / APP_NAME
    else:
        state = home / "logs"
    return AppPaths(
        home=home,
        config=home / "config.toml",
        credentials=home / "credentials.toml",
        session=home / "session.json",
        log_dir=state,
        log_file=state / "oit-portal.log",
        lock=_tmp_dir() / "oit-portal.lock",
        pid=_tmp_dir() / "oit-portal.pid",
    )
