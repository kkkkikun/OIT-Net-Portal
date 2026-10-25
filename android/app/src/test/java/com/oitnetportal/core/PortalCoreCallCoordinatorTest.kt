package com.oitnetportal.core

import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class PortalCoreCallCoordinatorTest {
    @Test
    fun `serialized calls never overlap across callers`() = runTest {
        val coordinator = PortalCoreCallCoordinator()
        var activeCalls = 0
        var maximumActiveCalls = 0

        val jobs = List(2) {
            launch {
                coordinator.withSerializedCall {
                    activeCalls++
                    maximumActiveCalls = maxOf(maximumActiveCalls, activeCalls)
                    delay(1_000)
                    activeCalls--
                }
            }
        }
        runCurrent()
        assertEquals(1, maximumActiveCalls)
        advanceTimeBy(2_000)
        runCurrent()
        jobs.forEach { it.join() }

        assertEquals(1, maximumActiveCalls)
        assertEquals(0, activeCalls)
    }
}
