package com.oitnetportal.core

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** 后台重连只持久化非敏感状态；账号与秘密仍由 AccountStore 管理。 */
enum class BackgroundReconnectStatus {
    STOPPED,
    STARTING,
    MONITORING,
    BACKOFF,
    NEEDS_ATTENTION,
}

data class BackgroundReconnectSnapshot(
    val enabled: Boolean = false,
    val status: BackgroundReconnectStatus = BackgroundReconnectStatus.STOPPED,
    val detail: String = "后台自动重连已关闭",
)

interface BackgroundReconnectStateStore {
    val snapshots: StateFlow<BackgroundReconnectSnapshot>
    var enabled: Boolean

    fun update(status: BackgroundReconnectStatus, detail: String)
}

class PersistentBackgroundReconnectStateStore private constructor(
    context: Context,
) : BackgroundReconnectStateStore {
    private val prefs = context.applicationContext
        .getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
    private val mutableSnapshots = MutableStateFlow(loadSnapshot())

    override val snapshots = mutableSnapshots.asStateFlow()

    override var enabled: Boolean
        get() = mutableSnapshots.value.enabled
        set(value) {
            prefs.edit().putBoolean(KEY_ENABLED, value).apply()
            mutableSnapshots.value = mutableSnapshots.value.copy(enabled = value)
        }

    override fun update(status: BackgroundReconnectStatus, detail: String) {
        prefs.edit()
            .putString(KEY_STATUS, status.name)
            .putString(KEY_DETAIL, detail)
            .apply()
        mutableSnapshots.value = mutableSnapshots.value.copy(status = status, detail = detail)
    }

    private fun loadSnapshot(): BackgroundReconnectSnapshot {
        val status = runCatching {
            BackgroundReconnectStatus.valueOf(
                prefs.getString(KEY_STATUS, BackgroundReconnectStatus.STOPPED.name)
                    ?: BackgroundReconnectStatus.STOPPED.name
            )
        }.getOrDefault(BackgroundReconnectStatus.STOPPED)
        return BackgroundReconnectSnapshot(
            enabled = prefs.getBoolean(KEY_ENABLED, false),
            status = status,
            detail = prefs.getString(KEY_DETAIL, "后台自动重连已关闭")
                ?: "后台自动重连已关闭",
        )
    }

    companion object {
        private const val PREFS_NAME = "oit_portal_background_reconnect"
        private const val KEY_ENABLED = "enabled"
        private const val KEY_STATUS = "status"
        private const val KEY_DETAIL = "detail"

        @Volatile
        private var instance: PersistentBackgroundReconnectStateStore? = null

        fun get(context: Context): PersistentBackgroundReconnectStateStore =
            instance ?: synchronized(this) {
                instance ?: PersistentBackgroundReconnectStateStore(context.applicationContext)
                    .also { instance = it }
            }
    }
}
