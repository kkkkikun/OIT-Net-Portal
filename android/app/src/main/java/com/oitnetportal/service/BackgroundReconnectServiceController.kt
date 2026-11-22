package com.oitnetportal.service

import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import com.oitnetportal.core.BackgroundReconnectLauncher
import com.oitnetportal.core.BackgroundReconnectStateStore
import com.oitnetportal.core.BackgroundReconnectStatus
import com.oitnetportal.core.BackgroundServiceRuntime

class BackgroundReconnectServiceController(
    context: Context,
    private val stateStore: BackgroundReconnectStateStore,
) : BackgroundReconnectLauncher {
    private val appContext = context.applicationContext

    override fun start() {
        stateStore.enabled = true
        try {
            ContextCompat.startForegroundService(
                appContext,
                intent(PortalForegroundService.ACTION_START),
            )
        } catch (_: IllegalStateException) {
            stateStore.enabled = false
            stateStore.update(
                BackgroundReconnectStatus.NEEDS_ATTENTION,
                "系统限制后台服务启动，请回到应用重试",
            )
        }
    }

    override fun stop() {
        stateStore.enabled = false
        stateStore.update(BackgroundReconnectStatus.STOPPED, "后台自动重连已关闭")
        if (BackgroundServiceRuntime.isRunning()) {
            runCatching { appContext.startService(intent(PortalForegroundService.ACTION_STOP)) }
        }
    }

    override fun accountsChanged() {
        if (stateStore.enabled && BackgroundServiceRuntime.isRunning()) {
            runCatching {
                appContext.startService(intent(PortalForegroundService.ACTION_ACCOUNTS_CHANGED))
            }
        }
    }

    override fun attention(detail: String) {
        stateStore.enabled = false
        stateStore.update(BackgroundReconnectStatus.NEEDS_ATTENTION, detail)
        if (BackgroundServiceRuntime.isRunning()) {
            runCatching {
                appContext.startService(intent(PortalForegroundService.ACTION_ATTENTION_STOP))
            }
        }
    }

    private fun intent(action: String) = Intent(appContext, PortalForegroundService::class.java)
        .setAction(action)
}
