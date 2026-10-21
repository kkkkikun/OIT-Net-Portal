"""设置页与诊断事件日志的离线源码契约检查。"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE_ROOT = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "oitnetportal"
)
SETTINGS_SOURCE = (APP_SOURCE_ROOT / "core" / "AppSettings.kt").read_text(encoding="utf-8")
VIEW_MODEL_SOURCE = (APP_SOURCE_ROOT / "ui" / "PortalViewModel.kt").read_text(encoding="utf-8")
SCREEN_SOURCE = (APP_SOURCE_ROOT / "ui" / "PortalScreen.kt").read_text(encoding="utf-8")
ACTIVITY_SOURCE = (APP_SOURCE_ROOT / "MainActivity.kt").read_text(encoding="utf-8")


def test_settings_store_holds_only_non_sensitive_switches():
    assert "interface SettingsStore" in SETTINGS_SOURCE
    assert "autoRefreshOnNetworkRecovery" in SETTINGS_SOURCE
    assert "autoRefreshOnForeground" in SETTINGS_SOURCE
    # 设置存储不得涉及凭据字段（先剥离注释，只查代码本体）
    import re
    code_only = re.sub(r"/\*\*.*?\*/", "", SETTINGS_SOURCE, flags=re.DOTALL)
    code_only = re.sub(r"//[^\n]*", "", code_only)
    for marker in ("password", "username", "credential"):
        assert marker not in code_only.lower()
    # 两个开关默认开启
    assert 'getBoolean(KEY_NETWORK_RECOVERY, true)' in SETTINGS_SOURCE
    assert 'getBoolean(KEY_FOREGROUND, true)' in SETTINGS_SOURCE


def test_settings_persistence_is_isolated_in_store_class():
    # Activity / Screen / ViewModel 不得直接触碰偏好 API
    for source in (ACTIVITY_SOURCE, SCREEN_SOURCE, VIEW_MODEL_SOURCE):
        assert "SharedPreferences" not in source
        assert "getSharedPreferences" not in source
    assert "AppSettingsStore(appContext)" in ACTIVITY_SOURCE
    assert "settingsStore = AppSettingsStore" in ACTIVITY_SOURCE


def test_settings_switches_wired_to_viewmodel():
    assert "onToggleNetworkRecovery = viewModel::setAutoRefreshOnNetworkRecovery" in SCREEN_SOURCE
    assert "onToggleForegroundRefresh = viewModel::setAutoRefreshOnForeground" in SCREEN_SOURCE
    assert "state.autoRefreshOnNetworkRecovery" in SCREEN_SOURCE
    assert "state.autoRefreshOnForeground" in SCREEN_SOURCE
    assert "Switch(" in SCREEN_SOURCE


def test_settings_gate_network_and_foreground_refresh():
    network_body = VIEW_MODEL_SOURCE.split(
        "fun onNetworkAvailable()", maxsplit=1)[1].split(
        "fun onAppForeground()", maxsplit=1)[0]
    assert "!_uiState.value.autoRefreshOnNetworkRecovery" in network_body
    foreground_body = VIEW_MODEL_SOURCE.split(
        "fun onAppForeground()", maxsplit=1)[1].split(
        "fun setAutoRefreshOnNetworkRecovery", maxsplit=1)[0]
    assert "!_uiState.value.autoRefreshOnForeground" in foreground_body


def test_diagnostic_events_are_bounded_and_timestamped():
    assert "private const val MAX_EVENTS = 50" in VIEW_MODEL_SOURCE
    assert ".take(MAX_EVENTS)" in VIEW_MODEL_SOURCE
    assert "EVENT_TIME_FORMAT" in VIEW_MODEL_SOURCE
    assert "DateTimeFormatter.ofPattern(\"HH:mm:ss\")" in VIEW_MODEL_SOURCE


def test_diagnostic_events_never_include_credentials():
    for line in VIEW_MODEL_SOURCE.splitlines():
        if "recordEvent(" in line and "private fun recordEvent" not in line:
            lowered = line.lower()
            assert "password" not in lowered
            assert "username" not in lowered


def test_screen_renders_event_list_and_keeps_capture_placeholder():
    assert "state.events.take(MAX_SHOWN_EVENTS)" in SCREEN_SOURCE
    assert "private const val MAX_SHOWN_EVENTS = 10" in SCREEN_SOURCE
    assert 'Text("诊断事件"' in SCREEN_SOURCE
    assert 'Text("协议 Capture（待接入）")' in SCREEN_SOURCE
