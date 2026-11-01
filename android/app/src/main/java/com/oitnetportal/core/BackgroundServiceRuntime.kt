package com.oitnetportal.core

/**
 * 进程内记录后台前台服务是否存活。
 *
 * 持久化的 enabled=true 只能说明"用户开过这个功能"：厂商划卡会直接杀掉进程，
 * START_STICKY 也不会被系统重启，但 SharedPreferences 里的状态文本仍是上一次的旧值，
 * 界面于是显示「网络在线，后台巡检中」而实际没有任何服务在跑。
 *
 * 这里用进程内存做存活标记：进程被杀标记自动清空，重开 App 时即可判断服务确实已停。
 */
object BackgroundServiceRuntime {
    @Volatile
    private var running: Boolean = false

    fun markRunning() {
        running = true
    }

    fun markStopped() {
        running = false
    }

    fun isRunning(): Boolean = running
}
