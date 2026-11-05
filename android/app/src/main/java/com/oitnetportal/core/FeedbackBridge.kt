package com.oitnetportal.core

/**
 * 反馈提交通道。
 *
 * 契约保持与认证核心同样的边界：只暴露「提交一条反馈」这一个动作，
 * 实现方负责脱敏与网络细节，失败以异常表达，异常文本不得包含同学原文。
 */
interface FeedbackBridge {

    /** 提交通道是否可用（例如收集端地址已配置）。 */
    val isAvailable: Boolean

    /**
     * 提交一条反馈。
     *
     * @param category 反馈类型：suggestion / issue / other
     * @param content 同学填写的正文
     * @param diagnostics 脱敏后的诊断摘要，可为 null
     */
    suspend fun submit(category: String, content: String, diagnostics: String?)

    /** 释放底层资源。 */
    fun close()
}

/** 收集端地址未配置或通道不可用时的占位实现。 */
class UnavailableFeedbackBridge : FeedbackBridge {
    override val isAvailable: Boolean = false

    override suspend fun submit(category: String, content: String, diagnostics: String?) {
        throw FeedbackUnavailableException()
    }

    override fun close() = Unit
}

class FeedbackUnavailableException : IllegalStateException("反馈通道尚未就绪")
