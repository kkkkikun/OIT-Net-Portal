package com.oitnetportal.core

import com.kkkkikun.openfeedback.core.FeedbackType
import com.oitnetportal.ui.FeedbackCategory
import org.junit.Assert.assertEquals
import org.junit.Test

/**
 * 分类映射的回归测试。
 *
 * 新分类（bug/feature/experience/other）是服务端认的；
 * 旧分类（issue/suggestion/other）是飞书直发时代用的，服务端同样接受。
 * 两套都要能识别，否则回退时反馈会被归错类。
 */
class FeedbackCategoryMappingTest {

    @Test
    fun mapsTheCanonicalCategories() {
        assertEquals(FeedbackType.BUG, OpenFeedbackBridge.categoryFor("bug"))
        assertEquals(FeedbackType.FEATURE, OpenFeedbackBridge.categoryFor("feature"))
        assertEquals(FeedbackType.EXPERIENCE, OpenFeedbackBridge.categoryFor("experience"))
        assertEquals(FeedbackType.OTHER, OpenFeedbackBridge.categoryFor("other"))
    }

    @Test
    fun mapsTheLegacyFeishuCategories() {
        assertEquals(FeedbackType.BUG, OpenFeedbackBridge.categoryFor("issue"))
        assertEquals(FeedbackType.FEATURE, OpenFeedbackBridge.categoryFor("suggestion"))
        assertEquals(FeedbackType.OTHER, OpenFeedbackBridge.categoryFor("other"))
    }

    @Test
    fun fallsBackToOtherForUnknownCategories() {
        assertEquals(FeedbackType.OTHER, OpenFeedbackBridge.categoryFor("nonsense"))
        assertEquals(FeedbackType.OTHER, OpenFeedbackBridge.categoryFor(""))
    }

    @Test
    fun everyAppCategoryMapsToADistinctServerCategory() {
        val mapped = FeedbackCategory.entries.map { OpenFeedbackBridge.categoryFor(it.wireValue) }
        assertEquals(mapped.size, mapped.toSet().size)
        assertEquals(mapped.size, FeedbackCategory.entries.size)
    }
}
