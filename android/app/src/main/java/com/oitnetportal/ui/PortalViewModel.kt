package com.oitnetportal.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.oitnetportal.core.ChaquopyPortalCoreBridge
import com.oitnetportal.core.CoreUnavailableException
import com.oitnetportal.core.CredentialStore
import com.oitnetportal.core.LoginOutcome
import com.oitnetportal.core.LoginResult
import com.oitnetportal.core.PortalCoreBridge
import com.oitnetportal.core.PortalStatus
import com.oitnetportal.core.ProbeResult
import com.oitnetportal.core.SettingsStore
import com.oitnetportal.core.StoredCredentials
import com.oitnetportal.core.UnavailablePortalCoreBridge
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
)

class PortalViewModel(
    initialCore: PortalCoreBridge,
    private val bridgeFactory: (suspend (String, String) -> PortalCoreBridge)? = null,
    private val credentialStore: CredentialStore? = null,
    private val settingsStore: SettingsStore? = null,
) : ViewModel() {
    private var core: PortalCoreBridge = initialCore
    private val operationMutex = Mutex()

    /**
     * 启动时一次性读出的已记住凭据，仅用于表单预填。
     * 不做任何自动提交：是否登录始终由用户显式点击触发。
     */
    val rememberedCredentials: StoredCredentials? = credentialStore?.load()

    @Volatile
    private var disposed = false

    private val _uiState = MutableStateFlow(
        PortalUiState(
            coreAvailable = initialCore.isAvailable,
            statusDetail = when {
                initialCore.isAvailable -> "尚未探测"
                bridgeFactory == null -> "Python 核心桥接尚未接入；当前仅展示界面骨架。"
                else -> "请先输入校园网账号和密码"
            },
            autoRefreshOnNetworkRecovery = settingsStore?.autoRefreshOnNetworkRecovery ?: true,
            autoRefreshOnForeground = settingsStore?.autoRefreshOnForeground ?: true,
        ),
    )
    val uiState: StateFlow<PortalUiState> = _uiState.asStateFlow()

    init {
        recordEvent(
            if (initialCore.isAvailable) "Python 核心桥接已就绪"
            else "应用已启动，等待输入校园网凭据"
        )
    }

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
                persistRememberedCredentials(username, password, remember, result)
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

    /**
     * 只有登录确认成功（LOGGED_IN/ALREADY_ONLINE）才按用户选择保存或清除凭据；
     * 登录失败一律不动已存凭据，避免坏账密覆盖好账密。
     */
    private fun persistRememberedCredentials(
        username: String,
        password: String,
        remember: Boolean,
        result: LoginResult,
    ) {
        val store = credentialStore ?: return
        when (result.outcome) {
            LoginOutcome.ALREADY_ONLINE, LoginOutcome.LOGGED_IN ->
                if (remember) {
                    store.save(StoredCredentials(username, password))
                } else {
                    store.clear()
                }
            else -> Unit
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
     * 默认网络恢复或能力变化：做一次有界重试的状态探测。
     * 只探测，不提交凭据、不自动登录；本地会话已结束（coreAvailable=false）时静默跳过。
     */
    fun onNetworkAvailable() {
        if (disposed || !_uiState.value.coreAvailable) return
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
            credentialStore: CredentialStore? = null,
            settingsStore: SettingsStore? = null,
        ) = viewModelFactory {
            initializer {
                PortalViewModel(core, bridgeFactory, credentialStore, settingsStore)
            }
        }
    }
}
