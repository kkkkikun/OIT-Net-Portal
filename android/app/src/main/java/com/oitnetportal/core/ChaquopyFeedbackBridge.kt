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
 * Chaquopy 实现的反馈提交通道。
 *
 * 与认证桥接分开：反馈提交不需要校园网账号密码，因此不经过
 * [ChaquopyPortalCoreBridge]，也不会因为「还没登录」而不可用。
 */
class ChaquopyFeedbackBridge private constructor(
    private var pythonBridge: PyObject?,
) : FeedbackBridge {

    private val pythonMutex = Mutex()

    @Volatile
    private var closed = false

    override val isAvailable: Boolean
        get() = !closed && pythonBridge != null

    override suspend fun submit(category: String, content: String, diagnostics: String?) {
        withContext(Dispatchers.IO) {
            pythonMutex.withLock {
                val bridge = pythonBridge
                if (closed || bridge == null) {
                    throw FeedbackUnavailableException()
                }
                try {
                    val result = bridge.callAttr(
                        "submit",
                        category,
                        content,
                        diagnostics,
                    )
                    result.close()
                } catch (cancelled: CancellationException) {
                    throw cancelled
                } catch (_: PyException) {
                    throw RuntimeException("反馈提交失败，请稍后重试")
                }
            }
        }
    }

    override fun close() {
        closed = true
        val bridge = pythonBridge ?: return
        pythonBridge = null
        try {
            bridge.close()
        } catch (_: Exception) {
            // Python 侧资源释放失败不影响 App 生命周期。
        }
    }

    companion object {
        /**
         * 用通道地址创建反馈桥接。
         *
         * 通道地址为空时返回不可用实现，反馈入口据此提示先配置地址。
         *
         * ViewModel 工厂是同步的，所以这里不用 suspend；Python 运行时的启动
         * 只在首次创建桥接时发生，之后复用已启动的运行时。
         */
        fun create(
            context: Context,
            endpoint: String,
            appVersion: String,
            secret: String = "",
        ): FeedbackBridge {
            val cleaned = endpoint.trim()
            if (cleaned.isEmpty()) return UnavailableFeedbackBridge()
            return try {
                if (!Python.isStarted()) {
                    Python.start(AndroidPlatform(context.applicationContext))
                }
                val module = Python.getInstance().getModule("oit_portal.mobile_feedback")
                try {
                    val bridge = module.callAttr(
                        "create_mobile_feedback_bridge",
                        cleaned,
                        appVersion,
                        secret.trim(),
                    )
                    ChaquopyFeedbackBridge(bridge)
                } finally {
                    module.close()
                }
            } catch (_: Exception) {
                UnavailableFeedbackBridge()
            }
        }
    }
}
