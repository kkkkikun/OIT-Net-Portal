"""requests.Session cookie 持久化（会话复用策略的基础）。"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import requests

from ..log import get_logger

logger = get_logger()


def save(session: requests.Session, path: Path) -> None:
    """把 session 中全部 cookie 序列化为 JSON（权限 600）。"""
    jars = [
        {
            "name": c.name,
            "value": c.value,
            "domain": c.domain,
            "path": c.path,
            "expires": c.expires,
        }
        for c in session.cookies
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jars, ensure_ascii=False, indent=1), encoding="utf-8")
    _chmod_600(path)
    logger.info("已持久化 %d 个会话 cookie", len(jars))


def load(session: requests.Session, path: Path) -> int:
    """恢复 cookie（自动跳过已过期的）。返回恢复数量。"""
    if not path.is_file():
        return 0
    try:
        jars = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("session 文件损坏，忽略：%s", exc)
        return 0
    now = time.time()
    count = 0
    for item in jars:
        expires = item.get("expires")
        if expires and expires <= now:
            continue
        session.cookies.set(
            item["name"], item["value"],
            domain=item.get("domain", ""), path=item.get("path", "/"),
        )
        count += 1
    logger.info("从磁盘恢复 %d 个会话 cookie", count)
    return count


def clear(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
        logger.info("已清除持久化会话")
    except OSError as exc:
        logger.warning("清除会话文件失败：%s", exc)


def _chmod_600(path: Path) -> None:
    try:
        os.chmod(path, 0o600)  # Windows 下无效果，靠用户目录 ACL
    except OSError:
        pass
