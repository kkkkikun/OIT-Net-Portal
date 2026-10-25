package com.oitnetportal.core

import android.content.Context

/**
 * 应用行为设置（非敏感开关，明文偏好即可）。
 * 凭据不属于这里——敏感数据只走 [CredentialStore] 的加密存储。
 */
interface SettingsStore {
    /** 网络恢复（默认网络可用/能力验证通过）时自动刷新连接状态。 */
    var autoRefreshOnNetworkRecovery: Boolean

    /** 应用回到前台时自动刷新一次连接状态。 */
    var autoRefreshOnForeground: Boolean

    /** 后台自动重连；状态由同一进程的状态仓库发布。 */
    var backgroundAutoReconnectEnabled: Boolean
}

class AppSettingsStore(context: Context) : SettingsStore {
    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val backgroundState = PersistentBackgroundReconnectStateStore.get(context)

    override var autoRefreshOnNetworkRecovery: Boolean
        get() = prefs.getBoolean(KEY_NETWORK_RECOVERY, true)
        set(value) {
            prefs.edit().putBoolean(KEY_NETWORK_RECOVERY, value).apply()
        }

    override var autoRefreshOnForeground: Boolean
        get() = prefs.getBoolean(KEY_FOREGROUND, true)
        set(value) {
            prefs.edit().putBoolean(KEY_FOREGROUND, value).apply()
        }

    override var backgroundAutoReconnectEnabled: Boolean
        get() = backgroundState.enabled
        set(value) {
            backgroundState.enabled = value
        }

    private companion object {
        const val PREFS_NAME = "oit_portal_settings"
        const val KEY_NETWORK_RECOVERY = "auto_refresh_on_network_recovery"
        const val KEY_FOREGROUND = "auto_refresh_on_foreground"
    }
}
