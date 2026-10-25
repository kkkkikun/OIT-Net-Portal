package com.oitnetportal.service

import android.content.Context
import android.content.Intent
import androidx.core.content.ContextCompat
import com.oitnetportal.core.BackgroundReconnectLauncher
import com.oitnetportal.core.BackgroundReconnectStateStore
import com.oitnetportal.core.BackgroundReconnectStatus

class BackgroundReconnectServiceController(
    context: Context,
    private val stateStore: BackgroundReconnectStateStore,
) : BackgroundReconnectLauncher {
    private val appContext = context.applicationContext

    override fun start() {
        stateStore.enabled = true
        ContextCompat.startForegroundService(
            appContext,
            intent(PortalForegroundService.ACTION_START),
        )
    }

    override fun stop() {
        stateStore.enabled = false
        appContext.startService(intent(PortalForegroundService.ACTION_STOP))
    }

    override fun accountsChanged() {
        if (stateStore.enabled) {
            appContext.startService(intent(PortalForegroundService.ACTION_ACCOUNTS_CHANGED))
        }
    }

    override fun attention(detail: String) {
        stateStore.enabled = false
        stateStore.update(BackgroundReconnectStatus.NEEDS_ATTENTION, detail)
        appContext.startService(intent(PortalForegroundService.ACTION_ATTENTION_STOP))
    }

    private fun intent(action: String) = Intent(appContext, PortalForegroundService::class.java)
        .setAction(action)
}
