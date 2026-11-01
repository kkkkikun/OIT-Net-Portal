"""Static contracts for the 2026-10-31 Android follow-up work.

Covers three fixes: the P1 service-restore gap, the P2 notification-visibility
warning, and the Material3 surface-container palette mismatch. Also pins the
debug-only VPN harness so it can never leak into the release variant.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANDROID = ROOT / "android" / "app" / "src"
JAVA = ANDROID / "main" / "java" / "com" / "oitnetportal"
DEBUG = ANDROID / "debug"
MAIN_MANIFEST = (ANDROID / "main" / "AndroidManifest.xml").read_text(encoding="utf-8")


def read(relative: str) -> str:
    path = JAVA / relative
    return path.read_text(encoding="utf-8") if path.exists() else ""


def test_p1_restore_uses_process_local_liveness_marker():
    runtime = read("core/BackgroundServiceRuntime.kt")
    service = read("service/PortalForegroundService.kt")
    viewmodel = read("ui/PortalViewModel.kt")

    # 进程内存活标记：进程被杀即清空，用来区分"服务真的在跑"和"状态文本是陈旧的"
    assert "object BackgroundServiceRuntime" in runtime
    assert "fun markRunning()" in runtime
    assert "fun markStopped()" in runtime
    assert "fun isRunning(): Boolean" in runtime
    # 标记只能存在内存里：整个对象不碰任何 Android 持久化设施
    assert "import android" not in runtime
    assert "getSharedPreferences" not in runtime

    assert "BackgroundServiceRuntime.markRunning()" in service
    assert "BackgroundServiceRuntime.markStopped()" in service


def test_p1_relaunch_restarts_service_and_clears_stale_detail():
    viewmodel = read("ui/PortalViewModel.kt")
    assert "restoreBackgroundReconnectIfNeeded" in viewmodel
    assert "BackgroundServiceRuntime.isRunning()" in viewmodel
    # 恢复前必须先把陈旧状态纠正掉，不能继续显示"后台巡检中"
    assert "后台服务已停止，正在重新启动" in viewmodel
    # 只在开关确实是开的时候才恢复
    assert "if (!store.snapshots.value.enabled) return" in viewmodel


def test_p2_notification_visibility_is_checked_on_three_layers():
    provider = read("core/AndroidNotificationStatusProvider.kt")
    interface = read("core/NotificationStatusProvider.kt")
    assert "interface NotificationStatusProvider" in interface
    assert "areNotificationsEnabled(): Boolean" in interface

    assert "NotificationManagerCompat" in provider
    assert "areNotificationsEnabled()" in provider
    assert "POST_NOTIFICATIONS" in provider
    assert "OP_POST_NOTIFICATION" in provider
    # AppOps 常量未在公开 SDK 暴露，只能按名字解析，不能硬编码编号
    assert "OP_POST_NOTIFICATION = \"POST_NOTIFICATION\"" in provider


def test_p2_warning_card_links_to_system_notification_settings():
    screen = read("ui/PortalScreen.kt")
    assert "system notification" not in screen.lower()
    assert "ACTION_APP_NOTIFICATION_SETTINGS" in screen
    assert "EXTRA_APP_PACKAGE" in screen
    assert "state.notificationsEnabled" in screen
    assert "系统通知已被关闭" in screen


def test_material3_surface_container_roles_are_defined():
    theme = read("ui/OitPortalTheme.kt")
    # Material3 1.2+ 的 Card 默认取 surfaceContainer*；不显式定义会回落成 M3 基线紫调灰
    for role in (
        "surfaceContainerLowest",
        "surfaceContainerLow",
        "surfaceContainerHigh",
        "surfaceContainerHighest",
        "surfaceBright",
        "surfaceDim",
        "surfaceTint",
    ):
        assert role in theme, role
    # 卡片颜色由应用自己定，不依赖库版本的默认角色
    screen = read("ui/PortalScreen.kt")
    form = read("ui/PortalCredentialForm.kt")
    assert "containerColor = MaterialTheme.colorScheme.surface" in screen
    assert "containerColor = MaterialTheme.colorScheme.surface" in form


def test_debug_only_vpn_harness_never_reaches_the_release_variant():
    assert (DEBUG / "AndroidManifest.xml").exists()
    assert (DEBUG / "java" / "com" / "oitnetportal" / "debug").exists()
    # release 变体的清单里不能出现调试用的 VPN 服务与广播接收器
    assert "BlackholeVpnService" not in MAIN_MANIFEST
    assert "DebugVpnControlReceiver" not in MAIN_MANIFEST
    # 主清单里也不能有：调试组件只能待在 src/debug
    assert "android.net.VpnService" not in MAIN_MANIFEST
