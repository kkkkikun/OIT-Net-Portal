package com.oitnetportal

import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import com.oitnetportal.core.AndroidKeystoreAccountStore
import com.oitnetportal.core.AndroidWifiIdentityProvider
import com.oitnetportal.core.AppSettingsStore
import com.oitnetportal.core.ChaquopyPortalCoreBridge
import com.oitnetportal.core.UnavailablePortalCoreBridge
import com.oitnetportal.ui.PortalApp
import com.oitnetportal.ui.PortalViewModel

class MainActivity : ComponentActivity() {
    private val portalViewModel: PortalViewModel by viewModels {
        val appContext = applicationContext
        PortalViewModel.factory(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { username, password ->
                ChaquopyPortalCoreBridge.create(appContext, username, password)
            },
            accountStore = AndroidKeystoreAccountStore(appContext),
            settingsStore = AppSettingsStore(appContext),
            wifiIdentity = AndroidWifiIdentityProvider(appContext),
        )
    }

    private var networkCallback: ConnectivityManager.NetworkCallback? = null

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
    private fun registerNetworkCallback() {
        if (networkCallback != null) return
        val connectivityManager = getSystemService(ConnectivityManager::class.java) ?: return
        val callback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                portalViewModel.onNetworkAvailable()
            }

            override fun onCapabilitiesChanged(
                network: Network,
                networkCapabilities: NetworkCapabilities,
            ) {
                // 仅在系统完成网络验证后触发一次状态校准，避免能力抖动反复探测
                if (networkCapabilities.hasCapability(
                        NetworkCapabilities.NET_CAPABILITY_VALIDATED
                    )
                ) {
                    portalViewModel.onNetworkAvailable()
                }
            }

            override fun onLost(network: Network) {
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
}
