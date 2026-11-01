package com.oitnetportal.debug

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.net.VpnService
import android.util.Log

/**
 * 仅存在于 debug 变体的黑洞 VPN 控制器。
 *
 * VpnService 不能被外部直接启动（BIND_VPN_SERVICE 是系统级权限），
 * 所以由这个广播接收器在应用内部发起启动/停止，adb 只需要发广播即可。
 */
class DebugVpnControlReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            ACTION_STOP -> {
                context.startService(
                    Intent(context, BlackholeVpnService::class.java)
                        .setAction(BlackholeVpnService.ACTION_STOP),
                )
            }
            else -> {
                val consentIntent = VpnService.prepare(context)
                if (consentIntent != null) {
                    // 还没拿到 VPN 授权：需要先允许本应用使用 VPN
                    Log.w(TAG, "VPN 授权未就绪：请先允许本应用建立 VPN 连接")
                    return
                }
                context.startService(Intent(context, BlackholeVpnService::class.java))
            }
        }
    }

    companion object {
        private const val TAG = "OitPortalDebugVpn"
        const val ACTION_START = "com.oitnetportal.debug.action.START_BLACKHOLE_VPN"
        const val ACTION_STOP = "com.oitnetportal.debug.action.STOP_BLACKHOLE_VPN"
    }
}
