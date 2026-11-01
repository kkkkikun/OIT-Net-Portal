package com.oitnetportal.core

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/** 只负责账号选择，不把账号或秘密写入状态与日志。 */
object BackgroundAccountSelector {
    fun select(
        accounts: List<StoredAccount>,
        lastUsedId: String?,
        currentSsid: String?,
    ): StoredAccount? = accounts.firstOrNull {
        it.boundSsid.isNotBlank() && it.boundSsid == currentSsid
    } ?: accounts.firstOrNull { it.id == lastUsedId }
}

/** 进程内共享重登节流，账号操作导致控制器重建时也不能绕过。 */
class BackgroundReconnectAttemptTracker {
    var lastLoginAttemptAt: Long? = null
    var loginFailures = 0L

    companion object {
        val shared = BackgroundReconnectAttemptTracker()
    }
}

/** 以固定节奏组合单次探测和登录；所有延迟与重试都有上界。 */
class BackgroundReconnectController(
    private val core: PortalCoreBridge,
    private val scope: CoroutineScope,
    private val clock: () -> Long,
    private val attemptTracker: BackgroundReconnectAttemptTracker = BackgroundReconnectAttemptTracker(),
    private val onState: (BackgroundReconnectStatus, String) -> Unit,
    private val onNeedsAttention: (String) -> Unit,
) {
    private val calibrationSignals = Channel<Unit>(Channel.CONFLATED)
    private var worker: Job? = null
    private var probeFailures = 0L

    @Volatile
    private var stopped = false

    val isRunning: Boolean
        get() = !stopped && worker?.isActive == true

    fun start() {
        if (stopped || worker?.isActive == true) return
        onState(BackgroundReconnectStatus.STARTING, "正在启动后台巡检")
        worker = scope.launch { runLoop() }
    }

    fun requestCalibration() {
        if (!stopped) calibrationSignals.trySend(Unit)
    }

    suspend fun stopAndWait() {
        stopped = true
        worker?.cancel()
        worker?.join()
        worker = null
    }

    private suspend fun runLoop() {
        while (!stopped) {
            val waitMillis = handleProbe(safeProbe()) ?: break
            withTimeoutOrNull(waitMillis) { calibrationSignals.receive() }
        }
    }

    private suspend fun safeProbe(): ProbeResult = try {
        core.probe()
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (_: Exception) {
        ProbeResult(PortalStatus.UNKNOWN)
    }

    private suspend fun handleProbe(result: ProbeResult): Long? = when (result.status) {
        PortalStatus.ONLINE -> healthyDelay()
        PortalStatus.OFFLINE -> monitoringDelay(OFFLINE_INTERVAL_MS, "等待网络恢复")
        PortalStatus.UNKNOWN -> backoffDelay(++probeFailures)
        PortalStatus.CAPTIVE -> handleCaptive()
    }

    private suspend fun handleCaptive(): Long? {
        probeFailures = 0
        val remaining = remainingLoginInterval()
        if (remaining > 0) {
            return backoffState(remaining, "等待安全重登间隔")
        }
        attemptTracker.lastLoginAttemptAt = clock()
        // 重登路径必须与普通巡检可区分：否则成功重登的日志和「本来就在线」逐字相同，
        // 事后无法判断是否真的发生过自动重登（2026-11-01 真机验收发现）。
        onState(BackgroundReconnectStatus.MONITORING, "检测到需要校园网认证，正在自动重登")
        return handleLogin(safeLogin())
    }

    private suspend fun safeLogin(): LoginResult = try {
        core.loginOnce()
    } catch (cancelled: CancellationException) {
        throw cancelled
    } catch (_: Exception) {
        LoginResult(LoginOutcome.FAILED)
    }

    private fun handleLogin(result: LoginResult): Long? = when (result.outcome) {
        LoginOutcome.ALREADY_ONLINE -> healthyDelay("自动重登检查完成，校园网已在线")
        LoginOutcome.LOGGED_IN -> healthyDelay("自动重登成功，网络在线")
        LoginOutcome.NO_NETWORK -> monitoringDelay(OFFLINE_INTERVAL_MS, "等待网络恢复")
        LoginOutcome.FAILED -> failedLoginDelay()
        LoginOutcome.NEED_CREDENTIALS -> needsAttention("请更新校园网账号或密码")
        LoginOutcome.CAPTCHA_REQUIRED -> needsAttention("需要人工完成校园网验证")
        LoginOutcome.LOGIN_REJECTED -> needsAttention("校园网账号或密码被拒绝")
    }

    private fun healthyDelay(detail: String = "网络在线，后台巡检中"): Long {
        probeFailures = 0
        attemptTracker.loginFailures = 0
        return monitoringDelay(ONLINE_INTERVAL_MS, detail)
    }

    private fun monitoringDelay(delayMillis: Long, detail: String): Long {
        onState(BackgroundReconnectStatus.MONITORING, detail)
        return delayMillis
    }

    private fun backoffDelay(failures: Long): Long {
        val delayMillis = exponentialBackoff(failures)
        return backoffState(delayMillis, "网络状态未知，等待退避重试")
    }

    private fun failedLoginDelay(): Long? {
        attemptTracker.loginFailures++
        if (attemptTracker.loginFailures >= MAX_LOGIN_FAILURES) {
            return needsAttention("连续登录失败，请人工检查校园网状态")
        }
        val delayMillis = maxOf(
            MIN_RELOGIN_INTERVAL_MS,
            exponentialBackoff(attemptTracker.loginFailures),
            remainingLoginInterval(),
        )
        return backoffState(delayMillis, "登录失败，等待安全重试")
    }

    private fun remainingLoginInterval(): Long {
        val lastAttempt = attemptTracker.lastLoginAttemptAt ?: return 0
        return (MIN_RELOGIN_INTERVAL_MS - (clock() - lastAttempt)).coerceAtLeast(0)
    }

    private fun backoffState(delayMillis: Long, detail: String): Long {
        onState(BackgroundReconnectStatus.BACKOFF, detail)
        return delayMillis
    }

    private fun needsAttention(detail: String): Long? {
        stopped = true
        onState(BackgroundReconnectStatus.NEEDS_ATTENTION, detail)
        onNeedsAttention(detail)
        return null
    }

    private fun exponentialBackoff(failures: Long): Long {
        val shift = (failures - 1).coerceIn(0, MAX_BACKOFF_SHIFT)
        return (INITIAL_BACKOFF_MS shl shift.toInt()).coerceAtMost(MAX_BACKOFF_MS)
    }

    companion object {
        private const val ONLINE_INTERVAL_MS = 60_000L
        private const val OFFLINE_INTERVAL_MS = 30_000L
        private const val MIN_RELOGIN_INTERVAL_MS = 300_000L
        private const val INITIAL_BACKOFF_MS = 5_000L
        private const val MAX_BACKOFF_MS = 300_000L
        private const val MAX_BACKOFF_SHIFT = 6L
        private const val MAX_LOGIN_FAILURES = 3L
    }
}
