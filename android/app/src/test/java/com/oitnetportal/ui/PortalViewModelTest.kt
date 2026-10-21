package com.oitnetportal.ui

import com.oitnetportal.core.AccountStore
import com.oitnetportal.core.CaptureEngine
import com.oitnetportal.core.DaemonEngine
import com.oitnetportal.core.LoginOutcome
import com.oitnetportal.core.LoginResult
import com.oitnetportal.core.PortalCoreBridge
import com.oitnetportal.core.PortalStatus
import com.oitnetportal.core.ProbeResult
import com.oitnetportal.core.SettingsStore
import com.oitnetportal.core.StoredAccount
import com.oitnetportal.core.UnavailablePortalCoreBridge
import com.oitnetportal.core.WifiIdentityProvider
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

/** 内存假账号存储：记录写操作次数，不触碰 Keystore/磁盘。 */
private class FakeAccountStore(
    initial: List<StoredAccount> = emptyList(),
    private var lastUsedId: String? = null,
) : AccountStore {
    private val accounts = initial.toMutableList()
    var upsertCount = 0
        private set
    var removeCount = 0
        private set

    override fun loadAccounts(): List<StoredAccount> = accounts.toList()

    override fun upsert(account: StoredAccount) {
        upsertCount++
        accounts.removeAll { it.id == account.id }
        accounts.add(account)
    }

    override fun remove(accountId: String) {
        removeCount++
        accounts.removeAll { it.id == accountId }
        if (lastUsedId == accountId) lastUsedId = null
    }

    override fun loadLastUsedId(): String? = lastUsedId

    override fun saveLastUsedId(accountId: String) {
        lastUsedId = accountId
    }

    fun saved(id: String): StoredAccount? = accounts.firstOrNull { it.id == id }

    fun size(): Int = accounts.size
}

/** 可控的假 Wi-Fi 标识来源。 */
private class FakeWifiIdentityProvider(
    var ssid: String? = null,
    var canRead: Boolean = false,
) : WifiIdentityProvider {
    override fun canReadSsid(): Boolean = canRead
    override fun currentSsid(): String? = if (canRead) ssid else null
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
        accountStore: AccountStore? = null,
        settingsStore: SettingsStore? = null,
        wifiIdentity: WifiIdentityProvider? = null,
    ) = PortalViewModel(
        core,
        bridgeFactory = null,
        accountStore = accountStore,
        settingsStore = settingsStore,
        wifiIdentity = wifiIdentity,
    )

    /** 等待 Dispatchers.IO 上的真实线程工作落地（runTest 虚拟时钟不会等真实线程）。 */
    private suspend fun TestScope.awaitReal(timeoutMs: Long = 5000, condition: () -> Boolean) {
        withContext(Dispatchers.IO) {
            val deadline = System.currentTimeMillis() + timeoutMs
            while (!condition() && System.currentTimeMillis() < deadline) {
                Thread.sleep(10)
            }
        }
        advanceUntilIdle()
        assertTrue(condition())
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

        assertEquals(3, core.probeCallCount)
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
        assertEquals(1, core.probeCallCount)
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
        assertNull(vm.uiState.value.notice)
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

    // ── 设置开关与诊断事件 ───────────────────────────────

    @Test
    fun `network recovery probe is skipped when setting disabled`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接"))
        val vm = viewModel(core, settingsStore = FakeSettingsStore(
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
        val vm = viewModel(core, settingsStore = FakeSettingsStore(
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
        val vm = viewModel(FakeCoreBridge(), settingsStore = store)

        vm.setAutoRefreshOnNetworkRecovery(false)
        vm.setAutoRefreshOnForeground(false)

        assertEquals(false, store.autoRefreshOnNetworkRecovery)
        assertEquals(false, store.autoRefreshOnForeground)
        assertEquals(false, vm.uiState.value.autoRefreshOnNetworkRecovery)
        assertEquals(false, vm.uiState.value.autoRefreshOnForeground)
        val vm2 = viewModel(FakeCoreBridge(), settingsStore = store)
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

    // ── 多账号管理 ──────────────────────────────────────

    private fun studentAccount() = StoredAccount(
        id = "2024001", alias = "学生号", username = "2024001",
        password = "stu-secret", boundSsid = "OIT-XUESHENG",
    )

    private fun teacherAccount() = StoredAccount(
        id = "t1001", alias = "教师号", username = "t1001",
        password = "tea-secret", boundSsid = "OIT-JIAOSHI",
    )

    @Test
    fun `startup preselects account bound to current ssid without auto login`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        val store = FakeAccountStore(listOf(studentAccount(), teacherAccount()))
        val wifi = FakeWifiIdentityProvider(ssid = "OIT-JIAOSHI", canRead = true)
        val vm = viewModel(core, accountStore = store, wifiIdentity = wifi)

        val prefill = vm.uiState.value.prefill
        assertEquals("t1001", prefill?.username)
        assertEquals("tea-secret", prefill?.password)
        assertEquals(true, prefill?.saveAccount)
        assertEquals(2, vm.uiState.value.savedAccounts.size)
        assertEquals(true, vm.uiState.value.wifiAutoMatchAvailable)
        assertEquals(0, core.loginCallCount)   // 不自动登录
        assertEquals(0, core.probeCallCount)   // 不自动探测
        // 状态中的账号元数据不含密码字段
        assertTrue(vm.uiState.value.savedAccounts.none { it.toString().contains("secret") })
    }

    @Test
    fun `startup falls back to last used account when ssid unavailable`() = runTest {
        installMain()
        val store = FakeAccountStore(
            listOf(studentAccount(), teacherAccount()),
            lastUsedId = "2024001",
        )
        val wifi = FakeWifiIdentityProvider(ssid = null, canRead = false)
        val vm = viewModel(FakeCoreBridge(), accountStore = store, wifiIdentity = wifi)

        assertEquals("2024001", vm.uiState.value.prefill?.username)
        assertEquals(false, vm.uiState.value.wifiAutoMatchAvailable)
    }

    @Test
    fun `startup prefill is empty when no accounts saved`() = runTest {
        installMain()
        val vm = viewModel(FakeCoreBridge(), accountStore = FakeAccountStore())

        assertNull(vm.uiState.value.prefill)
        assertTrue(vm.uiState.value.savedAccounts.isEmpty())
    }

    @Test
    fun `selectAccount prefills form and marks last used`() = runTest {
        installMain()
        val store = FakeAccountStore(listOf(studentAccount(), teacherAccount()))
        val vm = viewModel(FakeCoreBridge(), accountStore = store)

        vm.selectAccount("t1001")

        val prefill = vm.uiState.value.prefill
        assertEquals("t1001", prefill?.username)
        assertEquals("tea-secret", prefill?.password)
        assertEquals("t1001", store.loadLastUsedId())
    }

    @Test
    fun `network change preselects ssid bound account`() = runTest {
        installMain()
        val store = FakeAccountStore(listOf(studentAccount(), teacherAccount()))
        val wifi = FakeWifiIdentityProvider(ssid = null, canRead = true)
        val vm = viewModel(UnavailablePortalCoreBridge(), accountStore = store, wifiIdentity = wifi)
        assertNull(vm.uiState.value.prefill)

        wifi.ssid = "OIT-XUESHENG"
        vm.onNetworkAvailable()
        advanceUntilIdle()

        assertEquals("2024001", vm.uiState.value.prefill?.username)
        assertTrue(vm.uiState.value.events.any { it.contains("按当前 Wi-Fi 预选账号") })
    }

    @Test
    fun `successful login with remember saves account bound to current ssid`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.loginResult = LoginResult(LoginOutcome.LOGGED_IN, "登录成功")
        val store = FakeAccountStore()
        val wifi = FakeWifiIdentityProvider(ssid = "OIT-XUESHENG", canRead = true)
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> core },
            accountStore = store,
            wifiIdentity = wifi,
        )

        vm.loginWithCredentials("2024001", "stu-secret", remember = true)
        awaitReal { core.loginCallCount > 0 }

        val saved = store.saved("2024001")
        assertEquals("stu-secret", saved?.password)
        assertEquals("OIT-XUESHENG", saved?.boundSsid)
        assertEquals("2024001", store.loadLastUsedId())
        assertEquals(1, vm.uiState.value.savedAccounts.size)
        assertEquals(0, store.removeCount)
    }

    @Test
    fun `repeat login with same username updates instead of duplicating`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.loginResult = LoginResult(LoginOutcome.LOGGED_IN, "登录成功")
        val store = FakeAccountStore()
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> core },
            accountStore = store,
        )

        vm.loginWithCredentials("2024001", "old-pass", remember = true)
        awaitReal { store.saved("2024001") != null }
        vm.loginWithCredentials("2024001", "new-pass", remember = true)
        awaitReal { store.upsertCount >= 2 }

        assertEquals(1, store.size())
        assertEquals("new-pass", store.saved("2024001")?.password)
    }

    @Test
    fun `successful login without remember removes matching saved account`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.loginResult = LoginResult(LoginOutcome.LOGGED_IN, "登录成功")
        val store = FakeAccountStore(listOf(studentAccount()))
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> core },
            accountStore = store,
        )

        vm.loginWithCredentials("2024001", "stu-secret", remember = false)
        awaitReal { store.removeCount > 0 }

        assertNull(store.saved("2024001"))
        assertTrue(vm.uiState.value.savedAccounts.isEmpty())
    }

    @Test
    fun `failed login never touches saved accounts`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        core.loginResult = LoginResult(LoginOutcome.LOGIN_REJECTED, "账号或密码被拒绝")
        val store = FakeAccountStore(listOf(studentAccount()))
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> core },
            accountStore = store,
        )

        vm.loginWithCredentials("2024001", "wrong", remember = true)
        awaitReal { core.loginCallCount > 0 }
        advanceUntilIdle()

        assertEquals(0, store.upsertCount)
        assertEquals(0, store.removeCount)
        assertEquals("stu-secret", store.saved("2024001")?.password)
    }

    @Test
    fun `blank credentials are rejected before touching store or bridge`() = runTest {
        installMain()
        val store = FakeAccountStore()
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> FakeCoreBridge() },
            accountStore = store,
        )

        vm.loginWithCredentials("", "  ", remember = true)
        advanceUntilIdle()

        assertEquals(0, store.upsertCount)
        assertEquals(0, store.removeCount)
    }

    @Test
    fun `deleteAccount removes account and clears prefill when selected`() = runTest {
        installMain()
        val store = FakeAccountStore(listOf(studentAccount(), teacherAccount()))
        val vm = viewModel(FakeCoreBridge(), accountStore = store)
        vm.selectAccount("2024001")
        assertEquals("2024001", vm.uiState.value.prefill?.accountId)

        vm.deleteAccount("2024001")

        assertEquals(1, vm.uiState.value.savedAccounts.size)
        assertNull(vm.uiState.value.prefill)
        assertNull(store.saved("2024001"))
    }

    @Test
    fun `updateAccountMeta edits alias and ssid binding without touching password`() = runTest {
        installMain()
        val store = FakeAccountStore(listOf(studentAccount()))
        val vm = viewModel(FakeCoreBridge(), accountStore = store)

        vm.updateAccountMeta("2024001", "主账号", "OIT-GONGQIN")

        val updated = store.saved("2024001")
        assertEquals("主账号", updated?.alias)
        assertEquals("OIT-GONGQIN", updated?.boundSsid)
        assertEquals("stu-secret", updated?.password)
        assertEquals("主账号", vm.uiState.value.savedAccounts.first().alias)
    }

    @Test
    fun `diagnostic events are bounded and never contain credentials`() = runTest {
        installMain()
        val core = FakeCoreBridge()
        repeat(80) { core.probeResponses.add(ProbeResult(PortalStatus.ONLINE, "网络已连接")) }
        core.loginResult = LoginResult(LoginOutcome.LOGGED_IN, "登录成功")
        val store = FakeAccountStore()
        val vm = PortalViewModel(
            UnavailablePortalCoreBridge(),
            bridgeFactory = { _, _ -> core },
            accountStore = store,
        )

        vm.loginWithCredentials("2024001", "secret", remember = true)
        awaitReal { core.loginCallCount > 0 }
        vm.selectAccount("2024001")
        repeat(60) { vm.refresh() }
        advanceUntilIdle()

        val events = vm.uiState.value.events
        assertTrue(events.size <= 50)
        assertTrue(events.none { it.contains("secret") || it.contains("2024001") })
    }
}
