package com.oitnetportal.core

import android.content.Context
import com.kkkkikun.openfeedback.core.DeviceContext
import com.kkkkikun.openfeedback.core.FeedbackClient
import com.kkkkikun.openfeedback.core.FeedbackConfig
import com.kkkkikun.openfeedback.core.FeedbackSubmission
import com.kkkkikun.openfeedback.core.FeedbackType
import com.kkkkikun.openfeedback.core.SubmitOutcome
import kotlinx.coroutines.CancellationException

/**
 * OpenFeedback 实现的反馈提交通道。
 *
 * 与认证桥接分开：反馈提交不需要校园网账号密码，因此不经过
 * [ChaquopyPortalCoreBridge]，也不会因为「还没登录」而不可用。
 *
 * 断网时反馈会存进 SDK 的本机队列，联网后由 WorkManager 自动重试；
 * 提交带 `submissionId`，服务端据此去重，重试不会产生重复记录。
 */
class OpenFeedbackBridge(
    private val client: FeedbackClient,
) : FeedbackBridge {

    @Volatile
    private var closed = false

    override val isAvailable: Boolean
        get() = !closed

    override suspend fun submit(category: String, content: String, diagnostics: String?) {
        if (closed) {
            throw FeedbackUnavailableException()
        }

        val text = content.trim()
        if (text.isEmpty()) {
            throw IllegalArgumentException("内容不能为空")
        }

        // 旧的三类分类直接沿用：服务端同时接受新分类与旧分类。
        val type = categoryFor(category)

        val submission = FeedbackSubmission(
            submissionId = com.kkkkikun.openfeedback.core.newSubmissionId(),
            type = type,
            title = null,
            description = text,
            contact = null,
            device = client.deviceContext,
            // 诊断摘要由宿主过滤后给出，这里只做最后一次长度兜底。
            diagnostics = diagnostics?.trim()?.takeIf { it.isNotEmpty() },
        )

        try {
            when (val outcome = client.submitter.submit(submission)) {
                is SubmitOutcome.Success -> Unit
                is SubmitOutcome.Queued ->
                    // 已存本机，联网后自动重试。这不是失败，同学不该看到报错。
                    Unit
                is SubmitOutcome.Rejected ->
                    throw RuntimeException("反馈提交失败，请稍后重试")
            }
        } catch (cancelled: CancellationException) {
            throw cancelled
        }
    }

    override fun close() {
        closed = true
    }

    companion object {
        /** 这个 App 在 OpenFeedback 服务端注册的应用标识。 */
        const val APP_ID = "oit-net-portal"

        /** 反馈窗口里显示的应用名。 */
        const val APP_NAME = "校园网助手"

        /**
         * 把 App 的分类名映射到服务端分类。
         *
         * 新分类（bug/feature/experience/other）与旧分类
         * （issue/suggestion/other）都能识别，所以回退也不会把反馈发错类。
         */
        fun categoryFor(wire: String): FeedbackType =
            FeedbackType.fromWire(wire) ?: FeedbackType.OTHER

        /**
         * 用服务地址创建反馈桥接。
         *
         * 通道地址为空时返回不可用实现，反馈入口据此提示先配置地址。
         */
        fun create(
            context: Context,
            endpoint: String,
            appVersion: String,
        ): FeedbackBridge {
            val cleaned = endpoint.trim()
            if (cleaned.isEmpty()) return UnavailableFeedbackBridge()
            return try {
                OpenFeedbackBridge(
                    FeedbackClient(
                        context = context.applicationContext,
                        config = FeedbackConfig(
                            appId = APP_ID,
                            endpoint = cleaned,
                            appName = APP_NAME,
                            enableScreenshot = false,
                            enableDeviceInfo = true,
                        ),
                    )
                )
            } catch (_: Exception) {
                UnavailableFeedbackBridge()
            }
        }
    }
}
