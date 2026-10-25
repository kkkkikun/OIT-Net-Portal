package com.oitnetportal.core

/** UI 与 Android Service 之间的窄接口；不传递账号或会话对象。 */
interface BackgroundReconnectLauncher {
    fun start()
    fun stop()
    fun accountsChanged()
    fun attention(detail: String)
}
