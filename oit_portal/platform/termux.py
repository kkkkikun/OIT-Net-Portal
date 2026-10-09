"""Termux 平台：wake-lock 与通知（依赖 termux-tools / termux-api，缺失时静默跳过）。"""

from __future__ import annotations

import shutil
import subprocess

from ..log import get_logger

logger = get_logger()


def _run(cmd: list[str]) -> bool:
    exe = shutil.which(cmd[0])
    if not exe:
        logger.debug("%s 不可用，跳过", cmd[0])
        return False
    try:
        subprocess.run([exe, *cmd[1:]], check=False, timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("%s 执行失败：%s", cmd[0], exc)
        return False


def wake_lock() -> None:
    """持有 CPU 唤醒锁，避免锁屏后 daemon 被冻结。"""
    if _run(["termux-wake-lock"]):
        logger.info("已持有 Termux wake-lock")


def wake_unlock() -> None:
    _run(["termux-wake-unlock"])


def notify(title: str, text: str) -> None:
    """需要 Termux:API 才可用；未安装则降级为纯日志。"""
    if _run(["termux-notification", "--title", title, "--content", text]):
        logger.info("通知：%s - %s", title, text)
