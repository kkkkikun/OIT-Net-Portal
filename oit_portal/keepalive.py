"""保活策略：各状态下的下一次等待时长（含抖动、指数退避、深度退避、burst 探测）。"""

from __future__ import annotations

import random
import time

from .auth.flow import FlowOutcome
from .config import Config

# 视为「失败」需要计数退避的结局
FAILURE_OUTCOMES = frozenset({
    FlowOutcome.FAILED,
    FlowOutcome.LOGIN_REJECTED,
    FlowOutcome.CAPTCHA_REQUIRED,
    FlowOutcome.NEED_CREDENTIALS,
})


def jittered(base: float, ratio: float) -> float:
    """base ± ratio 比例抖动。"""
    delta = base * ratio
    return max(1.0, base + random.uniform(-delta, delta))


class KeepalivePolicy:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        # 触发 burst 探测：网络从 OFFLINE 回到 CAPTIVE 时，标记 burst 窗口起点
        # burst 期间 5s 探一次（默认），让连上校园网到登录成功的延迟最小化
        self._recovery_since: float | None = None

    def mark_recovery(self, now: float | None = None) -> None:
        """网络恢复（OFFLINE → 非 OFFLINE）时调用，开启 burst 窗口。"""
        self._recovery_since = time.time() if now is None else now

    def in_burst(self, now: float | None = None) -> bool:
        if self._recovery_since is None:
            return False
        now = time.time() if now is None else now
        return now - self._recovery_since < self.cfg.probe.recovery_burst_sec

    def next_delay(self, *, outcome: FlowOutcome, consecutive_failures: int,
                   online_since: float | None, now: float | None = None) -> float:
        now = time.time() if now is None else now
        p, r = self.cfg.probe, self.cfg.retry

        if outcome is FlowOutcome.NO_NETWORK:
            # 离线时关闭 burst 窗口（下次恢复时再开）
            self._recovery_since = None
            return jittered(p.offline_interval_sec, p.jitter_ratio)

        if outcome in FAILURE_OUTCOMES:
            if consecutive_failures >= r.max_attempts:
                return jittered(r.deep_backoff_sec, p.jitter_ratio)
            expo = r.backoff_base_sec * (2 ** max(0, consecutive_failures - 1))
            return jittered(min(expo, r.backoff_cap_sec), p.jitter_ratio)

        # 离线 → 现在的 CAPTIVE/ONLINE 转换（policy.mark_recovery 由 daemon 触发）
        # burst 期间（recovery 窗口内）用 5s 短间隔
        if self.in_burst(now) and online_since is None:
            return jittered(p.recovery_burst_interval_sec, p.jitter_ratio)

        # ONLINE / LOGGED_IN：刚上线短窗内密集复查，稳定后放慢
        base = p.online_interval_sec
        if online_since is not None and now - online_since < p.post_online_window_sec:
            base = p.post_online_interval_sec
        return jittered(base, p.jitter_ratio)

    def allow_password(self, last_password_login: float | None,
                       now: float | None = None) -> bool:
        """账密重登最小间隔保护（防 cookie 失效风暴）。"""
        if last_password_login is None:
            return True
        now = time.time() if now is None else now
        return now - last_password_login >= self.cfg.retry.min_relogin_interval_sec
