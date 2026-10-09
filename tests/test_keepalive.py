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
