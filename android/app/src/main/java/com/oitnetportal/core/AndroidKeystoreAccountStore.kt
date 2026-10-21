package com.oitnetportal.core

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONArray
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Android Keystore 保护的多账号加密存储。
 *
 * AES-256/GCM 密钥只存在于 AndroidKeyStore（不可导出），应用私目录偏好里只落
 * Base64(iv || 密文) 的账号 JSON 数组；Keystore 密钥失效或数据损坏时 load 返回
 * 空列表，按"无存账号"处理。自动迁移旧版单凭据条目（"remembered"）。
 */
class AndroidKeystoreAccountStore(context: Context) : AccountStore {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    override fun loadAccounts(): List<StoredAccount> {
        migrateLegacyEntry()
        return loadAccountsRaw()
    }

    /** 不含迁移逻辑的原始读取，供迁移路径内部使用（避免递归）。 */
    private fun loadAccountsRaw(): List<StoredAccount> {
        val packed = prefs.getString(KEY_ACCOUNTS, null) ?: return emptyList()
        return try {
            val json = JSONArray(decryptToString(packed))
            buildList {
                for (index in 0 until json.length()) {
                    val entry = json.getJSONObject(index)
                    add(
                        StoredAccount(
                            id = entry.getString(FIELD_USERNAME),
                            alias = entry.optString(FIELD_ALIAS, ""),
                            username = entry.getString(FIELD_USERNAME),
                            password = entry.getString(FIELD_PASSWORD),
                            boundSsid = entry.optString(FIELD_SSID, ""),
                        ),
                    )
                }
            }
        } catch (_: Exception) {
            // 密钥失效/数据损坏/格式错误：统一按无存账号处理，不泄露细节
            emptyList()
        }
    }

    override fun upsert(account: StoredAccount) {
        if (account.username.isBlank() || account.password.isBlank()) return
        val updated = loadAccounts()
            .filterNot { it.id == account.id } + account
        persistAccounts(updated)
    }

    override fun remove(accountId: String) {
        val updated = loadAccounts().filterNot { it.id == accountId }
        persistAccounts(updated)
        if (prefs.getString(KEY_LAST_USED, null) == accountId) {
            prefs.edit().remove(KEY_LAST_USED).apply()
        }
    }

    override fun loadLastUsedId(): String? = prefs.getString(KEY_LAST_USED, null)

    override fun saveLastUsedId(accountId: String) {
        prefs.edit().putString(KEY_LAST_USED, accountId).apply()
    }

    /** 旧版单凭据条目迁移为账号列表；迁移失败按无存账号处理并清除旧条目。 */
    private fun migrateLegacyEntry() {
        val legacy = prefs.getString(KEY_LEGACY_SINGLE, null) ?: return
        try {
            val json = JSONObject(decryptToString(legacy))
            val username = json.getString(FIELD_USERNAME)
            if (username.isNotBlank()) {
                persistAccounts(
                    loadAccountsRaw() + StoredAccount(
                        id = username,
                        username = username,
                        password = json.getString(FIELD_PASSWORD),
                    ),
                )
                saveLastUsedId(username)
            }
        } catch (_: Exception) {
            // 旧条目不可读：放弃迁移，不阻塞新功能
        } finally {
            prefs.edit().remove(KEY_LEGACY_SINGLE).apply()
        }
    }

    private fun persistAccounts(accounts: List<StoredAccount>) {
        try {
            val json = JSONArray()
            accounts.forEach { account ->
                json.put(
                    JSONObject()
                        .put(FIELD_USERNAME, account.username)
                        .put(FIELD_PASSWORD, account.password)
                        .put(FIELD_ALIAS, account.alias)
                        .put(FIELD_SSID, account.boundSsid),
                )
            }
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.ENCRYPT_MODE, secretKey())
            val ciphertext = cipher.doFinal(json.toString().toByteArray(Charsets.UTF_8))
            val packed = byteArrayOf(cipher.iv.size.toByte()) + cipher.iv + ciphertext
            prefs.edit()
                .putString(KEY_ACCOUNTS, Base64.encodeToString(packed, Base64.NO_WRAP))
                .apply()
        } catch (_: Exception) {
            // 加密失败宁可不存，也绝不落明文
        }
    }

    /** 解密 Base64(1字节iv长度 | iv | 密文) 为 UTF-8 字符串。 */
    private fun decryptToString(packed: String): String {
        val raw = Base64.decode(packed, Base64.NO_WRAP)
        val ivLength = raw[0].toInt()
        require(raw.size > 1 + ivLength) { "corrupted entry" }
        val iv = raw.copyOfRange(1, 1 + ivLength)
        val ciphertext = raw.copyOfRange(1 + ivLength, raw.size)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(GCM_TAG_BITS, iv))
        return String(cipher.doFinal(ciphertext), Charsets.UTF_8)
    }

    /** 获取或惰性生成 Keystore 中的 AES 密钥（与旧版单凭据存储共用同一密钥）。 */
    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getEntry(KEY_ALIAS, null) as? KeyStore.SecretKeyEntry)
            ?.let { return it.secretKey }
        val generator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE,
        )
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(KEY_SIZE_BITS)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val KEY_ALIAS = "oit_portal_credential"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val KEY_SIZE_BITS = 256
        const val GCM_TAG_BITS = 128
        const val PREFS_NAME = "oit_portal_credentials"
        const val KEY_ACCOUNTS = "accounts"
        const val KEY_LAST_USED = "last_used"
        const val KEY_LEGACY_SINGLE = "remembered"
        const val FIELD_USERNAME = "u"
        const val FIELD_PASSWORD = "p"
        const val FIELD_ALIAS = "a"
        const val FIELD_SSID = "s"
    }
}
