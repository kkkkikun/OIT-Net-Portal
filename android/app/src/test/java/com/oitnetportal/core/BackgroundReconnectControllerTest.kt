package com.oitnetportal.core

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

private class ScheduledFakeCore(
    private val fallbackStatus: PortalStatus = PortalStatus.ONLINE,
) : PortalCoreBridge {
    override val isAvailable: Boolean = true
    val probeResponses = ArrayDeque<ProbeResult>()
    var loginResult = LoginResult(LoginOutcome.LOGGED_IN)
    var probeCallCount = 0
        private set
    var loginCallCount = 0
        private set
    var firstProbeGate: CompletableDeferred<Unit>? = null

    override suspend fun probe(): ProbeResult {
        probeCallCount++
        if (probeCallCount == 1) firstProbeGate?.await()
        return probeResponses.removeFirstOrNull() ?: ProbeResult(fallbackStatus)
    }

    override suspend fun loginOnce(): LoginResult {
        loginCallCount++
        return loginResult
    }

    override fun captureEngine(): CaptureEngine = throw UnsupportedOperationException()
    override fun daemonEngine(): DaemonEngine = throw UnsupportedOperationException()
}

@OptIn(ExperimentalCoroutinesApi::class)
class BackgroundReconnectControllerTest {
    private fun TestScope.controller(
        core: ScheduledFakeCore,
        states: MutableList<BackgroundReconnectStatus> = mutableListOf(),
        attention: MutableList<String> = mutableListOf(),
        details: MutableList<String> = mutableListOf(),
        attemptTracker: BackgroundReconnectAttemptTracker = BackgroundReconnectAttemptTracker(),
    ) = BackgroundReconnectController(
        core = core,
        scope = this,
        clock = { testScheduler.currentTime },
        attemptTracker = attemptTracker,
        onState = { status, detail ->
            states.add(status)
            details.add(detail)
        },
        onNeedsAttention = { attention.add(it) },
    )

    @Test
    fun `online probes never login and repeat after sixty seconds`() = runTest {
        val core = ScheduledFakeCore()
        val controller = controller(core)

        controller.start()
        runCurrent()
        advanceTimeBy(59_999)
        runCurrent()
        assertEquals(1, core.probeCallCount)
        advanceTimeBy(1)
        runCurrent()

        assertEquals(2, core.probeCallCount)
        assertEquals(0, core.loginCallCount)
        controller.stopAndWait()
    }

    @Test
    fun `captive probe logs in once and success restores online interval`() = runTest {
        val core = ScheduledFakeCore()
        core.probeResponses.add(ProbeResult(PortalStatus.CAPTIVE))
        val states = mutableListOf<BackgroundReconnectStatus>()
        val controller = controller(core, states)

        controller.start()
        runCurrent()

        assertEquals(1, core.loginCallCount)
        assertEquals(BackgroundReconnectStatus.MONITORING, states.last())
        controller.stopAndWait()
    }

    @Test
    fun `captive path reports distinguishable auto relogin states`() = runTest {
        val core = ScheduledFakeCore()
        core.probeResponses.add(ProbeResult(PortalStatus.CAPTIVE))
        val details = mutableListOf<String>()
        val controller = controller(core, details = details)

        controller.start()
        runCurrent()

        assertTrue(
            "自动重登前必须有可区分的提示，实际=$details",
            details.any { it.contains("检测到需要校园网认证") },
        )
        assertTrue(
            "自动重登成功必须有可区分的提示，实际=$details",
            details.any { it.contains("自动重登成功") },
        )
        controller.stopAndWait()
    }

    @Test
    fun `online patrol keeps the plain monitoring detail`() = runTest {
        val core = ScheduledFakeCore()
        val details = mutableListOf<String>()
        val controller = controller(core, details = details)

        controller.start()
        runCurrent()

        assertEquals("网络在线，后台巡检中", details.last())
        controller.stopAndWait()
    }

    @Test
    fun `already online login outcome is still distinguishable from plain patrol`() = runTest {
        val core = ScheduledFakeCore()
        core.probeResponses.add(ProbeResult(PortalStatus.CAPTIVE))
        core.loginResult = LoginResult(LoginOutcome.ALREADY_ONLINE)
        val details = mutableListOf<String>()
        val controller = controller(core, details = details)

        controller.start()
        runCurrent()

        assertTrue("实际=$details", details.any { it.contains("检测到需要校园网认证") })
        assertTrue("实际=$details", details.any { it.contains("已在线") })
        controller.stopAndWait()
    }

    @Test
    fun `offline waits thirty seconds without submitting credentials`() = runTest {
        val core = ScheduledFakeCore(fallbackStatus = PortalStatus.OFFLINE)
        val controller = controller(core)

        controller.start()
        runCurrent()
        advanceTimeBy(29_999)
        runCurrent()
        assertEquals(1, core.probeCallCount)
        advanceTimeBy(1)
        runCurrent()

        assertEquals(2, core.probeCallCount)
        assertEquals(0, core.loginCallCount)
        controller.stopAndWait()
    }

    @Test
    fun `captive retries respect three hundred second minimum login interval`() = runTest {
        val core = ScheduledFakeCore(fallbackStatus = PortalStatus.CAPTIVE)
        val controller = controller(core)

        controller.start()
        runCurrent()
        assertEquals(1, core.loginCallCount)
        advanceTimeBy(60_000)
        runCurrent()
        assertEquals(1, core.loginCallCount)
        advanceTimeBy(240_000)
        runCurrent()

        assertEquals(2, core.loginCallCount)
        controller.stopAndWait()
    }

    @Test
    fun `controller restart preserves minimum interval and failure count`() = runTest {
        val tracker = BackgroundReconnectAttemptTracker()
        val firstCore = ScheduledFakeCore(fallbackStatus = PortalStatus.CAPTIVE)
        firstCore.loginResult = LoginResult(LoginOutcome.FAILED)
        val first = controller(firstCore, attemptTracker = tracker)
        first.start()
        runCurrent()
        first.stopAndWait()
        assertEquals(1, firstCore.loginCallCount)

        val secondCore = ScheduledFakeCore(fallbackStatus = PortalStatus.CAPTIVE)
        secondCore.loginResult = LoginResult(LoginOutcome.FAILED)
        val second = controller(secondCore, attemptTracker = tracker)
        advanceTimeBy(299_999)
        second.start()
        runCurrent()
        assertEquals(0, secondCore.loginCallCount)
        advanceTimeBy(1)
        runCurrent()
        second.stopAndWait()

        assertEquals(1, secondCore.loginCallCount)
        assertEquals(2L, tracker.loginFailures)
    }

    @Test
    fun `unknown probes use bounded exponential backoff without login`() = runTest {
        val core = ScheduledFakeCore(fallbackStatus = PortalStatus.UNKNOWN)
        val states = mutableListOf<BackgroundReconnectStatus>()
        val controller = controller(core, states)

        controller.start()
        runCurrent()
        advanceTimeBy(4_999)
        runCurrent()
        assertEquals(1, core.probeCallCount)
        advanceTimeBy(1)
        runCurrent()
        assertEquals(2, core.probeCallCount)
        advanceTimeBy(9_999)
        runCurrent()
        assertEquals(2, core.probeCallCount)
        advanceTimeBy(1)
        runCurrent()

        assertEquals(3, core.probeCallCount)
        assertEquals(0, core.loginCallCount)
        assertTrue(states.contains(BackgroundReconnectStatus.BACKOFF))
        controller.stopAndWait()
    }

    @Test
    fun `third consecutive failed login stops automatic attempts`() = runTest {
        val core = ScheduledFakeCore(fallbackStatus = PortalStatus.CAPTIVE)
        core.loginResult = LoginResult(LoginOutcome.FAILED)
        val attention = mutableListOf<String>()
        val controller = controller(core, attention = attention)

        controller.start()
        runCurrent()
        advanceTimeBy(300_000)
        runCurrent()
        advanceTimeBy(300_000)
        runCurrent()
        advanceTimeBy(600_000)
        runCurrent()

        assertEquals(3, core.loginCallCount)
        assertEquals(1, attention.size)
        controller.stopAndWait()
    }

    @Test
    fun `rejected credentials immediately require attention and never retry`() = runTest {
        val core = ScheduledFakeCore(fallbackStatus = PortalStatus.CAPTIVE)
        core.loginResult = LoginResult(LoginOutcome.LOGIN_REJECTED)
        val attention = mutableListOf<String>()
        val controller = controller(core, attention = attention)

        controller.start()
        runCurrent()
        advanceTimeBy(600_000)
        runCurrent()

        assertEquals(1, core.loginCallCount)
        assertEquals(1, attention.size)
        controller.stopAndWait()
    }

    @Test
    fun `network signals are conflated to one pending calibration`() = runTest {
        val core = ScheduledFakeCore()
        core.firstProbeGate = CompletableDeferred()
        val controller = controller(core)

        controller.start()
        runCurrent()
        repeat(5) { controller.requestCalibration() }
        core.firstProbeGate?.complete(Unit)
        runCurrent()

        assertEquals(2, core.probeCallCount)
        controller.stopAndWait()
    }

    @Test
    fun `stop cancels future work and ignores later network signals`() = runTest {
        val core = ScheduledFakeCore()
        core.firstProbeGate = CompletableDeferred()
        val controller = controller(core)

        controller.start()
        runCurrent()
        controller.stopAndWait()
        controller.requestCalibration()
        advanceTimeBy(600_000)
        runCurrent()

        assertEquals(1, core.probeCallCount)
        assertEquals(0, core.loginCallCount)
    }

    @Test
    fun `account selector prefers exact ssid binding over last used`() {
        val bound = StoredAccount("bound", username = "bound", password = "one", boundSsid = "OIT")
        val recent = StoredAccount("recent", username = "recent", password = "two")

        val selected = BackgroundAccountSelector.select(
            accounts = listOf(recent, bound),
            lastUsedId = "recent",
            currentSsid = "OIT",
        )

        assertEquals("bound", selected?.id)
    }

    @Test
    fun `account selector uses last used or returns null without safe choice`() {
        val recent = StoredAccount("recent", username = "recent", password = "two")
        assertEquals(
            "recent",
            BackgroundAccountSelector.select(listOf(recent), "recent", null)?.id,
        )
        assertEquals(
            null,
            BackgroundAccountSelector.select(listOf(recent), null, null)?.id,
        )
        assertEquals(
            null,
            BackgroundAccountSelector.select(emptyList(), "recent", null)?.id,
        )
    }
}
