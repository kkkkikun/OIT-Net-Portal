package com.oitnetportal.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.oitnetportal.core.AccountInfo
import com.oitnetportal.core.AccountStore
import com.oitnetportal.core.ChaquopyPortalCoreBridge
import com.oitnetportal.core.CoreUnavailableException
import com.oitnetportal.core.LoginOutcome
import com.oitnetportal.core.LoginResult
import com.oitnetportal.core.PortalCoreBridge
import com.oitnetportal.core.PortalStatus
import com.oitnetportal.core.ProbeResult
import com.oitnetportal.core.SettingsStore
import com.oitnetportal.core.StoredAccount
import com.oitnetportal.core.UnavailablePortalCoreBridge
import com.oitnetportal.core.WifiIdentityProvider
import com.oitnetportal.core.toInfo
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import java.time.LocalTime
import java.time.format.DateTimeFormatter

/** 表单预填载荷；nonce 单调递增驱动 Compose 重新预填，saveAccount 反映该账号已在本机保存。 */
data class PrefillCredentials(
    val nonce: Int,
    val accountId: String?,
    val username: String,
    val password: String,
    val saveAccount: Boolean,
)

data class PortalUiState(
    val coreAvailable: Boolean,
    val status: PortalStatus = PortalStatus.UNKNOWN,
    val statusDetail: String,
    val isBusy: Boolean = false,
    val notice: String? = null,
    val autoRefreshOnNetworkRecovery: Boolean = true,
    val autoRefreshOnForeground: Boolean = true,
    /** 会话内诊断事件（新事件在前，有上限），只含脱敏文本。 */
    val events: List<String> = emptyList(),
    /** 已保存账号的脱敏元数据（不含密码）。 */
    val savedAccounts: List<AccountInfo> = emptyList(),
    /** 当前表单预填；null 表示空白表单。 */
    val prefill: PrefillCredentials? = null,
    /** 是否具备读取 Wi-Fi 名称的授权（决定能否按 SSID 自动预选账号）。 */
    val wifiAutoMatchAvailable: Boolean = false,
)

class PortalViewModel(
    initialCore: PortalCoreBridge,
    private val bridgeFactory: (suspend (String, String) -> PortalCoreBridge)? = null,
    private val accountStore: AccountStore? = null,
    private val settingsStore: SettingsStore? = null,
    private val wifiIdentity: WifiIdentityProvider? = null,
) : ViewModel() {
    private var core: PortalCoreBridge = initialCore
    private val operationMutex = Mutex()

    @Volatile
    private var disposed = false

    private var prefillNonce = 0

    private val _uiState = MutableStateFlow(initialUiState(initialCore))
    val uiState: StateFlow<PortalUiState> = _uiState.asStateFlow()

    init {
        recordEvent(
            if (initialCore.isAvailable) "Python 核心桥接已就绪"
            else "应用已启动，等待输入校园网凭据"
        )
    }

    private fun initialUiState(initialCore: PortalCoreBridge): PortalUiState {
        val accounts = accountStore?.loadAccounts().orEmpty()
        return PortalUiState(
            coreAvailable = initialCore.isAvailable,
            statusDetail = when {
                initialCore.isAvailable -> "尚未探测"
                bridgeFactory == null -> "Python 核心桥接尚未接入；当前仅展示界面骨架。"
                else -> "请先输入校园网账号和密码"
            },
            autoRefreshOnNetworkRecovery = settingsStore?.autoRefreshOnNetworkRecovery ?: true,
            autoRefreshOnForeground = settingsStore?.autoRefreshOnForeground ?: true,
            savedAccounts = accounts.map { it.toInfo() },
            prefill = choosePrefill(accounts),
            wifiAutoMatchAvailable = wifiIdentity?.canReadSsid() ?: false,
        )
    }

    /** 启动预选：当前 SSID 绑定账号优先，其次最近使用账号；不做任何自动提交。 */
    private fun choosePrefill(accounts: List<StoredAccount>): PrefillCredentials? {
        if (accounts.isEmpty()) return null
        val currentSsid = wifiIdentity?.currentSsid()
        val matched = accounts.firstOrNull {
            it.boundSsid.isNotBlank() && it.boundSsid == currentSsid
        }
        val chosen = matched
            ?: accounts.firstOrNull { it.id == accountStore?.loadLastUsedId() }
            ?: return null
        return PrefillCredentials(
            nonce = nextNonce(),
            accountId = chosen.id,
            username = chosen.username,
            password = chosen.password,
            saveAccount = true,
        )
    }

    private fun nextNonce(): Int = ++prefillNonce

    fun refresh() = runOperation {
        val result = core.probe()
        applyProbeResult(result)
        recordEvent("手动刷新：${result.status}")
    }

    fun loginOnce() = runOperation {
        applyLoginResult(core.loginOnce())
    }

    fun loginWithCredentials(username: String, password: String, remember: Boolean) {
        if (username.isBlank() || password.isBlank()) {
            _uiState.update { it.copy(notice = "请输入校园网账号和密码") }
            return
        }
        val factory = bridgeFactory
        if (factory == null) {
            _uiState.update {
                it.copy(notice = "Python 核心桥接尚未接入，无法执行该操作。")
            }
            return
        }

        runOperation {
            val adopted = withContext(Dispatchers.IO) {
                var newCore: PortalCoreBridge? = null
                var adopted = false
                try {
                    val createdCore = factory(username, password)
                    newCore = createdCore
                    if (disposed) {
                        releaseCore(createdCore)
                        return@withContext false
                    }

                    val oldCore = core
                    core = createdCore
                    adopted = true
                    if (!disposed) {
                        _uiState.update {
                            it.copy(
                                coreAvailable = true,
                                status = PortalStatus.UNKNOWN,
                                statusDetail = "正在验证校园网登录状态",
                                notice = null,
                            )
                        }
                    }
                    releaseCore(oldCore)
                    true
                } finally {
                    if (!adopted) {
                        newCore?.let { releaseCore(it) }
                    }
                }
            }
            if (adopted && !disposed) {
                val result = core.loginOnce()
                applyLoginResult(result)
                persistAccount(username, password, remember, result)
            }
        }
    }

    fun endLocalSession() = runOperation {
        recordEvent("用户结束本地会话")
        val endingCore = core
        core = UnavailablePortalCoreBridge()
        _uiState.update {
            it.copy(
                coreAvailable = false,
                status = PortalStatus.UNKNOWN,
                statusDetail = "本地认证会话已结束",
                notice = "已关闭应用内 Python 会话；不会向校园网服务器发送退出请求。",
            )
        }
        releaseCore(endingCore)
    }

    // ── 账号管理 ─────────────────────────────────────────────

    /** 用户从下拉列表选择账号：预填表单并记录为最近使用。 */
    fun selectAccount(accountId: String) {
        if (disposed) return
        val store = accountStore ?: return
        val account = store.loadAccounts().firstOrNull { it.id == accountId } ?: return
        store.saveLastUsedId(account.id)
        _uiState.update {
            it.copy(
                prefill = PrefillCredentials(
                    nonce = nextNonce(),
                    accountId = account.id,
                    username = account.username,
                    password = account.password,
                    saveAccount = true,
                ),
            )
        }
        recordEvent("已选择账号：${account.alias.ifBlank { "未命名账号" }}")
    }

    fun deleteAccount(accountId: String) {
        if (disposed) return
        val store = accountStore ?: return
        store.remove(accountId)
        _uiState.update {
            it.copy(
                savedAccounts = store.loadAccounts().map(StoredAccount::toInfo),
                prefill = if (it.prefill?.accountId == accountId) null else it.prefill,
            )
        }
        recordEvent("已删除一个已保存账号")
    }

    /** 更新账号备注与 SSID 绑定（不允许改账密；账密变更走重新登录保存）。 */
    fun updateAccountMeta(accountId: String, alias: String, boundSsid: String) {
        if (disposed) return
        val store = accountStore ?: return
        val account = store.loadAccounts().firstOrNull { it.id == accountId } ?: return
        store.upsert(account.copy(alias = alias.trim(), boundSsid = boundSsid.trim()))
        _uiState.update {
            it.copy(savedAccounts = store.loadAccounts().map(StoredAccount::toInfo))
        }
        recordEvent("已更新账号备注")
    }

    /** 权限申请结果回调：刷新能力标记，授权成功则立即尝试按 SSID 预选。 */
    fun onWifiPermissionResult() {
        if (disposed) return
        val available = wifiIdentity?.canReadSsid() ?: false
        _uiState.update { it.copy(wifiAutoMatchAvailable = available) }
        recordEvent(
            if (available) "已授权 Wi-Fi 名称读取，可按网络自动匹配账号"
            else "未授权 Wi-Fi 名称读取，账号需手动选择"
        )
        if (available) {
            preselectAccountForCurrentSsid()
        }
    }

    /** 按当前 Wi-Fi 预选绑定账号；仅匹配结果与当前预填不同时才覆盖，避免打断输入。 */
    private fun preselectAccountForCurrentSsid() {
        val currentSsid = wifiIdentity?.currentSsid() ?: return
        val matched = accountStore?.loadAccounts()
            ?.firstOrNull { it.boundSsid.isNotBlank() && it.boundSsid == currentSsid }
            ?: return
        if (_uiState.value.prefill?.accountId == matched.id) return
        _uiState.update {
            it.copy(
                prefill = PrefillCredentials(
                    nonce = nextNonce(),
                    accountId = matched.id,
                    username = matched.username,
                    password = matched.password,
                    saveAccount = true,
                ),
            )
        }
        recordEvent("已按当前 Wi-Fi 预选账号：${matched.alias.ifBlank { "未命名账号" }}")
    }

    /**
     * 只有登录确认成功（LOGGED_IN/ALREADY_ONLINE）才按用户选择保存或删除账号；
     * 登录失败一律不动已存账号，避免坏账密覆盖好账密。
     */
    private fun persistAccount(
        username: String,
        password: String,
        remember: Boolean,
        result: LoginResult,
    ) {
        val store = accountStore ?: return
        when (result.outcome) {
            LoginOutcome.ALREADY_ONLINE, LoginOutcome.LOGGED_IN -> {
                if (remember) {
                    val existing = store.loadAccounts().firstOrNull { it.id == username }
                    val currentSsid = wifiIdentity?.currentSsid() ?: ""
                    store.upsert(
                        StoredAccount(
                            id = username,
                            alias = existing?.alias ?: "",
                            username = username,
                            password = password,
                            boundSsid = existing?.boundSsid?.ifBlank { currentSsid }
                                ?: currentSsid,
                        ),
                    )
                    store.saveLastUsedId(username)
                    _uiState.update {
                        it.copy(
                            savedAccounts = store.loadAccounts().map(StoredAccount::toInfo),
                            notice = "账号已保存到本机加密存储",
                        )
                    }
                    recordEvent("已保存账号到本机加密存储")
                } else {
                    store.remove(username)
                    _uiState.update {
                        it.copy(savedAccounts = store.loadAccounts().map(StoredAccount::toInfo))
                    }
                }
            }
            else -> Unit
        }
    }

    private fun applyLoginResult(result: LoginResult) {
        recordEvent("登录结果：${result.outcome}")
        _uiState.update {
            it.copy(
                status = when (result.outcome) {
                    LoginOutcome.ALREADY_ONLINE, LoginOutcome.LOGGED_IN -> PortalStatus.ONLINE
                    LoginOutcome.NO_NETWORK -> PortalStatus.OFFLINE
                    LoginOutcome.NEED_CREDENTIALS -> PortalStatus.CAPTIVE
                    LoginOutcome.CAPTCHA_REQUIRED -> PortalStatus.CAPTIVE
                    LoginOutcome.LOGIN_REJECTED -> PortalStatus.CAPTIVE
                    LoginOutcome.FAILED -> PortalStatus.UNKNOWN
                },
                statusDetail = result.detail.ifBlank { "登录流程已结束" },
                notice = when (result.outcome) {
                    LoginOutcome.ALREADY_ONLINE, LoginOutcome.LOGGED_IN -> null
                    else -> "本次未完成静默登录；人工引导页面尚未实现。"
                },
            )
        }
    }

    private suspend fun releaseCore(target: PortalCoreBridge) {
        val chaquopyBridge = target as? ChaquopyPortalCoreBridge ?: return
        withContext(NonCancellable) {
            try {
                chaquopyBridge.shutdown()
            } catch (_: Exception) {
                // Shutdown failures are deliberately not exposed to UI or logs.
            }
        }
    }

    private fun applyProbeResult(result: ProbeResult) {
        _uiState.update {
            it.copy(
                status = result.status,
                statusDetail = result.detail.ifBlank { defaultStatusDetail(result.status) },
            )
        }
    }

    /** 默认网络断开：直接反映离线，不触碰 Python 桥接。 */
    fun onNetworkLost() {
        if (disposed) return
        recordEvent("网络连接已断开")
        _uiState.update {
            if (it.status == PortalStatus.OFFLINE) it
            else it.copy(status = PortalStatus.OFFLINE, statusDetail = "网络连接已断开")
        }
    }

    /**
     * 默认网络恢复或能力变化：先按 SSID 预选账号，再做一次有界重试的状态探测。
     * 只探测，不提交凭据、不自动登录；本地会话已结束（coreAvailable=false）时静默跳过。
     */
    fun onNetworkAvailable() {
        if (disposed) return
        preselectAccountForCurrentSsid()
        if (!_uiState.value.coreAvailable) return
        if (!_uiState.value.autoRefreshOnNetworkRecovery) return
        recordEvent("检测到网络恢复，开始状态校准")
        runOperation {
            var attempt = 0
            while (attempt < NETWORK_RECOVERY_MAX_ATTEMPTS) {
                attempt++
                val result = core.probe()
                applyProbeResult(result)
                recordEvent("网络恢复校准（第 $attempt 次）：${result.status}")
                // ONLINE/CAPTIVE 是确定结论；OFFLINE/UNKNOWN 可能是门户未就绪的瞬态
                if (result.status == PortalStatus.ONLINE ||
                    result.status == PortalStatus.CAPTIVE ||
                    attempt >= NETWORK_RECOVERY_MAX_ATTEMPTS
                ) {
                    return@runOperation
                }
                delay(NETWORK_RECOVERY_DELAY_MS)
            }
        }
    }

    /** 回到前台：单次状态探测；本地会话已结束或用户关闭时静默跳过。 */
    fun onAppForeground() {
        if (disposed || !_uiState.value.coreAvailable) return
        if (!_uiState.value.autoRefreshOnForeground) return
        refresh()
    }

    fun setAutoRefreshOnNetworkRecovery(enabled: Boolean) {
        if (disposed) return
        settingsStore?.autoRefreshOnNetworkRecovery = enabled
        _uiState.update { it.copy(autoRefreshOnNetworkRecovery = enabled) }
        recordEvent(if (enabled) "已开启网络恢复自动刷新" else "已关闭网络恢复自动刷新")
    }

    fun setAutoRefreshOnForeground(enabled: Boolean) {
        if (disposed) return
        settingsStore?.autoRefreshOnForeground = enabled
        _uiState.update { it.copy(autoRefreshOnForeground = enabled) }
        recordEvent(if (enabled) "已开启前台自动刷新" else "已关闭前台自动刷新")
    }

    /** 记录一条脱敏诊断事件；调用方负责不传入凭据/URL/异常原文。 */
    private fun recordEvent(message: String) {
        val stamped = "${LocalTime.now().format(EVENT_TIME_FORMAT)} $message"
        _uiState.update { it.copy(events = (listOf(stamped) + it.events).take(MAX_EVENTS)) }
    }

    private fun runOperation(operation: suspend () -> Unit) {
        if (disposed || _uiState.value.isBusy) return

        viewModelScope.launch {
            if (!operationMutex.tryLock()) return@launch
            try {
                if (disposed || _uiState.value.isBusy) return@launch
                _uiState.update { it.copy(isBusy = true, notice = null) }
                operation()
            } catch (_: CoreUnavailableException) {
                _uiState.update {
                    it.copy(notice = "Python 核心桥接尚未接入，无法执行该操作。")
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                _uiState.update {
                    it.copy(notice = "操作失败；脱敏诊断接口尚未接入。")
                }
            } finally {
                _uiState.update { it.copy(isBusy = false) }
                operationMutex.unlock()
            }
        }
    }

    override fun onCleared() {
        disposed = true
        // Best-effort cleanup: process death can still prevent this independent IO work.
        CoroutineScope(SupervisorJob() + Dispatchers.IO).launch {
            operationMutex.withLock {
                val finalCore = core
                core = UnavailablePortalCoreBridge()
                releaseCore(finalCore)
            }
        }
    }

    private fun defaultStatusDetail(status: PortalStatus): String = when (status) {
        PortalStatus.UNKNOWN -> "状态未知"
        PortalStatus.ONLINE -> "网络在线"
        PortalStatus.CAPTIVE -> "需要校园网认证"
        PortalStatus.OFFLINE -> "当前无可用网络"
    }

    companion object {
        /** 网络恢复探测：重试次数与间隔均有上界，避免门户未就绪时无限循环。 */
        private const val NETWORK_RECOVERY_MAX_ATTEMPTS = 3
        private const val NETWORK_RECOVERY_DELAY_MS = 2000L

        /** 诊断事件缓冲上限：会话内保留最近 50 条。 */
        private const val MAX_EVENTS = 50
        private val EVENT_TIME_FORMAT = DateTimeFormatter.ofPattern("HH:mm:ss")

        fun factory(
            core: PortalCoreBridge,
            bridgeFactory: (suspend (String, String) -> PortalCoreBridge)? = null,
            accountStore: AccountStore? = null,
            settingsStore: SettingsStore? = null,
            wifiIdentity: WifiIdentityProvider? = null,
        ) = viewModelFactory {
            initializer {
                PortalViewModel(core, bridgeFactory, accountStore, settingsStore, wifiIdentity)
            }
        }
    }
}
