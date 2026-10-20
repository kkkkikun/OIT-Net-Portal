"""Chaquopy Kotlin 桥接 shutdown 契约的离线源码检查。"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_SOURCE = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" /
    "com" / "oitnetportal" / "core" / "ChaquopyPortalCoreBridge.kt"
).read_text(encoding="utf-8")
SHUTDOWN_BODY = BRIDGE_SOURCE.split("suspend fun shutdown()", maxsplit=1)[1].split(
    "private fun PyObject.stringValue", maxsplit=1)[0]


def test_shutdown_is_serialized_on_io_and_idempotent():
    assert "withContext(Dispatchers.IO)" in SHUTDOWN_BODY
    assert "pythonMutex.withLock" in SHUTDOWN_BODY
    assert "if (closed) return@withLock" in SHUTDOWN_BODY
    assert "closed = true" in SHUTDOWN_BODY


def test_shutdown_invokes_python_close_before_releasing_bridge():
    python_close = 'callAttr("close")'
    java_release = "bridge.close()"
    assert python_close in SHUTDOWN_BODY
    assert java_release in SHUTDOWN_BODY
    assert SHUTDOWN_BODY.index(python_close) < SHUTDOWN_BODY.index(java_release)
    assert "bridge?.close()" not in SHUTDOWN_BODY


def test_shutdown_releases_python_none_result_and_bridge_in_finally():
    assert "PyObject?" in SHUTDOWN_BODY
    assert "closeResult?.close()" in SHUTDOWN_BODY
    assert "finally" in SHUTDOWN_BODY
    assert "pythonBridge = null" in SHUTDOWN_BODY
