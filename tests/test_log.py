"""日志：文件不可写时退化到仅控制台；指纹脱敏。"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from oit_portal.log import fingerprint, setup_logging


@pytest.fixture(autouse=True)
def _reset_logger():
    """每个测试都重置全局 logger，避免 handler 累积。"""
    logger = logging.getLogger("oit_portal")
    logger.handlers.clear()
    yield
    logger.handlers.clear()


def test_setup_logging_falls_back_when_file_unwritable(tmp_path, monkeypatch, capsys):
    """主 + 备路径都不可写时（极端异常）→ 不崩，只输出到终端。"""
    import tempfile
    # 强制让 tempfile.gettempdir() 返回一个不可写位置
    blocker2 = tmp_path / "tmpdir_blocker"
    blocker2.write_text("not a directory")
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(blocker2))

    # 主路径不可写（parent 是文件，mkdir 会失败）
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    bad_log = blocker / "oit-portal.log"

    # 不应抛异常——两级 OSError 内部捕获
    setup_logging(bad_log, console=False)

    captured = capsys.readouterr()
    assert "日志文件不可写" in captured.err
    assert str(bad_log) in captured.err


def test_setup_logging_two_level_fallback(tmp_path, monkeypatch, capsys):
    """主路径不可写 → 退化到 $TMPDIR（即使控制台关掉也能用日志文件）。"""
    import tempfile
    tmpdir = tmp_path / "tmpdir"
    tmpdir.mkdir()
    # 直接 monkey-patch tempfile.gettempdir（避免 Python 缓存导致 setenv 失效）
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmpdir))

    # 主路径不可写（parent 是文件，mkdir 会失败）
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    bad_log = blocker / "oit-portal.log"

    setup_logging(bad_log, console=False)

    # 退化到 $TMPDIR/oit-portal/oit-portal.log
    fallback = tmpdir / "oit-portal" / "oit-portal.log"
    captured = capsys.readouterr()
    assert "改写到" in captured.err
    assert str(fallback) in captured.err

    # 文件被实际创建
    logger = logging.getLogger("oit_portal")
    logger.info("fallback works")
    assert fallback.exists()
    assert "fallback works" in fallback.read_text(encoding="utf-8")


def test_setup_logging_normal_case_creates_file(tmp_path):
    """正常情况：log_file 可写时创建 RotatingFileHandler。"""
    log_file = tmp_path / "subdir" / "test.log"
    setup_logging(log_file, console=False)

    logger = logging.getLogger("oit_portal")
    logger.info("hello world")

    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert "hello world" in content
    assert "INFO" in content


def test_setup_logging_idempotent(tmp_path):
    """重复调用不会叠加 handler（避免 daemon 启动时日志被复制 N 份）。"""
    log_file = tmp_path / "test.log"
    setup_logging(log_file, console=False)
    setup_logging(log_file, console=False)
    setup_logging(log_file, console=False)

    logger = logging.getLogger("oit_portal")
    # 只应该有一个 file handler（第一个 setup 添加的）
    file_handlers = [h for h in logger.handlers
                     if "RotatingFileHandler" in type(h).__name__]
    assert len(file_handlers) == 1


def test_fingerprint_masks_value():
    assert fingerprint("supersecret") == "supe***(11ch)"
    assert fingerprint("") == "<empty>"
    assert fingerprint(None) == "<empty>"
    # 短字符串也安全（不暴露原文）
    assert fingerprint("ab") == "ab***(2ch)"
