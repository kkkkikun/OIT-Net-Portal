"""保活策略：间隔、指数退避、深度退避、账密最小间隔保护。"""

from oit_portal.auth.flow import FlowOutcome
from oit_portal.keepalive import KeepalivePolicy, jittered

from conftest import make_config


def policy(**overrides) -> KeepalivePolicy:
    return KeepalivePolicy(make_config(**overrides))


def test_failure_backoff_sequence():
    """失败 1~4 次指数退避；第 5 次（max_attempts）起进入深度退避。"""
    p = policy()
    seq = [p.next_delay(outcome=FlowOutcome.FAILED, consecutive_failures=n,
                        online_since=None) for n in range(1, 6)]
    assert seq == [5, 10, 20, 40, 600]  # 抖动已关闭


def test_backoff_capped():
    """提高 max_attempts 后指数仍受 300s 封顶约束。"""
    p = policy(retry={"max_attempts": 9})
    assert p.next_delay(outcome=FlowOutcome.FAILED, consecutive_failures=8,
                        online_since=None) == 300


def test_deep_backoff_after_max_attempts():
    p = policy()  # max_attempts=5
    assert p.next_delay(outcome=FlowOutcome.LOGIN_REJECTED,
                        consecutive_failures=5, online_since=None) == 600
    assert p.next_delay(outcome=FlowOutcome.FAILED, consecutive_failures=99,
                        online_since=None) == 600


def test_no_network_uses_offline_interval():
    p = policy()
    assert p.next_delay(outcome=FlowOutcome.NO_NETWORK, consecutive_failures=9,
                        online_since=None) == 30


def test_post_online_dense_then_stable():
    p = policy()
    dense = p.next_delay(outcome=FlowOutcome.LOGGED_IN, consecutive_failures=0,
                         online_since=100.0, now=200.0)   # 刚上线 100s < 300s 窗口
    stable = p.next_delay(outcome=FlowOutcome.ALREADY_ONLINE, consecutive_failures=0,
                          online_since=0.0, now=1000.0)   # 早已稳定
    assert dense == 15
    assert stable == 60


def test_allow_password_min_interval():
    p = policy()  # min_relogin_interval_sec=300
    assert p.allow_password(None) is True
    assert p.allow_password(1000.0, now=1100.0) is False   # 100s < 300s
    assert p.allow_password(1000.0, now=1500.0) is True    # 500s >= 300s


def test_jitter_bounds():
    for _ in range(50):
        v = jittered(100, 0.2)
        assert 80 <= v <= 120


def test_burst_interval_after_recovery():
    """网络恢复后 burst 窗口内 5s 探一次（不再是 30s offline 间隔）。"""
    p = policy()
    p.mark_recovery(now=1000.0)
    # 刚 mark_recovery，未上线（online_since=None）→ 应返回 burst 间隔
    delay = p.next_delay(outcome=FlowOutcome.FAILED, consecutive_failures=0,
                        online_since=None, now=1001.0)
    assert delay == 5  # 抖动已关闭


def test_burst_window_expires_to_normal():
    """burst 窗口（默认 60s）过期后回到正常 captive 行为。"""
    p = policy()
    p.mark_recovery(now=1000.0)
    # 65s 后 burst 窗口已过
    delay = p.next_delay(outcome=FlowOutcome.FAILED, consecutive_failures=0,
                        online_since=None, now=1065.0)
    # FAILED 在 FAILURE_OUTCOMES，consecutive_failures=0 → 走 backoff_base_sec=5
    assert delay == 5


def test_burst_resets_on_no_network():
    """重新进入 NO_NETWORK 时 burst 窗口应关闭（避免回 OFFLINE 时还短间隔）。"""
    p = policy()
    p.mark_recovery(now=1000.0)
    assert p.in_burst(now=1000.0) is True
    # 模拟一次 NO_NETWORK
    p.next_delay(outcome=FlowOutcome.NO_NETWORK, consecutive_failures=0,
                 online_since=None, now=1001.0)
    assert p.in_burst(now=1001.0) is False


def test_burst_does_not_apply_when_online():
    """已经在 ONLINE 后即使还在 burst 窗口，也用 post_online 间隔。"""
    p = policy()
    p.mark_recovery(now=1000.0)
    # 已在线（online_since=1005，刚上线）
    delay = p.next_delay(outcome=FlowOutcome.LOGGED_IN, consecutive_failures=0,
                        online_since=1005.0, now=1010.0)
    # 在线 5s < 300s post_online_window → 15s
    assert delay == 15


def test_burst_recovery_then_burst_via_ssid_pattern():
    """完整路径：mark_recovery → burst 探 → 在线 → 正常。"""
    p = policy()
    # T=0: mark_recovery（SSID 触发或 offline→captive 触发）
    p.mark_recovery(now=0.0)
    # T=1: 探 → 还在 captive（online_since=None，FAILED 不在 burst 计数）
    # burst 窗口 60s 内 + online_since=None → 5s
    assert p.next_delay(outcome=FlowOutcome.FAILED, consecutive_failures=0,
                        online_since=None, now=1.0) == 5
    # T=2: 探 → 登录成功（online_since=2）
    p.next_delay(outcome=FlowOutcome.LOGGED_IN, consecutive_failures=0,
                 online_since=2.0, now=2.0)
    # T=10: 在线 8s，post_online 窗口内（< 300s）→ 15s
    assert p.next_delay(outcome=FlowOutcome.ALREADY_ONLINE, consecutive_failures=0,
                        online_since=2.0, now=10.0) == 15
