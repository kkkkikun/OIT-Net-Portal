package com.oitnetportal.core

import android.Manifest
import android.app.AppOpsManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Process
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

/**
 * 系统通知开关的真实查询实现；通知是否可用由系统与厂商 ROM 决定，应用只读取不修改。
 *
 * 三层都要看，缺一层就会出现"功能在跑、但用户看不到任何提示"：
 * 1. [NotificationManagerCompat.areNotificationsEnabled]：应用级通知开关被关或渠道被禁用；
 * 2. Android 13+ 的 `POST_NOTIFICATIONS` 运行时权限；
 * 3. AppOps 的 `POST_NOTIFICATION`：部分 ROM（含 vivo Funtouch）用 `MODE_IGNORED`
 *    让通知"入队但不展示"，而框架的 areNotificationsEnabled 在 API 28 上并不查这一层。
 */
class AndroidNotificationStatusProvider(context: Context) : NotificationStatusProvider {
    private val appContext = context.applicationContext

    override fun areNotificationsEnabled(): Boolean {
        if (!NotificationManagerCompat.from(appContext).areNotificationsEnabled()) return false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            val granted = ContextCompat.checkSelfPermission(
                appContext,
                Manifest.permission.POST_NOTIFICATIONS,
            ) == PackageManager.PERMISSION_GRANTED
            if (!granted) return false
        }
        return isPostNotificationAppOpAllowed()
    }

    /** 用 raw 变体读取原始模式：MODE_DEFAULT 表示没有显式设置，即允许。 */
    private fun isPostNotificationAppOpAllowed(): Boolean {
        val appOps = appContext.getSystemService(AppOpsManager::class.java) ?: return true
        val mode = runCatching { rawAppOpMode(appOps) }
            .getOrDefault(AppOpsManager.MODE_ALLOWED)
        // MODE_IGNORED：通知仍会入队但系统不展示；MODE_ERRORED：直接拒绝。
        return mode != AppOpsManager.MODE_IGNORED && mode != AppOpsManager.MODE_ERRORED
    }

    /**
     * API 29 才有 raw 变体；更早的版本只能用 checkOpNoThrow（API 19 起可用，29 起废弃）。
     * 两者对本用例的判定一致：显式 ignore/deny 都会原样返回，未设置则返回允许。
     */
    @Suppress("DEPRECATION")
    private fun rawAppOpMode(appOps: AppOpsManager): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            appOps.unsafeCheckOpRawNoThrow(
                OP_POST_NOTIFICATION,
                Process.myUid(),
                appContext.packageName,
            )
        } else {
            appOps.checkOpNoThrow(
                OP_POST_NOTIFICATION,
                Process.myUid(),
                appContext.packageName,
            )
        }

    private companion object {
        /**
         * `AppOpsManager.OP_POST_NOTIFICATION` 未在公开 SDK 中暴露，而各厂商 ROM 的 op 编号并不统一
         * （实测 vivo 上是 11，AOSP 上 26 是 CAMERA），因此按名字交给框架去解析。
         */
        const val OP_POST_NOTIFICATION = "POST_NOTIFICATION"
    }
}
