package com.oitnetportal.core

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities

/** 仅在认证调用期间绑定底层 Wi-Fi，不修改或关闭用户的 VPN。 */
class CampusNetworkBinder(context: Context) {
    @PublishedApi
    internal val connectivityManager = context.applicationContext
        .getSystemService(ConnectivityManager::class.java)

    inline fun <T> withCampusNetwork(block: () -> T): T {
        val manager = connectivityManager ?: return block()
        val wifi = manager.allNetworks.firstOrNull { network ->
            manager.getNetworkCapabilities(network)?.let { capabilities ->
                capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) &&
                    !capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN)
            } == true
        } ?: return block()
        if (!manager.bindProcessToNetwork(wifi)) return block()
        return try {
            block()
        } finally {
            manager.bindProcessToNetwork(null)
        }
    }
}
