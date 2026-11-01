package com.oitnetportal.debug

import android.content.Intent
import android.net.VpnService
import android.os.ParcelFileDescriptor
import java.io.FileInputStream

/**
 * 仅存在于 debug 变体的"黑洞 VPN"：建立 tun 接口接管默认路由，把所有出站流量读出来直接丢弃。
 *
 * 用途：在没有真实 VPN 账号的前提下复现"VPN 开启后校园网认证请求被带偏"的场景——
 * 默认网络变成这个黑洞 VPN 后，校园网门户在默认路由上不可达；
 * 若 CampusNetworkBinder 在认证期间把进程绑回物理 Wi-Fi，认证就仍然能成功。
 *
 * release 变体不包含本文件（文件位于 android/app/src/debug/）。
 */
class BlackholeVpnService : VpnService() {
    private var tunnel: ParcelFileDescriptor? = null
    private var drainThread: Thread? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopTunnel()
            stopSelf(startId)
            return START_NOT_STICKY
        }
        startTunnel()
        return START_STICKY
    }

    private fun startTunnel() {
        if (tunnel != null) return
        val builder = Builder()
        builder.setSession("OIT-Portal 黑洞 VPN")
        builder.setMtu(1500)
        builder.addAddress(TUN_ADDRESS, 32)
        builder.addRoute("0.0.0.0", 0)
        builder.addDnsServer(TUN_DNS)
        val descriptor = builder.establish() ?: return
        tunnel = descriptor
        drainThread = Thread {
            val input = FileInputStream(descriptor.fileDescriptor)
            val buffer = ByteArray(16 * 1024)
            while (!Thread.currentThread().isInterrupted) {
                val read = try {
                    input.read(buffer)
                } catch (_: Exception) {
                    -1
                }
                if (read <= 0) break
                // 黑洞：读出来直接丢弃，不回写，等于流量被吞掉
            }
        }.apply {
            isDaemon = true
            name = "oit-blackhole-vpn"
            start()
        }
    }

    private fun stopTunnel() {
        drainThread?.interrupt()
        drainThread = null
        try {
            tunnel?.close()
        } catch (_: Exception) {
            // tun 已经失效时忽略关闭异常
        }
        tunnel = null
    }

    override fun onDestroy() {
        stopTunnel()
        super.onDestroy()
    }

    override fun onRevoke() {
        stopTunnel()
        super.onRevoke()
    }

    companion object {
        const val ACTION_STOP = "com.oitnetportal.debug.action.STOP_BLACKHOLE_VPN"
        private const val TUN_ADDRESS = "10.77.0.2"
        private const val TUN_DNS = "10.77.0.1"
    }
}
