package com.oitnetportal.core

import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/** 所有 Chaquopy 桥接实例共享一个进程级调用串行点。 */
class PortalCoreCallCoordinator internal constructor() {
    private val mutex = Mutex()

    suspend fun <T> withSerializedCall(block: suspend () -> T): T = mutex.withLock {
        block()
    }
}
