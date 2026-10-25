package com.oitnetportal.service

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.IBinder
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import com.oitnetportal.MainActivity
import com.oitnetportal.R
import com.oitnetportal.core.AndroidKeystoreAccountStore
import com.oitnetportal.core.AndroidWifiIdentityProvider
import com.oitnetportal.core.BackgroundAccountSelector
import com.oitnetportal.core.BackgroundReconnectController
import com.oitnetportal.core.BackgroundReconnectAttemptTracker
import com.oitnetportal.core.BackgroundReconnectStateStore
import com.oitnetportal.core.BackgroundReconnectStatus
import com.oitnetportal.core.ChaquopyPortalCoreBridge
import com.oitnetportal.core.PersistentBackgroundReconnectStateStore
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch

/** Android 生命周期边界；认证策略由可独立测试的控制器负责。 */
class PortalForegroundService : Service() {
    private lateinit var stateStore: BackgroundReconnectStateStore
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private val commands = Channel<ServiceCommand>(Channel.UNLIMITED)
    private var core: ChaquopyPortalCoreBridge? = null
    private var controller: BackgroundReconnectController? = null
    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var latestStartId = 0
    private var destructionPending = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        stateStore = PersistentBackgroundReconnectStateStore.get(this)
        createNotificationChannel()
        registerNetworkCallback()
        serviceScope.launch { processCommands() }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        latestStartId = startId
        when (intent?.action) {
            ACTION_STOP -> {
                stateStore.enabled = false
                commands.trySend(ServiceCommand.Stop(preserveAttention = false, startId = startId))
            }
            ACTION_ATTENTION_STOP -> {
                showAttentionNotification(stateStore.snapshots.value.detail)
                commands.trySend(ServiceCommand.Stop(preserveAttention = true, startId = startId))
            }
            ACTION_ACCOUNTS_CHANGED -> {
                if (stateStore.enabled) {
                    startForeground(NOTIFICATION_ID, buildOngoingNotification())
                    commands.trySend(ServiceCommand.Restart)
                }
            }
            else -> {
                if (stateStore.enabled) {
                    stateStore.update(BackgroundReconnectStatus.STARTING, "正在启动后台巡检")
                    startForeground(NOTIFICATION_ID, buildOngoingNotification())
                    commands.trySend(ServiceCommand.Start)
                } else {
                    requestStopSelf(startId)
                }
            }
        }
        return if (stateStore.enabled) START_STICKY else START_NOT_STICKY
    }

    override fun onDestroy() {
        unregisterNetworkCallback()
        commands.trySend(ServiceCommand.Destroy)
        super.onDestroy()
    }

    private suspend fun processCommands() {
        for (command in commands) {
            when (command) {
                ServiceCommand.Start -> {
                    if (!destructionPending && stateStore.enabled && controller?.isRunning != true) {
                        stopWorker()
                        startWorker()
                    }
                }
                ServiceCommand.Restart -> restartWorker()
                is ServiceCommand.Stop -> {
                    if (!stateStore.enabled) {
                        stopService(command.preserveAttention, command.startId)
                    }
                }
                ServiceCommand.Destroy -> {
                    stopWorker()
                    break
                }
            }
        }
    }

    private suspend fun restartWorker() {
        if (destructionPending) return
        stopWorker()
        if (stateStore.enabled) startWorker()
    }

    private suspend fun startWorker() {
        val accountStore = AndroidKeystoreAccountStore(this)
        val account = BackgroundAccountSelector.select(
            accounts = accountStore.loadAccounts(),
            lastUsedId = accountStore.loadLastUsedId(),
            currentSsid = AndroidWifiIdentityProvider(this).currentSsid(),
        )
        if (account == null) {
            needsAttention("请先选择并保存一个校园网账号")
            return
        }
        try {
            val newCore = ChaquopyPortalCoreBridge.create(this, account.username, account.password)
            core = newCore
            controller = BackgroundReconnectController(
                core = newCore,
                scope = serviceScope,
                clock = { SystemClock.elapsedRealtime() },
                attemptTracker = BackgroundReconnectAttemptTracker.shared,
                onState = { status, detail ->
                    stateStore.update(status, detail)
                    updateOngoingNotification()
                },
                onNeedsAttention = { detail -> needsAttention(detail) },
            ).also { it.start() }
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (_: Exception) {
            needsAttention("后台核心不可用，请手动登录后重试")
        }
    }

    private suspend fun stopWorker() {
        controller?.stopAndWait()
        controller = null
        core?.shutdown()
        core = null
    }

    private suspend fun stopService(preserveAttention: Boolean, startId: Int) {
        stopWorker()
        if (stateStore.enabled) return
        stopForeground(STOP_FOREGROUND_REMOVE)
        if (!preserveAttention) {
            stateStore.update(BackgroundReconnectStatus.STOPPED, "后台自动重连已关闭")
        }
        requestStopSelf(startId)
    }

    private fun requestStopSelf(startId: Int) {
        if (stopSelfResult(startId)) destructionPending = true
    }

    private fun needsAttention(detail: String) {
        stateStore.enabled = false
        stateStore.update(BackgroundReconnectStatus.NEEDS_ATTENTION, detail)
        showAttentionNotification(detail)
        commands.trySend(ServiceCommand.Stop(preserveAttention = true, startId = latestStartId))
    }

    private fun registerNetworkCallback() {
        if (networkCallback != null) return
        val connectivityManager = getSystemService(ConnectivityManager::class.java) ?: return
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                controller?.requestCalibration()
            }

            override fun onCapabilitiesChanged(
                network: Network,
                networkCapabilities: NetworkCapabilities,
            ) {
                if (networkCapabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)) {
                    controller?.requestCalibration()
                }
            }

            override fun onLost(network: Network) {
                controller?.requestCalibration()
            }
        }
        connectivityManager.registerDefaultNetworkCallback(callback)
        networkCallback = callback
    }

    private fun unregisterNetworkCallback() {
        val callback = networkCallback ?: return
        networkCallback = null
        try {
            getSystemService(ConnectivityManager::class.java)
                ?.unregisterNetworkCallback(callback)
        } catch (_: IllegalArgumentException) {
            // 系统已移除回调时无需重复注销。
        }
    }

    private fun createNotificationChannel() {
        val channel = NotificationChannel(
            CHANNEL_ID,
            getString(R.string.notification_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.notification_channel_description)
        }
        getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }

    private fun contentIntent(): PendingIntent = PendingIntent.getActivity(
        this,
        0,
        Intent(this, MainActivity::class.java),
        PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
    )

    private fun buildOngoingNotification(): Notification {
        val stopIntent = PendingIntent.getService(
            this,
            1,
            Intent(this, PortalForegroundService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.notification_title))
            .setContentText(stateStore.snapshots.value.detail)
            .setContentIntent(contentIntent())
            .setOnlyAlertOnce(true)
            .setOngoing(true)
            .addAction(0, getString(R.string.notification_stop), stopIntent)
            .build()
    }

    @SuppressLint("MissingPermission")
    private fun updateOngoingNotification() {
        if (controller == null) return
        getSystemService(NotificationManager::class.java)
            .notify(NOTIFICATION_ID, buildOngoingNotification())
    }

    @SuppressLint("MissingPermission")
    private fun showAttentionNotification(detail: String) {
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.notification_attention_title))
            .setContentText(detail)
            .setContentIntent(contentIntent())
            .setAutoCancel(true)
            .build()
        getSystemService(NotificationManager::class.java)
            .notify(ATTENTION_NOTIFICATION_ID, notification)
    }

    private sealed interface ServiceCommand {
        data object Start : ServiceCommand
        data object Restart : ServiceCommand
        data class Stop(val preserveAttention: Boolean, val startId: Int) : ServiceCommand
        data object Destroy : ServiceCommand
    }

    companion object {
        const val ACTION_START = "com.oitnetportal.action.START_DAEMON"
        const val ACTION_STOP = "com.oitnetportal.action.STOP_DAEMON"
        const val ACTION_ACCOUNTS_CHANGED = "com.oitnetportal.action.ACCOUNTS_CHANGED"
        const val ACTION_ATTENTION_STOP = "com.oitnetportal.action.ATTENTION_STOP"
        private const val CHANNEL_ID = "campus_network_daemon"
        private const val NOTIFICATION_ID = 1001
        private const val ATTENTION_NOTIFICATION_ID = 1002
    }
}
