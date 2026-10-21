package com.oitnetportal.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.oitnetportal.core.ChaquopyPortalCoreBridge
import com.oitnetportal.core.CoreUnavailableException
import com.oitnetportal.core.LoginOutcome
import com.oitnetportal.core.LoginResult
import com.oitnetportal.core.PortalCoreBridge
import com.oitnetportal.core.PortalStatus
import com.oitnetportal.core.ProbeResult
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

data class PortalUiState(
    val coreAvailable: Boolean,
    val status: PortalStatus = PortalStatus.UNKNOWN,
    val statusDetail: String,
    val isBusy: Boolean = false,
    val notice: String? = null,
)

class PortalViewModel(
    initialCore: PortalCoreBridge,
    private val bridgeFactory: (suspend (String, String) -> ChaquopyPortalCoreBridge)? = null,
) : ViewModel() {
    private var core: PortalCoreBridge = initialCore
    private val operationMutex = Mutex()

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
        ),
    )
    val uiState: StateFlow<PortalUiState> = _uiState.asStateFlow()

    fun refresh() = runOperation {
        applyProbeResult(core.probe())
    }

    fun loginOnce() = runOperation {
        applyLoginResult(core.loginOnce())
    }

    fun loginWithCredentials(username: String, password: String) {
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
                var newCore: ChaquopyPortalCoreBridge? = null
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
                applyLoginResult(core.loginOnce())
            }
        }
    }

    fun endLocalSession() = runOperation {
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
        runOperation {
            var attempt = 0
            while (attempt < NETWORK_RECOVERY_MAX_ATTEMPTS) {
                attempt++
                val result = core.probe()
                applyProbeResult(result)
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

    /** 回到前台：单次状态探测；本地会话已结束时静默跳过。 */
    fun onAppForeground() {
        if (disposed || !_uiState.value.coreAvailable) return
        refresh()
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

        fun factory(
            core: PortalCoreBridge,
            bridgeFactory: (suspend (String, String) -> ChaquopyPortalCoreBridge)? = null,
        ) = viewModelFactory {
            initializer {
                PortalViewModel(core, bridgeFactory)
            }
        }
    }
}
