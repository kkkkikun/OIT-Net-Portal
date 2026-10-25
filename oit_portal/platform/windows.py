"""Windows 平台：Toast 通知（PowerShell 尽力而为，失败静默降级为纯日志）。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..log import get_logger

logger = get_logger()

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "OIT-Portal"


def startup_command(executable: str | None = None) -> str:
    if executable is not None:
        return subprocess.list2cmdline([executable])
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable])
    python = Path(sys.executable)
    pythonw = python.with_name("pythonw.exe")
    interpreter = str(pythonw if pythonw.is_file() else python)
    return subprocess.list2cmdline([interpreter, "-m", "oit_portal.tray"])


def startup_enabled() -> bool:
    if sys.platform != "win32":
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            winreg.QueryValueEx(key, _RUN_VALUE)
        return True
    except FileNotFoundError:
        return False


def set_startup(enabled: bool, executable: str | None = None) -> None:
    if sys.platform != "win32":
        raise OSError("开机自启仅支持 Windows")
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ,
                              startup_command(executable))
        else:
            try:
                winreg.DeleteValue(key, _RUN_VALUE)
            except FileNotFoundError:
                pass


_PS_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$tmpl = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $tmpl.GetElementsByTagName('text')
$texts.Item(0).AppendChild($tmpl.CreateTextNode('{title}')) > $null
$texts.Item(1).AppendChild($tmpl.CreateTextNode('{text}')) > $null
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('oit-portal').Show([Windows.UI.Notifications.ToastNotification]::new($tmpl))
"""


def notify(title: str, text: str) -> None:
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             _PS_TOAST.format(title=title, text=text)],
            check=False, timeout=15,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        logger.info("通知：%s - %s", title, text)
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("Toast 通知失败（降级为日志）：%s", exc)
