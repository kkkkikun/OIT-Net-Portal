package com.oitnetportal.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.oitnetportal.core.CoreUnavailableException
import com.oitnetportal.core.LoginOutcome
import com.oitnetportal.core.PortalCoreBridge
import com.oitnetportal.core.PortalStatus
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class PortalUiState(
    val coreAvailable: Boolean,
    val status: PortalStatus = PortalStatus.UNKNOWN,
    val statusDetail: String,
    val isBusy: Boolean = false,
    val notice: String? = null,
)

class PortalViewModel(
    private val core: PortalCoreBridge,
) : ViewModel() {
    private val _uiState = MutableStateFlow(
        PortalUiState(
            coreAvailable = core.isAvailable,
            statusDetail = if (core.isAvailable) {
                "尚未探测"
            } else {
                "Python 核心桥接尚未接入；当前仅展示界面骨架。"
            },
        ),
    )
    val uiState: StateFlow<PortalUiState> = _uiState.asStateFlow()

    fun refresh() = runOperation {
        val result = core.probe()
        _uiState.update {
            it.copy(
                status = result.status,
                statusDetail = result.detail.ifBlank { defaultStatusDetail(result.status) },
            )
        }
    }

    fun loginOnce() = runOperation {
        val result = core.loginOnce()
        _uiState.update {
            it.copy(
                status = when (result.outcome) {
                    LoginOutcome.ALREADY_ONLINE, LoginOutcome.LOGGED_IN -> PortalStatus.ONLINE
                    LoginOutcome.NO_NETWORK -> PortalStatus.OFFLINE
                    else -> it.status
                },
                statusDetail = result.detail.ifBlank { "登录流程已结束" },
                notice = when (result.outcome) {
                    LoginOutcome.ALREADY_ONLINE, LoginOutcome.LOGGED_IN -> null
                    else -> "本次未完成静默登录；人工引导页面尚未实现。"
                },
            )
        }
    }

    private fun runOperation(operation: suspend () -> Unit) {
        if (_uiState.value.isBusy) return

        viewModelScope.launch {
            _uiState.update { it.copy(isBusy = true, notice = null) }
            try {
                operation()
            } catch (_: CoreUnavailableException) {
                _uiState.update {
                    it.copy(notice = "Python 核心桥接尚未接入，无法执行该操作。")
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) {
                // Bridge failures are intentionally collapsed to a UI-safe message.
                _uiState.update {
                    it.copy(notice = "操作失败；脱敏诊断接口尚未接入。")
                }
            } finally {
                _uiState.update { it.copy(isBusy = false) }
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
        fun factory(core: PortalCoreBridge) = viewModelFactory {
            initializer {
                PortalViewModel(core)
            }
        }
    }
}
