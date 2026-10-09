"""日志：轮转文件 + 可选控制台；永不记录明文密码与完整 cookie。"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import tempfile
from pathlib import Path

LOGGER_NAME = "oit_portal"
_FMT = "%(asctime)s %(levelname)-7s %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def fingerprint(secret: str | None) -> str:
    """敏感值只记前 4 位指纹。"""
    if not secret:
        return "<empty>"
    return f"{secret[:4]}***({len(secret)}ch)"


def _try_attach_file_handler(logger: logging.Logger, path: Path) -> bool:
    """尝试挂载 RotatingFileHandler。成功 True；OSError 任何阶段 False。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FMT, _DATEFMT))
        logger.addHandler(fh)
        return True
    except OSError:
        return False


def setup_logging(log_file: Path | None, *, console: bool = True) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if logger.handlers:  # 已初始化（如测试重复调用）
        return logger

    if log_file is not None:
        if not _try_attach_file_handler(logger, log_file):
            # Termux 等环境下 home 目录可能不可写 → 退化到 $TMPDIR
            fallback = Path(tempfile.gettempdir()) / "oit-portal" / log_file.name
            if not _try_attach_file_handler(logger, fallback):
                print(f"⚠ 日志文件不可写 {log_file} / {fallback}，仅输出到终端",
                      file=sys.stderr)
            else:
                print(f"⚠ 日志文件 {log_file} 不可写，改写到 {fallback}",
                      file=sys.stderr)
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter(_FMT, _DATEFMT))
        logger.addHandler(ch)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
