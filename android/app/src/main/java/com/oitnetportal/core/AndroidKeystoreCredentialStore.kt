package com.oitnetportal.core

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Android Keystore 保护的凭据加密存储。
 *
 * AES-256/GCM 密钥只存在于 AndroidKeyStore（TEE/StrongBox 可选，不强制），
 * 应用私目录的 SharedPreferences 里只落 Base64(iv || 密文)；Keystore 密钥不可导出，
 * 卸载应用或锁屏凭据变更导致密钥失效时，load() 返回 null，按"无存凭据"处理。
 */
class AndroidKeystoreCredentialStore(context: Context) : CredentialStore {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    override fun load(): StoredCredentials? {
        val packed = prefs.getString(KEY_ENTRY, null) ?: return null
        return try {
            val raw = Base64.decode(packed, Base64.NO_WRAP)
            // 格式：1 字节 iv 长度 | iv | 密文
            val ivLength = raw[0].toInt()
            require(raw.size > 1 + ivLength) { "corrupted entry" }
            val iv = raw.copyOfRange(1, 1 + ivLength)
            val ciphertext = raw.copyOfRange(1 + ivLength, raw.size)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(GCM_TAG_BITS, iv))
            val json = JSONObject(String(cipher.doFinal(ciphertext), Charsets.UTF_8))
            StoredCredentials(json.getString(FIELD_USERNAME), json.getString(FIELD_PASSWORD))
        } catch (_: Exception) {
            // 密钥失效/数据损坏/格式错误：统一按无存凭据处理，不泄露细节
            null
        }
    }

    override fun save(credentials: StoredCredentials) {
        try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.ENCRYPT_MODE, secretKey())
            val plaintext = JSONObject()
                .put(FIELD_USERNAME, credentials.username)
                .put(FIELD_PASSWORD, credentials.password)
                .toString()
                .toByteArray(Charsets.UTF_8)
            val ciphertext = cipher.doFinal(plaintext)
            val packed = byteArrayOf(cipher.iv.size.toByte()) + cipher.iv + ciphertext
            prefs.edit()
                .putString(KEY_ENTRY, Base64.encodeToString(packed, Base64.NO_WRAP))
                .apply()
        } catch (_: Exception) {
            // 加密失败宁可不存，也绝不落明文
        }
    }

    override fun clear() {
        prefs.edit().remove(KEY_ENTRY).apply()
    }

    /** 获取或惰性生成 Keystore 中的 AES 密钥。 */
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
        const val KEY_ENTRY = "remembered"
        const val FIELD_USERNAME = "u"
        const val FIELD_PASSWORD = "p"
    }
}
