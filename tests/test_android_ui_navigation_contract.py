"""Android UI redesign navigation and visual contract checks."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" /
    "com" / "oitnetportal" / "ui"
)
SCREEN = (UI_ROOT / "PortalScreen.kt").read_text(encoding="utf-8")
THEME = (UI_ROOT / "OitPortalTheme.kt").read_text(encoding="utf-8")


def test_primary_navigation_has_three_clear_destinations():
    assert 'CONNECT("连接"' in SCREEN
    assert 'SETTINGS("设置"' in SCREEN
    assert 'DIAGNOSTICS("诊断"' in SCREEN
    assert "NavigationBar(" in SCREEN
    assert "NavigationBarItem(" in SCREEN


def test_connection_screen_prioritizes_status_feedback_and_login():
    assert "StatusCard(state)" in SCREEN
    assert "state.notice?.let" in SCREEN
    assert "PortalCredentialForm(" in SCREEN
    assert 'Text("重试登录")' in SCREEN
    assert 'Text("刷新状态")' in SCREEN


def test_all_portal_states_have_explicit_labels_and_colors():
    for status in ("UNKNOWN", "ONLINE", "CAPTIVE", "OFFLINE"):
        assert f"PortalStatus.{status} ->" in SCREEN
    for label in ("校园网已连接", "需要认证", "当前离线", "尚未确认"):
        assert label in SCREEN


def test_settings_offer_background_reconnect_but_capture_remains_disabled():
    assert 'SettingSwitchRow("后台自动重连"' in SCREEN
    assert "state.backgroundReconnectDetail" in SCREEN
    assert 'Text("协议 Capture（待接入）")' in SCREEN
    assert "enabled = false" in SCREEN


def test_diagnostics_only_displays_the_bounded_event_window():
    assert "private const val MAX_SHOWN_EVENTS = 10" in SCREEN
    assert "state.events.take(MAX_SHOWN_EVENTS)" in SCREEN
    assert "日志只用于当前会话排障" in SCREEN


def test_theme_uses_a_coherent_light_palette_and_rounded_shapes():
    assert "lightColorScheme(" in THEME
    assert "Color(0xFF2457C5)" in THEME
    assert "Color(0xFFF5F7FB)" in THEME
    assert "RoundedCornerShape(24.dp)" in THEME
