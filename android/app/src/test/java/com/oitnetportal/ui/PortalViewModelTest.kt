package com.oitnetportal.ui

import com.oitnetportal.core.CaptureEngine
import com.oitnetportal.core.CredentialStore
import com.oitnetportal.core.DaemonEngine
import com.oitnetportal.core.LoginOutcome
import com.oitnetportal.core.LoginResult
import com.oitnetportal.core.PortalCoreBridge
import com.oitnetportal.core.PortalStatus
import com.oitnetportal.core.ProbeResult
import com.oitnetportal.core.SettingsStore
import com.oitnetportal.core.StoredCredentials
import com.oitnetportal.core.UnavailablePortalCoreBridge
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.advanceUntilIdle
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** 内存假桥接：记录调用次数，按队列返回探测结果，永不触碰 Python/Android 框架。 */
private class FakeCoreBridge(
    override val isAvailable: Boolean = true,
) : PortalCoreBridge {
    val probeResponses = ArrayDeque<ProbeResult>()
    var probeCallCount = 0
        private set
    var loginCallCount = 0
        private set
    var loginResult = LoginResult(LoginOutcome.FAILED, "登录失败")

    override suspend fun probe(): ProbeResult {
        probeCallCount++
        return probeResponses.removeFirstOrNull()
            ?: ProbeResult(PortalStatus.UNKNOWN, "未配置探测响应")
    }

    override suspend fun loginOnce(): LoginResult {
        loginCallCount++
        return loginResult
    }

    override fun captureEngine(): CaptureEngine = throw UnsupportedOperationException()

    override fun daemonEngine(): DaemonEngine = throw UnsupportedOperationException()
}

/** 内存假凭据存储：记录 save/clear 调用，不触碰 Keystore/磁盘。 */
private class FakeCredentialStore(
    private val stored: StoredCredentials? = null,
) : CredentialStore {
    var savedCredentials: StoredCredentials? = null
        private set
    var saveCallCount = 0
        private set
    var clearCallCount = 0
        private set
    var loadCallCount = 0
        private set

    override fun load(): StoredCredentials? {
        loadCallCount++
        return stored
    }

    override fun save(credentials: StoredCredentials) {
        saveCallCount++
        savedCredentials = credentials
    }

    override fun clear() {
        clearCallCount++
    }
}

/** 内存假设置存储：记录读写，不触碰磁盘。 */
private class FakeSettingsStore(
    override var autoRefreshOnNetworkRecovery: Boolean = true,
    override var autoRefreshOnForeground: Boolean = true,
) : SettingsStore

@OptIn(ExperimentalCoroutinesApi::class)
class PortalViewModelTest {
    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    /** Main 调度器必须共享 runTest 的 scheduler，否则 delay() 无法被 advanceUntilIdle 推进。 */
    private fun TestScope.installMain() {
        Dispatchers.setMain(UnconfinedTestDispatcher(testScheduler))
    }

    private fun viewModel(
        core: PortalCoreBridge = FakeCoreBridge(),
        credentialStore: CredentialStore? = null,
    ) = PortalViewModel(core, bridgeFactory = null, credentialStore = credentialStore)

    /** 等待 Dispatchers.IO 上的真实线程工作落地（runTest 虚拟时钟不会等真实线程）。 */
    private suspend fun TestScope.awaitReal(timeoutMs: Long = 5000, condition: () -> Boolean) {
        withContext(Dispatchers.IO) {
            val deadline = System.currentTimeMillis() + timeoutMs
            while (!condition() && System.currentTimeMillis() < deadline) {
                Thread.sleep(10)
            }
        }
        advanceUntilIdle()
        org.junit.Assert.assertTrue(condition())
    }

    // ── 登录结果映射（缺陷一回归）──────────────────────────────

    @Test
    fun `login success maps to online and clears notice`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.loginResult = LoginResult(LoginOutcome.LOGGED_IN, "登录成功")
        val vm = viewModel(core)

        vm.loginOnce()
        advanceUntilIdle()

        assertEquals(PortalStatus.ONLINE, vm.uiState.value.status)
        assertNull(vm.uiState.value.notice)
    }

    @Test
    fun `stale offline probe before login cannot overwrite confirmed login success`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        // 登录前探测为 OFFLINE（陈旧结果），登录本身确认成功
        core.probeResponses.add(ProbeResult(PortalStatus.OFFLINE, "当前无可用网络"))
        core.loginResult = LoginResult(LoginOutcome.LOGGED_IN, "登录成功")
        val vm = viewModel(core)

        vm.refresh()
        advanceUntilIdle()
        assertEquals(PortalStatus.OFFLINE, vm.uiState.value.status)
        vm.loginOnce()
        advanceUntilIdle()

        assertEquals(PortalStatus.ONLINE, vm.uiState.value.status)
        assertNull(vm.uiState.value.notice)
    }

    @Test
    fun `failed login never fakes online`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.loginResult = LoginResult(LoginOutcome.FAILED, "登录失败")
        val vm = viewModel(core)

        vm.loginOnce()
        advanceUntilIdle()

        assertEquals(PortalStatus.UNKNOWN, vm.uiState.value.status)
        assertTrue(vm.uiState.value.notice != null)
    }

    @Test
    fun `rejected login maps to captive without faking online`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.loginResult = LoginResult(LoginOutcome.LOGIN_REJECTED, "账号或密码被拒绝")
        val vm = viewModel(core)

        vm.loginOnce()
        advanceUntilIdle()

        assertEquals(PortalStatus.CAPTIVE, vm.uiState.value.status)
    }

    @Test
    fun `later successful probe updates ui to online`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.CAPTIVE, "需要完成校园网认证"))
        core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接"))
        val vm = viewModel(core)

        vm.refresh()
        advanceUntilIdle()
        assertEquals(PortalStatus.CAPTIVE, vm.uiState.value.status)
        vm.refresh()
        advanceUntilIdle()

        assertEquals(PortalStatus.ONLINE, vm.uiState.value.status)
    }

    @Test
    fun `unknown probe after confirmed online falls back without faking status`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接"))
        core.probeResponses.add(ProbeResult(PortalStatus.UNKNOWN, "网络状态暂时不可用"))
        val vm = viewModel(core)

        vm.refresh()
        advanceUntilIdle()
        assertEquals(PortalStatus.ONLINE, vm.uiState.value.status)
        vm.refresh()
        advanceUntilIdle()

        assertEquals(PortalStatus.UNKNOWN, vm.uiState.value.status)
    }

    // ── 网络恢复（缺陷二回归）──────────────────────────────

    @Test
    fun `network recovery triggers bounded probe retry until online`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.OFFLINE, "当前无可用网络"))
        core.probeResponses.add(ProbeResult(PortalStatus.UNKNOWN, "网络状态暂时不可用"))
        core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接"))
        val vm = viewModel(core)

        vm.onNetworkAvailable()
        advanceUntilIdle()

        assertEquals(3, core.probeCallCount)
        assertEquals(PortalStatus.ONLINE, vm.uiState.value.status)
    }

    @Test
    fun `network recovery stops retry at conclusive captive result`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.OFFLINE, "当前无可用网络"))
        core.probeResponses.add(ProbeResult(PortalStatus.CAPTIVE, "需要完成校园网认证"))
        val vm = viewModel(core)

        vm.onNetworkAvailable()
        advanceUntilIdle()

        assertEquals(2, core.probeCallCount)
        assertEquals(PortalStatus.CAPTIVE, vm.uiState.value.status)
    }

    @Test
    fun `network recovery retry is bounded when probes keep failing`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        repeat(10) { core.probeResponses.add(ProbeResult(PortalStatus.OFFLINE, "当前无可用网络")) }
        val vm = viewModel(core)

        vm.onNetworkAvailable()
        advanceUntilIdle()

        assertEquals(3, core.probeCallCount) // 有界：最多 NETWORK_RECOVERY_MAX_ATTEMPTS 次
        assertEquals(PortalStatus.OFFLINE, vm.uiState.value.status)
    }

    @Test
    fun `network recovery never submits credentials or triggers login`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.CAPTIVE, "需要完成校园网认证"))
        val vm = viewModel(core)

        vm.onNetworkAvailable()
        advanceUntilIdle()

        assertEquals(0, core.loginCallCount)
        assertTrue(vm.uiState.value.notice == null)
    }

    @Test
    fun `network lost marks offline without touching bridge`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接"))
        val vm = viewModel(core)
        vm.refresh()
        advanceUntilIdle()
        assertEquals(PortalStatus.ONLINE, vm.uiState.value.status)

        vm.onNetworkLost()
        advanceUntilIdle()

        assertEquals(PortalStatus.OFFLINE, vm.uiState.value.status)
        assertEquals(1, core.probeCallCount) // onNetworkLost 不探测
    }

    @Test
    fun `network events are ignored after local session ended`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        val vm = viewModel(core)
        vm.endLocalSession()
        advanceUntilIdle()

        vm.onNetworkAvailable()
        vm.onAppForeground()
        advanceUntilIdle()

        assertEquals(0, core.probeCallCount)
        assertEquals(0, core.loginCallCount)
        assertEquals(PortalStatus.UNKNOWN, vm.uiState.value.status)
    }

    @Test
    fun `network recovery is skipped when core unavailable`() = runTest {
        installMain()
        val vm = viewModel(UnavailablePortalCoreBridge())

        vm.onNetworkAvailable()
        vm.onAppForeground()
        advanceUntilIdle()

        assertEquals(PortalStatus.UNKNOWN, vm.uiState.value.status)
        assertNull(vm.uiState.value.notice) // 静默跳过，不弹出误导性提示
        assertTrue(!vm.uiState.value.isBusy)
    }

    @Test
    fun `foreground resume probes once when core available`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接"))
        val vm = viewModel(core)

        vm.onAppForeground()
        advanceUntilIdle()

        assertEquals(1, core.probeCallCount)
        assertEquals(PortalStatus.ONLINE, vm.uiState.value.status)
    }

    // ── 凭据安全存储（记住密码）──────────────────────────────

    @Test
    fun `remembered credentials are exposed for prefill only and never auto login`() = runTest {
        installMain()
        val store = FakeCredentialStore(StoredCredentials("2024001", "secret"))
        val core = FakeCoreBridge()
        val vm = PortalViewModel(
            core,
            bridgeFactory = { _, _ -> core },
            credentialStore = store,
        )

        assertEquals("2024001", vm.rememberedCredentials?.username)
        assertEquals("secret", vm.rememberedCredentials?.password)
        assertEquals(1, store.loadCallCount)
        assertEquals(0, core.loginCallCount)   // 不自动登录
        assertEquals(0, core.probeCallCount)   // 不自动探测
        assertEquals(0, store.saveCallCount)
    }

    @Test
    fun `successful login with remember checked saves credentials`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.loginResult = LoginResult(LoginOutcome.LOGGED_IN, "登录成功")
        val store = FakeCredentialStore()
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> core },
            credentialStore = store,
        )

        vm.loginWithCredentials("2024001", "secret", remember = true)
        awaitReal { store.saveCallCount > 0 }

        assertEquals(StoredCredentials("2024001", "secret"), store.savedCredentials)
        assertEquals(0, store.clearCallCount)
    }

    @Test
    fun `successful login with remember unchecked clears stored credentials`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.loginResult = LoginResult(LoginOutcome.LOGGED_IN, "登录成功")
        val store = FakeCredentialStore(StoredCredentials("old", "oldpass"))
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> core },
            credentialStore = store,
        )

        vm.loginWithCredentials("2024001", "secret", remember = false)
        awaitReal { store.clearCallCount > 0 }

        assertEquals(0, store.saveCallCount)
        assertEquals(1, store.clearCallCount)
    }

    @Test
    fun `failed login never touches stored credentials`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.loginResult = LoginResult(LoginOutcome.LOGIN_REJECTED, "账号或密码被拒绝")
        val store = FakeCredentialStore(StoredCredentials("old", "oldpass"))
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> core },
            credentialStore = store,
        )

        vm.loginWithCredentials("2024001", "wrong", remember = true)
        awaitReal { core.loginCallCount > 0 }
        advanceUntilIdle()

        assertEquals(0, store.saveCallCount)   // 失败不保存
        assertEquals(0, store.clearCallCount)  // 失败也不清掉旧凭据
    }

    @Test
    fun `blank credentials are rejected before touching store or bridge`() = runTest {
        installMain()
        val store = FakeCredentialStore()
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> FakeCoreBridge() },
            credentialStore = store,
        )

        vm.loginWithCredentials("", "  ", remember = true)
        advanceUntilIdle()

        assertEquals(0, store.saveCallCount)
        assertEquals(0, store.clearCallCount)
    }

    // ── 设置开关与诊断事件 ───────────────────────────────

    @Test
    fun `network recovery probe is skipped when setting disabled`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接"))
        val vm = PortalViewModel(core, settingsStore = FakeSettingsStore(
            autoRefreshOnNetworkRecovery = false,
        ))

        vm.onNetworkAvailable()
        advanceUntilIdle()

        assertEquals(0, core.probeCallCount)
    }

    @Test
    fun `foreground probe is skipped when setting disabled`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接"))
        val vm = PortalViewModel(core, settingsStore = FakeSettingsStore(
            autoRefreshOnForeground = false,
        ))

        vm.onAppForeground()
        advanceUntilIdle()

        assertEquals(0, core.probeCallCount)
    }

    @Test
    fun `toggle setters persist to store and update state`() = runTest {
        installMain()
        val store = FakeSettingsStore()
        val vm = PortalViewModel(FakeCoreBridge(), settingsStore = store)

        vm.setAutoRefreshOnNetworkRecovery(false)
        vm.setAutoRefreshOnForeground(false)

        assertEquals(false, store.autoRefreshOnNetworkRecovery)
        assertEquals(false, store.autoRefreshOnForeground)
        assertEquals(false, vm.uiState.value.autoRefreshOnNetworkRecovery)
        assertEquals(false, vm.uiState.value.autoRefreshOnForeground)
        // 重新构造（模拟重启）后设置保持
        val vm2 = PortalViewModel(FakeCoreBridge(), settingsStore = store)
        assertEquals(false, vm2.uiState.value.autoRefreshOnNetworkRecovery)
        assertEquals(false, vm2.uiState.value.autoRefreshOnForeground)
    }

    @Test
    fun `diagnostic events are recorded for login refresh and network changes`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接"))
        core.loginResult = LoginResult(LoginOutcome.LOGGED_IN, "登录成功")
        val vm = viewModel(core)

        vm.refresh()
        vm.loginOnce()
        vm.onNetworkLost()
        advanceUntilIdle()

        val events = vm.uiState.value.events
        assertTrue(events.any { it.contains("手动刷新") })
        assertTrue(events.any { it.contains("登录结果") })
        assertTrue(events.any { it.contains("网络连接已断开") })
    }

    @Test
    fun `diagnostic events are bounded and never contain credentials`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        repeat(80) { core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接")) }
        core.loginResult = LoginResult(LoginOutcome.LOGGED_IN, "登录成功")
        val store = FakeCredentialStore()
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> core },
            credentialStore = store,
        )

        vm.loginWithCredentials("2024001", "secret", remember = true)
        awaitReal { core.loginCallCount > 0 }
        repeat(60) {
            vm.refresh()
        }
        advanceUntilIdle()

        val events = vm.uiState.value.events
        assertTrue(events.size <= 50)
        assertTrue(events.none { it.contains("secret") || it.contains("2024001") })
    }
}
