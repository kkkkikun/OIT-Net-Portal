"""Android Keystore 凭据加密存储的离线源码契约检查。

只验证安全结构存在/不存在，不能证明加解密正确性，也不替代真机验收。
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STORE_PATH = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" /
    "com" / "oitnetportal" / "core" / "AndroidKeystoreCredentialStore.kt"
)
INTERFACE_PATH = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" /
    "com" / "oitnetportal" / "core" / "CredentialStore.kt"
)
STORE_SOURCE = STORE_PATH.read_text(encoding="utf-8")
INTERFACE_SOURCE = INTERFACE_PATH.read_text(encoding="utf-8")


def test_interface_defines_fail_closed_contract():
    assert "interface CredentialStore" in INTERFACE_SOURCE
    assert "fun load(): StoredCredentials?" in INTERFACE_SOURCE
    assert "fun save(credentials: StoredCredentials)" in INTERFACE_SOURCE
    assert "fun clear()" in INTERFACE_SOURCE
    assert "StoredCredentials" in INTERFACE_SOURCE


def test_keystore_backed_aes_gcm_encryption():
    assert '"AndroidKeyStore"' in STORE_SOURCE
    assert "KeyGenParameterSpec" in STORE_SOURCE
    assert "PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT" in STORE_SOURCE
    assert "BLOCK_MODE_GCM" in STORE_SOURCE
    assert "ENCRYPTION_PADDING_NONE" in STORE_SOURCE
    assert '"AES/GCM/NoPadding"' in STORE_SOURCE
    assert "GCMParameterSpec" in STORE_SOURCE
    assert "setKeySize(KEY_SIZE_BITS)" in STORE_SOURCE
    assert "const val KEY_SIZE_BITS = 256" in STORE_SOURCE


def test_only_ciphertext_is_persisted():
    save_body = STORE_SOURCE.split("override fun save", maxsplit=1)[1].split(
        "override fun clear", maxsplit=1)[0]
    # 落盘前必须经过 Cipher 加密
    assert "cipher.doFinal" in save_body
    assert "Base64.encodeToString" in save_body
    assert save_body.index("cipher.doFinal") < save_body.index("putString")
    # 明文密码绝不允许直接写入偏好
    assert 'putString(KEY_ENTRY, credentials.password)' not in STORE_SOURCE
    assert 'putString(KEY_ENTRY, plaintext)' not in STORE_SOURCE


def test_fail_closed_on_crypto_or_data_errors():
    load_body = STORE_SOURCE.split("override fun load", maxsplit=1)[1].split(
        "override fun save", maxsplit=1)[0]
    assert "catch (_: Exception)" in load_body
    assert "null" in load_body  # 解密失败按无存凭据处理
    save_body = STORE_SOURCE.split("override fun save", maxsplit=1)[1].split(
        "override fun clear", maxsplit=1)[0]
    assert "catch (_: Exception)" in save_body  # 加密失败宁可不存


def test_no_logging_or_plaintext_leakage():
    forbidden = (
        "Log.",
        "println(",
        "printStackTrace",
        "MODE_WORLD",
        "System.getenv",
    )
    for marker in forbidden:
        assert marker not in STORE_SOURCE


def test_clear_is_idempotent_removal():
    clear_body = STORE_SOURCE.split("override fun clear", maxsplit=1)[1]
    assert "remove(KEY_ENTRY)" in clear_body
