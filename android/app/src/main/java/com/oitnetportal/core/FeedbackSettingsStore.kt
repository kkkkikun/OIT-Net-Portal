package com.oitnetportal.core

import android.content.Context

/**
 * 反馈通道配置的本机存储。
 *
 * 地址是 OpenFeedback 服务的地址，**不是凭据**：
 * OpenFeedback 的提交接口不需要任何客户端密钥，APK 里只有公开的 `appId`。
 *
 * 默认值由构建期注入（`android/local.properties` 的 `oit.feedback.endpoint`），
 * 该文件已在 `.gitignore` 里，真实地址不会进仓库。
 * 同学换了网络或作者换了通道，可在 App 里自行改地址。
 */
class FeedbackSettingsStore(context: Context) {

    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)

    /**
     * OpenFeedback 服务地址。
     *
     * 形如 `https://feedback.example.com`；空表示尚未配置，反馈通道不可用。
     */
    var serviceEndpoint: String
        get() = prefs.getString(KEY_SERVICE_ENDPOINT, BuildConfigFeedback.DEFAULT_ENDPOINT)
            ?.trim()
            .orEmpty()
        set(value) {
            prefs.edit().putString(KEY_SERVICE_ENDPOINT, value.trim()).apply()
        }

    /** 通道地址是否已配置。 */
    fun hasServiceEndpoint(): Boolean = serviceEndpoint.isNotBlank()

    companion object {
        private const val PREFS_NAME = "oit_portal_feedback"
        private const val KEY_SERVICE_ENDPOINT = "service_endpoint"
    }
}
