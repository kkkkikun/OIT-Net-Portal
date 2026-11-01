package com.oitnetportal.core

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * 默认网络能力变化闸门。
 *
 * 背景（2026-11-01 红米 K50 Ultra / Android 15 真机验收）：
 * Wi-Fi 的 `onCapabilitiesChanged` 会随信号强度/带宽持续回调，
 * 每次都触发一次门户探测 + 两条诊断事件，几秒一条把 50 条环形缓冲区占满，
 * 关键事件被挤掉。闸门只认「验证状态从未验证翻转为已验证」这一次翻转。
 */
class NetworkValidationGateTest {
    @Test
    fun `first validated state triggers one calibration`() {
        val gate = NetworkValidationGate()

        assertTrue(gate.onValidatedStateChanged(true))
    }

    @Test
    fun `repeated validated capabilities do not trigger again`() {
        val gate = NetworkValidationGate()
        gate.onValidatedStateChanged(true)

        assertFalse(gate.onValidatedStateChanged(true))
        assertFalse(gate.onValidatedStateChanged(true))
    }

    @Test
    fun `unvalidated state never triggers`() {
        val gate = NetworkValidationGate()

        assertFalse(gate.onValidatedStateChanged(false))
        assertFalse(gate.onValidatedStateChanged(false))
    }

    @Test
    fun `validation lost then regained triggers again`() {
        val gate = NetworkValidationGate()
        gate.onValidatedStateChanged(true)

        assertFalse(gate.onValidatedStateChanged(false))
        assertTrue(gate.onValidatedStateChanged(true))
    }

    @Test
    fun `reset re-arms the gate for a new network`() {
        val gate = NetworkValidationGate()
        gate.onValidatedStateChanged(true)

        gate.reset()

        assertTrue(gate.onValidatedStateChanged(true))
    }
}
