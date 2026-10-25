"""Static contracts for Android background auto-reconnect."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "oitnetportal"
MANIFEST = (ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml").read_text()


def read(relative: str) -> str:
    path = JAVA / relative
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_background_state_defaults_off_and_persists_only_fixed_state():
    store = read("core/BackgroundReconnectStateStore.kt")
    settings = read("core/AppSettings.kt")
    assert "backgroundAutoReconnectEnabled" in settings
    assert "getBoolean(KEY_ENABLED, false)" in store
    for status in ("STOPPED", "STARTING", "MONITORING", "BACKOFF", "NEEDS_ATTENTION"):
        assert status in store
    for forbidden in ("putString(KEY_PASSWORD", "putString(KEY_COOKIE", "putString(KEY_TOKEN"):
        assert forbidden not in store


def test_foreground_service_has_notification_stop_and_network_lifecycle():
    service = read("service/PortalForegroundService.kt")
    assert "startForeground(" in service
    assert "ACTION_STOP" in service
    assert "ACTION_ACCOUNTS_CHANGED" in service
    assert "START_STICKY" in service
    assert "registerDefaultNetworkCallback" in service
    assert "unregisterNetworkCallback" in service
    assert "PendingIntent.getService" in service
    assert "ATTENTION_NOTIFICATION_ID" in service


def test_stale_stop_cannot_destroy_a_newer_start_command():
    service = read("service/PortalForegroundService.kt")
    assert "stopSelfResult(startId)" in service
    assert "stopSelf()" not in service
    assert "if (stateStore.enabled) return" in service
    assert "controller?.isRunning != true" in service
    assert "destructionPending" in service


def test_python_calls_are_serialized_across_bridge_instances():
    bridge = read("core/ChaquopyPortalCoreBridge.kt")
    assert "PortalCoreCallCoordinator" in bridge
    assert bridge.count("callCoordinator.withSerializedCall") == 2


def test_settings_ui_enables_real_background_reconnect_but_not_capture_or_boot():
    screen = read("ui/PortalScreen.kt")
    app = read("ui/PortalScreen.kt")
    assert 'SettingSwitchRow("后台自动重连"' in screen
    assert "state.backgroundAutoReconnectEnabled" in screen
    assert "state.backgroundReconnectDetail" in screen
    assert "自动重连服务尚未接入" not in screen
    assert 'Text("协议 Capture（待接入）")' in screen
    assert "enabled = false" in screen
    assert "POST_NOTIFICATIONS" in app
    assert "onBackgroundNotificationPermissionResult" in app
    assert "BOOT_COMPLETED" not in MANIFEST
    assert 'android:foregroundServiceType="specialUse"' in MANIFEST


def test_viewmodel_coordinates_background_lifecycle_without_raw_secrets():
    viewmodel = read("ui/PortalViewModel.kt")
    assert "setBackgroundAutoReconnect" in viewmodel
    assert "onBackgroundNotificationPermissionResult" in viewmodel
    assert "backgroundLauncher?.stop()" in viewmodel
    assert "backgroundLauncher?.accountsChanged()" in viewmodel
    assert "backgroundLauncher?.attention(" in viewmodel
    assert "账号已删除，请检查后台自动重连" in viewmodel
