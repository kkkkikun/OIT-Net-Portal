from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BINDER = (ROOT / "android/app/src/main/java/com/oitnetportal/core/CampusNetworkBinder.kt").read_text(encoding="utf-8")
BRIDGE = (ROOT / "android/app/src/main/java/com/oitnetportal/core/ChaquopyPortalCoreBridge.kt").read_text(encoding="utf-8")


def test_android_binds_only_wifi_and_never_tears_down_vpn():
    assert "NetworkCapabilities.TRANSPORT_WIFI" in BINDER
    assert "!capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)" in BINDER
    assert "bindProcessToNetwork(wifi)" in BINDER
    assert "bindProcessToNetwork(null)" in BINDER
    assert "finally" in BINDER
    assert "VpnService" not in BINDER
    assert "disconnect" not in BINDER


def test_probe_and_login_both_use_serialized_campus_binding():
    assert BRIDGE.count("campusNetwork.withCampusNetwork") == 2
    assert BRIDGE.count("callCoordinator.withSerializedCall") == 2
    assert "CampusNetworkBinder(context)" in BRIDGE
