"""Android Keystore 多账号加密存储的离线源码契约检查。

只验证安全结构存在/不存在，不能证明加解密正确性，也不替代真机验收。
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" /
    "com" / "oitnetportal" / "core"
)
STORE_PATH = CORE_DIR / "AndroidKeystoreAccountStore.kt"
INTERFACE_PATH = CORE_DIR / "AccountStore.kt"
SSID_PROVIDER_PATH = CORE_DIR / "WifiSsidProvider.kt"
MANIFEST_PATH = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
)
STORE_SOURCE = STORE_PATH.read_text(encoding="utf-8")
INTERFACE_SOURCE = INTERFACE_PATH.read_text(encoding="utf-8")
SSID_PROVIDER_SOURCE = SSID_PROVIDER_PATH.read_text(encoding="utf-8")
MANIFEST_SOURCE = MANIFEST_PATH.read_text(encoding="utf-8")


def test_legacy_single_credential_files_removed():
    assert not (CORE_DIR / "CredentialStore.kt").exists()
    assert not (CORE_DIR / "AndroidKeystoreCredentialStore.kt").exists()


def test_interface_defines_multi_account_fail_closed_contract():
    assert "interface AccountStore" in INTERFACE_SOURCE
    assert "fun loadAccounts(): List<StoredAccount>" in INTERFACE_SOURCE
    assert "fun upsert(account: StoredAccount)" in INTERFACE_SOURCE
    assert "fun remove(accountId: String)" in INTERFACE_SOURCE
    assert "fun loadLastUsedId(): String?" in INTERFACE_SOURCE
    # 账号模型含别名与 SSID 绑定；元数据视图不含密码
    assert 'val alias: String = ""' in INTERFACE_SOURCE
    assert 'val boundSsid: String = ""' in INTERFACE_SOURCE
    info_body = INTERFACE_SOURCE.split("data class AccountInfo", maxsplit=1)[1].split(
        "fun StoredAccount.toInfo", maxsplit=1)[0]
    assert "password" not in info_body


def test_keystore_backed_aes_gcm_encryption():
    assert '"AndroidKeyStore"' in STORE_SOURCE
    assert "KeyGenParameterSpec" in STORE_SOURCE
    assert "BLOCK_MODE_GCM" in STORE_SOURCE
    assert '"AES/GCM/NoPadding"' in STORE_SOURCE
    assert "GCMParameterSpec" in STORE_SOURCE
    assert "const val KEY_SIZE_BITS = 256" in STORE_SOURCE


def test_only_ciphertext_is_persisted():
    persist_body = STORE_SOURCE.split("private fun persistAccounts", maxsplit=1)[1].split(
        "private fun decryptToString", maxsplit=1)[0]
    assert "cipher.doFinal" in persist_body
    assert "Base64.encodeToString" in persist_body
    assert persist_body.index("cipher.doFinal") < persist_body.index("putString")


def test_fail_closed_on_crypto_or_data_errors():
    assert STORE_SOURCE.count("catch (_: Exception)") >= 3  # load / persist / migrate
    raw_body = STORE_SOURCE.split("private fun loadAccountsRaw", maxsplit=1)[1].split(
        "override fun upsert", maxsplit=1)[0]
    assert "emptyList()" in raw_body


def test_legacy_single_entry_migration_is_safe_and_non_recursive():
    assert 'KEY_LEGACY_SINGLE = "remembered"' in STORE_SOURCE
    assert "migrateLegacyEntry" in STORE_SOURCE
    migrate_body = STORE_SOURCE.split("private fun migrateLegacyEntry", maxsplit=1)[1].split(
        "private fun persistAccounts", maxsplit=1)[0]
    # 迁移内部只走原始读取，避免迁移 → 读取 → 迁移的递归
    assert "loadAccountsRaw()" in migrate_body
    assert "loadAccounts()" not in migrate_body
    assert "remove(KEY_LEGACY_SINGLE)" in migrate_body


def test_last_used_account_tracking():
    assert 'KEY_LAST_USED = "last_used"' in STORE_SOURCE
    assert "remove(KEY_LAST_USED)" in STORE_SOURCE  # 删除账号时同步清理最近使用


def test_no_logging_or_plaintext_leakage():
    for marker in ("Log.", "println(", "printStackTrace", "MODE_WORLD", "System.getenv"):
        assert marker not in STORE_SOURCE


def test_ssid_provider_permissions_are_scoped_by_api_level():
    assert "NEARBY_WIFI_DEVICES" in MANIFEST_SOURCE
    assert 'android:usesPermissionFlags="neverForLocation"' in MANIFEST_SOURCE
    assert "ACCESS_FINE_LOCATION" in MANIFEST_SOURCE
    assert "ACCESS_COARSE_LOCATION" in MANIFEST_SOURCE  # 精确定位必须与粗略定位成对声明
    assert 'android:maxSdkVersion="32"' in MANIFEST_SOURCE


def test_ssid_provider_is_fail_closed_and_strips_quotes():
    assert "canReadSsid()" in SSID_PROVIDER_SOURCE
    assert "WifiManager.UNKNOWN_SSID" in SSID_PROVIDER_SOURCE
    assert 'removeSurrounding("\\"")' in SSID_PROVIDER_SOURCE
    assert "catch (_: Exception)" in SSID_PROVIDER_SOURCE
    for marker in ("Log.", "println(", "printStackTrace"):
        assert marker not in SSID_PROVIDER_SOURCE
