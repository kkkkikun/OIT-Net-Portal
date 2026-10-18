package com.oitnetportal.core

/**
 * Platform-neutral contracts for the Python core. Implementations must sanitize every
 * detail or message before it crosses this boundary; secrets and raw session data do not belong here.
 */
interface PortalCoreBridge {
    val isAvailable: Boolean

    suspend fun probe(): ProbeResult

    suspend fun loginOnce(): LoginResult

    fun captureEngine(): CaptureEngine

    fun daemonEngine(): DaemonEngine
}

interface CaptureEngine {
    suspend fun capture(onProgress: (CaptureProgress) -> Unit): CaptureResult

    fun requestStop()
}

interface DaemonEngine {
    suspend fun run()

    fun requestStop()

    fun notifyNetworkRecovery()
}

enum class PortalStatus {
    UNKNOWN,
    ONLINE,
    CAPTIVE,
    OFFLINE,
}

data class ProbeResult(
    val status: PortalStatus,
    val detail: String = "",
)

enum class LoginOutcome {
    ALREADY_ONLINE,
    LOGGED_IN,
    NO_NETWORK,
    NEED_CREDENTIALS,
    CAPTCHA_REQUIRED,
    LOGIN_REJECTED,
    FAILED,
}

data class LoginResult(
    val outcome: LoginOutcome,
    val detail: String = "",
)

enum class CaptureStage {
    PROBE,
    DISCOVER,
    ANALYZE,
    LOGIN,
    SAVE,
    COMPLETE,
    FAILED,
}

data class CaptureProgress(
    val stage: CaptureStage,
    val message: String,
)

data class CaptureResult(
    val succeeded: Boolean,
    val message: String,
)

class CoreUnavailableException : IllegalStateException("Python core bridge is not connected")

/** Explicit placeholder: no Python runtime or CLI fallback is hidden behind this implementation. */
class UnavailablePortalCoreBridge : PortalCoreBridge {
    override val isAvailable: Boolean = false

    override suspend fun probe(): ProbeResult = unavailable()

    override suspend fun loginOnce(): LoginResult = unavailable()

    override fun captureEngine(): CaptureEngine = unavailable()

    override fun daemonEngine(): DaemonEngine = unavailable()

    private fun unavailable(): Nothing = throw CoreUnavailableException()
}
