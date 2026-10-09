"""Windows 平台：Toast 通知（PowerShell 尽力而为，失败静默降级为纯日志）。"""

from __future__ import annotations

import subprocess

from ..log import get_logger

logger = get_logger()

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
