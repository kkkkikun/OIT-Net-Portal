"""日志：轮转文件 + 可选控制台；永不记录明文密码与完整 cookie。"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

LOGGER_NAME = "oit_portal"
_FMT = "%(asctime)s %(levelname)-7s %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def fingerprint(secret: str | None) -> str:
    """敏感值只记前 4 位指纹。"""
    if not secret:
        return "<empty>"
    return f"{secret[:4]}***({len(secret)}ch)"


def setup_logging(log_file: Path | None, *, console: bool = True) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:  # 已初始化（如测试重复调用）
        return logger

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(logging.Formatter(_FMT, _DATEFMT))
        logger.addHandler(fh)
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(_FMT, _DATEFMT))
        logger.addHandler(ch)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
