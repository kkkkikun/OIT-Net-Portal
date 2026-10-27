package com.oitnetportal.core

import android.content.Context
import com.chaquo.python.PyException
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/**
 * Chaquopy implementation of the Python core bridge.
 *
 * This class is intentionally not wired into MainActivity yet: credential input, secure storage,
 * lifecycle ownership and foreground-service integration are separate steps.
 */
class ChaquopyPortalCoreBridge private constructor(
    private var pythonBridge: PyObject?,
    private val campusNetwork: CampusNetworkBinder,
) : PortalCoreBridge {
    private val pythonMutex = Mutex()

    @Volatile
    private var closed = false

    override val isAvailable: Boolean
        get() = !closed

    override suspend fun probe(): ProbeResult = withContext(Dispatchers.IO) {
        callCoordinator.withSerializedCall {
            campusNetwork.withCampusNetwork {
            pythonMutex.withLock {
                val bridge = pythonBridge
                if (closed || bridge == null) {
                    return@withLock ProbeResult(
                        status = PortalStatus.UNKNOWN,
                        detail = "Python 桥接已关闭",
                    )
                }

                try {
                    val result = bridge.callAttr("probe")
                    try {
                        val status = result.stringValue("status")
                        ProbeResult(
                            status = status.toPortalStatus(),
                            detail = status.toProbeDetail(),
                        )
                    } finally {
                        result.close()
                    }
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: PyException) {
                    ProbeResult(PortalStatus.UNKNOWN, "网络探测暂时不可用")
                } catch (_: Exception) {
                    ProbeResult(PortalStatus.UNKNOWN, "网络探测暂时不可用")
                }
            }
        }
        }
    }

    override suspend fun loginOnce(): LoginResult = withContext(Dispatchers.IO) {
        callCoordinator.withSerializedCall {
            campusNetwork.withCampusNetwork {
            pythonMutex.withLock {
                val bridge = pythonBridge
                if (closed || bridge == null) {
                    return@withLock LoginResult(
                        outcome = LoginOutcome.FAILED,
                        detail = "Python 桥接已关闭",
                    )
                }

                try {
                    val result = bridge.callAttr("login_once")
                    try {
                        val outcome = result.stringValue("outcome")
                        LoginResult(
                            outcome = outcome.toLoginOutcome(),
                            detail = outcome.toLoginDetail(),
                        )
                    } finally {
                        result.close()
                    }
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: PyException) {
                    LoginResult(LoginOutcome.FAILED, "登录失败，请稍后重试")
                } catch (_: Exception) {
                    LoginResult(LoginOutcome.FAILED, "登录失败，请稍后重试")
                }
            }
        }
        }
    }

    override fun captureEngine(): CaptureEngine {
        throw UnsupportedOperationException("Capture 尚未接入")
    }

    override fun daemonEngine(): DaemonEngine {
        throw UnsupportedOperationException("守护引擎尚未接入")
    }

    /** Idempotently closes the Python bridge and releases its Session. */
    suspend fun shutdown() = withContext(Dispatchers.IO) {
        pythonMutex.withLock {
            if (closed) return@withLock
            closed = true
            val bridge = pythonBridge ?: return@withLock
            pythonBridge = null
            try {
                val closeResult: PyObject? = bridge.callAttr("close")
                closeResult?.close()
            } catch (_: Exception) {
                // Shutdown must not expose Python exception details to Android logs or UI.
            } finally {
                try {
                    bridge.close()
                } catch (_: Exception) {
                    // Java-side reference cleanup is also best-effort during shutdown.
                }
            }
        }
    }

    private fun PyObject.stringValue(key: String): String? {
        val value = callAttr("get", key)
        return try {
            value.toJava(String::class.java)
        } finally {
            value.close()
        }
    }

    private fun String?.toPortalStatus(): PortalStatus = when (this) {
        "ONLINE" -> PortalStatus.ONLINE
        "CAPTIVE" -> PortalStatus.CAPTIVE
        "OFFLINE" -> PortalStatus.OFFLINE
        else -> PortalStatus.UNKNOWN
    }

    private fun String?.toProbeDetail(): String = when (toPortalStatus()) {
        PortalStatus.ONLINE -> "网络已连接"
        PortalStatus.CAPTIVE -> "需要完成校园网认证"
        PortalStatus.OFFLINE -> "当前无可用网络"
        PortalStatus.UNKNOWN -> "网络状态暂时不可用"
    }

    private fun String?.toLoginOutcome(): LoginOutcome = when (this) {
        "ALREADY_ONLINE" -> LoginOutcome.ALREADY_ONLINE
        "LOGGED_IN" -> LoginOutcome.LOGGED_IN
        "NO_NETWORK" -> LoginOutcome.NO_NETWORK
        "NEED_CREDENTIALS" -> LoginOutcome.NEED_CREDENTIALS
        "CAPTCHA_REQUIRED" -> LoginOutcome.CAPTCHA_REQUIRED
        "LOGIN_REJECTED" -> LoginOutcome.LOGIN_REJECTED
        else -> LoginOutcome.FAILED
    }

    private fun String?.toLoginDetail(): String = when (toLoginOutcome()) {
        LoginOutcome.ALREADY_ONLINE -> "网络已在线"
        LoginOutcome.LOGGED_IN -> "登录成功"
        LoginOutcome.NO_NETWORK -> "当前无可用网络"
        LoginOutcome.NEED_CREDENTIALS -> "需要更新账号或密码"
        LoginOutcome.CAPTCHA_REQUIRED -> "需要人工完成验证码"
        LoginOutcome.LOGIN_REJECTED -> "账号或密码被拒绝"
        LoginOutcome.FAILED -> "登录失败，请稍后重试"
    }

    companion object {
        private val startupMutex = Mutex()
        private val callCoordinator = PortalCoreCallCoordinator()

        suspend fun create(
            context: Context,
            username: String,
            password: String,
        ): ChaquopyPortalCoreBridge {
            require(username.isNotBlank()) { "账号不能为空" }
            require(password.isNotBlank()) { "密码不能为空" }

            return withContext(Dispatchers.IO) {
                startupMutex.withLock {
                    try {
                        if (!Python.isStarted()) {
                            Python.start(AndroidPlatform(context.applicationContext))
                        }
                        val module = Python.getInstance().getModule("oit_portal.mobile_bridge")
                        try {
                            val bridge = module.callAttr("create_mobile_bridge", username, password)
                            ChaquopyPortalCoreBridge(bridge, CampusNetworkBinder(context))
                        } finally {
                            module.close()
                        }
                    } catch (cancelled: CancellationException) {
                        throw cancelled
                    } catch (_: Exception) {
                        throw CoreUnavailableException()
                    }
                }
            }
        }
    }
}
