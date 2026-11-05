package com.oitnetportal

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import com.oitnetportal.core.AndroidKeystoreAccountStore
import com.oitnetportal.core.AndroidNotificationStatusProvider
import com.oitnetportal.core.AndroidWifiIdentityProvider
import com.oitnetportal.core.AppSettingsStore
import com.oitnetportal.core.ChaquopyPortalCoreBridge
import com.oitnetportal.core.FeedbackSettingsStore
import com.oitnetportal.core.NetworkValidationGate
import com.oitnetportal.core.OpenFeedbackBridge
import com.oitnetportal.core.PersistentBackgroundReconnectStateStore
import com.oitnetportal.core.UnavailablePortalCoreBridge
import com.oitnetportal.service.BackgroundReconnectServiceController
import com.oitnetportal.ui.PortalApp
import com.oitnetportal.ui.PortalViewModel

class MainActivity : ComponentActivity() {
    private val portalViewModel: PortalViewModel by viewModels {
        val appContext = applicationContext
        val backgroundState = PersistentBackgroundReconnectStateStore.get(appContext)
        val feedbackStore = FeedbackSettingsStore(appContext)
        PortalViewModel.factory(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { username, password ->
                ChaquopyPortalCoreBridge.create(appContext, username, password)
            },
            accountStore = AndroidKeystoreAccountStore(appContext),
            settingsStore = AppSettingsStore(appContext),
            wifiIdentity = AndroidWifiIdentityProvider(appContext),
            backgroundStateStore = backgroundState,
            backgroundLauncher = BackgroundReconnectServiceController(appContext, backgroundState),
            notificationStatusProvider = AndroidNotificationStatusProvider(appContext),
            feedbackBridge = OpenFeedbackBridge.create(
                appContext,
                feedbackStore.serviceEndpoint,
                appVersionName(appContext),
            ),
        )
    }

    private var networkCallback: ConnectivityManager.NetworkCallback? = null

    /** 只放行「验证通过」那一次翻转，避免能力抖动反复触发状态校准。 */
    private val validationGate = NetworkValidationGate()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        registerNetworkCallback()
        setContent {
            PortalApp(portalViewModel)
        }
    }

    override fun onResume() {
        super.onResume()
        portalViewModel.onAppForeground()
    }

    override fun onDestroy() {
        unregisterNetworkCallback()
        super.onDestroy()
    }

    /** 幂等注册默认网络回调；只转发事件给 ViewModel，不在这里做任何网络或凭据操作。 */
    private fun registerNetworkCallback() {        if (networkCallback != null) return
        val connectivityManager = getSystemService(ConnectivityManager::class.java) ?: return
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                portalViewModel.onNetworkAvailable()
            }

            override fun onCapabilitiesChanged(
                network: Network,
                networkCapabilities: NetworkCapabilities,
            ) {
                // 仅在网络「刚刚完成验证」时触发一次状态校准：
                // 能力回调会随信号强度/带宽持续到来，每次都校准会把诊断日志刷爆。
                val validated = networkCapabilities.hasCapability(
                    NetworkCapabilities.NET_CAPABILITY_VALIDATED
                )
                if (validationGate.onValidatedStateChanged(validated)) {
                    portalViewModel.onNetworkAvailable()
                }
            }

            override fun onLost(network: Network) {
                validationGate.reset()
                portalViewModel.onNetworkLost()
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
            // 回调未注册或已被系统移除时注销会抛此异常，属可忽略的生命周期竞态
        }
    }

    /** App 版本号：反馈里带上版本，作者才知道问题出在哪个版本。 */
    fun appVersionName(context: Context): String =
        runCatching {
            context.packageManager.getPackageInfo(context.packageName, 0).versionName
        }.getOrNull().orEmpty()
}
