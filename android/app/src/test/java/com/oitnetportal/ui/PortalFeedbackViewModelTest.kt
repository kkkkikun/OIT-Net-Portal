package com.oitnetportal.ui

import com.oitnetportal.core.FeedbackBridge
import com.oitnetportal.core.PortalCoreBridge
import com.oitnetportal.core.UnavailablePortalCoreBridge
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** 记录提交的假反馈桥接：只捕获调用，不触碰 Python/网络。 */
private class FakeFeedbackBridge(
    override val isAvailable: Boolean = true,
    private val failWith: Exception? = null,
) : FeedbackBridge {
    val submissions = mutableListOf<Triple<String, String, String?>>()
    var closeCount = 0
        private set

    override suspend fun submit(category: String, content: String, diagnostics: String?) {
        failWith?.let { throw it }
        submissions.add(Triple(category, content, diagnostics))
    }

    override fun close() {
        closeCount++
    }
}

@OptIn(ExperimentalCoroutinesApi::class)
class PortalFeedbackViewModelTest {

    @Before
    fun setUp() {
        Dispatchers.setMain(UnconfinedTestDispatcher())
    }

    @After
    fun tearDown() {
        Dispatchers.resetMain()
    }

    private fun viewModel(bridge: FeedbackBridge?) = PortalViewModel(
        initialCore = UnavailablePortalCoreBridge(),
        feedbackBridge = bridge,
    )

    @Test
    fun submitFeedback_sendsCategoryContentAndDiagnostics() = runTest {
        val bridge = FakeFeedbackBridge()
        val model = viewModel(bridge)

        model.submitFeedback(FeedbackCategory.BUG, "连不上校园网", withDiagnostics = false)

        assertEquals(1, bridge.submissions.size)
        val (category, content, diagnostics) = bridge.submissions.first()
        assertEquals("bug", category)
        assertEquals("连不上校园网", content)
        assertNull(diagnostics)
    }

    @Test
    fun submitFeedback_attachesSanitizedDiagnosticsWhenRequested() = runTest {
        val bridge = FakeFeedbackBridge()
        val model = viewModel(bridge)

        model.submitFeedback(FeedbackCategory.FEATURE, "建议加个深色模式", withDiagnostics = true)

        val diagnostics = bridge.submissions.first().third
        assertTrue(diagnostics != null && diagnostics.isNotEmpty())
    }

    @Test
    fun submitFeedback_rejectsBlankContent() = runTest {
        val bridge = FakeFeedbackBridge()
        val model = viewModel(bridge)

        model.submitFeedback(FeedbackCategory.OTHER, "   ", withDiagnostics = false)

        assertTrue(bridge.submissions.isEmpty())
        assertEquals("内容不能为空。", model.uiState.value.feedbackError)
    }

    @Test
    fun submitFeedback_reportsUnavailableBridge() = runTest {
        val model = viewModel(bridge = null)

        model.submitFeedback(FeedbackCategory.OTHER, "随手写的", withDiagnostics = false)

        assertEquals("反馈通道尚未配置，无法提交。", model.uiState.value.feedbackError)
    }

    @Test
    fun submitFeedback_reportsFailureWithoutLeakingDetails() = runTest {
        val bridge = FakeFeedbackBridge(failWith = RuntimeException("http://10.0.0.5:8765 refused"))
        val model = viewModel(bridge)

        model.submitFeedback(FeedbackCategory.OTHER, "随手写的", withDiagnostics = false)

        assertEquals("反馈提交失败，请稍后重试。", model.uiState.value.feedbackError)
    }

    @Test
    fun submitFeedback_marksSuccess() = runTest {
        val bridge = FakeFeedbackBridge()
        val model = viewModel(bridge)

        model.submitFeedback(FeedbackCategory.OTHER, "随手写的", withDiagnostics = false)

        assertTrue(model.uiState.value.feedbackSubmitted)
        assertNull(model.uiState.value.feedbackError)
    }

    @Test
    fun submitFeedback_failureDoesNotMarkSuccess() = runTest {
        val bridge = FakeFeedbackBridge(failWith = RuntimeException("boom"))
        val model = viewModel(bridge)

        model.submitFeedback(FeedbackCategory.OTHER, "随手写的", withDiagnostics = false)

        assertTrue(!model.uiState.value.feedbackSubmitted)
        assertEquals("反馈提交失败，请稍后重试。", model.uiState.value.feedbackError)
    }
}

class SanitizeDiagnosticsTest {

    @Test
    fun keepsStatusEvents() {
        val summary = sanitizeDiagnostics(listOf("12:00:01 手动刷新：ONLINE"))

        assertTrue(summary.contains("手动刷新：ONLINE"))
    }

    @Test
    fun dropsLinesWithUrls() {
        val summary = sanitizeDiagnostics(
            listOf("12:00:01 手动刷新：ONLINE", "12:00:02 请求 https://example.com/x?token=abc"),
        )

        assertTrue(summary.contains("手动刷新：ONLINE"))
        assertTrue(!summary.contains("token=abc"))
    }

    @Test
    fun dropsLinesMentioningAccounts() {
        val summary = sanitizeDiagnostics(
            listOf("12:00:01 手动刷新：ONLINE", "12:00:02 已选择账号：张三"),
        )

        assertTrue(summary.contains("手动刷新：ONLINE"))
        assertTrue(!summary.contains("张三"))
    }

    @Test
    fun capsLineCount() {
        val events = (0 until 50).map { "12:00:01 手动刷新：ONLINE $it" }

        val summary = sanitizeDiagnostics(events)

        assertEquals(10, summary.lines().size)
    }

    @Test
    fun emptyInputYieldsEmptySummary() {
        assertEquals("", sanitizeDiagnostics(emptyList()))
    }
}
