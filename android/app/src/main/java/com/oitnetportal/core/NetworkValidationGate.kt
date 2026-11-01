package com.oitnetportal.core

/**
 * 默认网络「验证通过」状态的翻转闸门。
 *
 * 背景（2026-11-01，红米 K50 Ultra / HyperOS 2 / Android 15 真机验收）：
 * Wi-Fi 的 `ConnectivityManager.NetworkCallback.onCapabilitiesChanged` 会随
 * 信号强度、带宽、验证态等持续回调。若每次回调都触发一次门户状态校准，
 * 诊断事件会每 3~12 秒涨两条，一分钟就把 50 条的环形缓冲区占满，
 * 「登录成功」这类关键事件会被直接挤掉。
 *
 * 这里只认「验证状态从未验证翻转为已验证」这一次翻转；
 * 之后能力再怎么变也不重复触发。网络断开或换网时复位，下一次验证通过仍要触发。
 */
class NetworkValidationGate {
    private var validated = false

    /**
     * 记录一次「验证状态」观测结果。
     *
     * @param isValidated 当前网络是否具备 `NET_CAPABILITY_VALIDATED`
     * @return true 表示这是一次新的「验证通过」，应当触发一次状态校准
     */
    fun onValidatedStateChanged(isValidated: Boolean): Boolean {
        val justValidated = isValidated && !validated
        validated = isValidated
        return justValidated
    }

    /** 网络断开或换网时复位，让下一次验证通过仍能触发校准。 */
    fun reset() {
        validated = false
    }
}
