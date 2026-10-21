package com.oitnetportal.core

import android.content.Context
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.wifi.WifiInfo
import android.net.wifi.WifiManager
import android.os.Build

/**
 * 当前 Wi-Fi SSID 读取。
 *
 * Android 把 SSID 视为位置信息：API 33+ 用 NEARBY_WIFI_DEVICES（neverForLocation，
 * 不涉及定位）；API 32 及以下只能用精确定位权限。任何一步不可用都返回 null，
 * 调用方退化为"最近使用账号"预选，不阻塞功能。
 */
class AndroidWifiIdentityProvider(context: Context) : WifiIdentityProvider {

    private val appContext = context.applicationContext

    override fun canReadSsid(): Boolean =
        appContext.checkSelfPermission(requiredPermission()) == PackageManager.PERMISSION_GRANTED

    override fun currentSsid(): String? {
        if (!canReadSsid()) return null
        return try {
            val raw = readRawSsid() ?: return null
            if (raw.isBlank() || raw == WifiManager.UNKNOWN_SSID) return null
            // 系统返回的 SSID 带双引号包裹
            raw.removeSurrounding("\"")
        } catch (_: Exception) {
            null
        }
    }

    private fun readRawSsid(): String? =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val connectivity = appContext.getSystemService(ConnectivityManager::class.java)
            val network = connectivity?.activeNetwork ?: return null
            val capabilities = connectivity.getNetworkCapabilities(network) ?: return null
            (capabilities.transportInfo as? WifiInfo)?.ssid
        } else {
            @Suppress("DEPRECATION")
            appContext.getSystemService(WifiManager::class.java)?.connectionInfo?.ssid
        }

    companion object {
        /** 当前系统版本读取 SSID 所需的运行时权限。 */
        fun requiredPermission(): String =
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                android.Manifest.permission.NEARBY_WIFI_DEVICES
            } else {
                android.Manifest.permission.ACCESS_FINE_LOCATION
            }
    }
}
