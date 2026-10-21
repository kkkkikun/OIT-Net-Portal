"""Android 网络监听与状态恢复的离线源码契约检查。

只验证关键结构存在/不存在，不能证明 Kotlin 可编译，也不替代真机验收。
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAIN_ACTIVITY_PATH = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" /
    "com" / "oitnetportal" / "MainActivity.kt"
)
VIEW_MODEL_PATH = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" /
    "com" / "oitnetportal" / "ui" / "PortalViewModel.kt"
)
MANIFEST_PATH = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
)
MAIN_ACTIVITY_SOURCE = MAIN_ACTIVITY_PATH.read_text(encoding="utf-8")
VIEW_MODEL_SOURCE = VIEW_MODEL_PATH.read_text(encoding="utf-8")
MANIFEST_SOURCE = MANIFEST_PATH.read_text(encoding="utf-8")


def _network_available_body() -> str:
    return VIEW_MODEL_SOURCE.split(
        "fun onNetworkAvailable()", maxsplit=1)[1].split(
        "fun onAppForeground()", maxsplit=1)[0]


def _network_lost_body() -> str:
    return VIEW_MODEL_SOURCE.split(
        "fun onNetworkLost()", maxsplit=1)[1].split(
        "fun onNetworkAvailable()", maxsplit=1)[0]


def _foreground_body() -> str:
    return VIEW_MODEL_SOURCE.split(
        "fun onAppForeground()", maxsplit=1)[1].split(
        "private fun runOperation", maxsplit=1)[0]


def test_manifest_declares_network_state_permission():
    assert "android.permission.ACCESS_NETWORK_STATE" in MANIFEST_SOURCE


def test_activity_registers_and_unregisters_default_network_callback():
    assert "registerDefaultNetworkCallback" in MAIN_ACTIVITY_SOURCE
    assert "unregisterNetworkCallback(callback)" in MAIN_ACTIVITY_SOURCE
    destroy_body = MAIN_ACTIVITY_SOURCE.split("override fun onDestroy()", maxsplit=1)[1]
    assert "unregisterNetworkCallback()" in destroy_body


def test_activity_registration_is_idempotent_and_not_repeated_on_resume():
    assert "if (networkCallback != null) return" in MAIN_ACTIVITY_SOURCE
    on_resume = MAIN_ACTIVITY_SOURCE.split("override fun onResume()", maxsplit=1)[1].split(
        "override fun onDestroy()", maxsplit=1)[0]
    assert "registerNetworkCallback" not in on_resume
    assert "onAppForeground()" in on_resume


def test_activity_callback_only_forwards_events_never_submits_credentials():
    forbidden = (
        "loginWithCredentials",
        "loginOnce",
        "create(appContext",
        "password",
    )
    callback_body = MAIN_ACTIVITY_SOURCE.split(
        "private fun registerNetworkCallback()", maxsplit=1)[1]
    for marker in forbidden:
        assert marker not in callback_body
    assert "onNetworkAvailable()" in callback_body
    assert "onNetworkLost()" in callback_body
    assert "NET_CAPABILITY_VALIDATED" in callback_body


def test_network_recovery_is_bounded_and_probe_only():
    body = _network_available_body()
    assert "NETWORK_RECOVERY_MAX_ATTEMPTS" in body
    assert "NETWORK_RECOVERY_DELAY_MS" in body
    assert "core.probe()" in body
    assert "while (true)" not in body
    # 网络恢复路径绝不提交凭据或自动登录
    assert "bridgeFactory" not in body
    assert "loginOnce" not in body
    assert "factory(" not in body


def test_network_events_skip_when_session_ended():
    body = _network_available_body()
    assert "!_uiState.value.coreAvailable" in body
    foreground = _foreground_body()
    assert "!_uiState.value.coreAvailable" in foreground
    assert "refresh()" in foreground


def test_network_lost_marks_offline_without_probing():
    body = _network_lost_body()
    assert "PortalStatus.OFFLINE" in body
    assert "core.probe()" not in body
    assert "runOperation" not in body


def test_network_constants_have_finite_bounds():
    assert "private const val NETWORK_RECOVERY_MAX_ATTEMPTS = 3" in VIEW_MODEL_SOURCE
    assert "private const val NETWORK_RECOVERY_DELAY_MS = 2000L" in VIEW_MODEL_SOURCE
