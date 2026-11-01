package com.oitnetportal.core

/**
 * 系统通知开关状态。
 *
 * 厂商 ROM（vivo / OPPO 等）默认禁用应用通知，此时前台服务的常驻通知
 * 与登录失败提醒都不会展示——功能在跑，用户却看不到任何提示。
 */
interface NotificationStatusProvider {
    /** 系统层面是否允许本应用发送通知。 */
    fun areNotificationsEnabled(): Boolean
}
