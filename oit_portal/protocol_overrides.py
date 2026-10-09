"""protocol.json 覆盖机制。

capture 向导自动发现协议后写 <home>/protocol.json，adapter 初始化时合并进
CAPTURED 常量块——实现「向导跑一次，工具自配置」，无需手改代码。
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from .log import get_logger
from .paths import resolve_paths

logger = get_logger()


def override_path() -> Path:
    return resolve_paths().home / "protocol.json"


def apply_overrides(namespace: SimpleNamespace, section: str,
                    path: Path | None = None) -> list[str]:
    """把 protocol.json 的 [section] 合并进 CAPTURED 命名空间（仅接受已有属性）。

    返回实际覆盖的键名列表；文件不存在/损坏时静默跳过。
    """
    p = path or override_path()
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("protocol.json 解析失败（忽略）：%s", exc)
        return []
    section_data = data.get(section)
    if not isinstance(section_data, dict):
        return []
    applied = []
    for key, value in section_data.items():
        if hasattr(namespace, key):
            setattr(namespace, key, value)
            applied.append(key)
        else:
            logger.warning("protocol.json 忽略未知键 %s.%s", section, key)
    if applied:
        logger.info("已应用协议覆盖 %s.%s", section, ",".join(applied))
    return applied
