"""Android Network Security Config 的离线 XML 契约检查。"""

from pathlib import Path
import xml.etree.ElementTree as ET


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_MAIN = PROJECT_ROOT / "android" / "app" / "src" / "main"
MANIFEST_PATH = APP_MAIN / "AndroidManifest.xml"
SECURITY_CONFIG_PATH = APP_MAIN / "res" / "xml" / "network_security_config.xml"
ANDROID_NS = "{http://schemas.android.com/apk/res/android}"
EXPECTED_CLEARTEXT_HOSTS = {
    "connect.rom.miui.com",
    "captive.apple.com",
    "www.qualcomm.cn",
    "open.oit.edu.cn",
    "172.16.11.54",
}


def _security_root():
    return ET.parse(SECURITY_CONFIG_PATH).getroot()


def test_manifest_references_existing_security_config_without_global_cleartext():
    manifest = ET.parse(MANIFEST_PATH).getroot()
    application = manifest.find("application")
    assert application is not None
    assert application.get(f"{ANDROID_NS}networkSecurityConfig") == \
        "@xml/network_security_config"
    assert application.get(f"{ANDROID_NS}usesCleartextTraffic") is None
    assert SECURITY_CONFIG_PATH.is_file()


def test_base_config_denies_cleartext_by_default():
    root = _security_root()
    base = root.find("base-config")
    assert root.tag == "network-security-config"
    assert base is not None
    assert base.get("cleartextTrafficPermitted") == "false"


def test_only_confirmed_campus_and_probe_hosts_allow_cleartext():
    root = _security_root()
    configs = root.findall("domain-config")
    assert configs
    hosts = set()
    for config in configs:
        assert config.get("cleartextTrafficPermitted") == "true"
        for domain in config.findall("domain"):
            assert domain.get("includeSubdomains") != "true"
            hosts.add((domain.text or "").strip())
    assert hosts == EXPECTED_CLEARTEXT_HOSTS


def test_security_config_does_not_relax_tls_trust():
    root = _security_root()
    assert root.find("trust-anchors") is None
    assert root.find("debug-overrides") is None
    for certificates in root.iter("certificates"):
        assert certificates.get("src") != "user"
