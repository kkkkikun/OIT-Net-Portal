"""保活策略：各状态下的下一次等待时长（含抖动、指数退避、深度退避）。"""

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

    def next_delay(self, *, outcome: FlowOutcome, consecutive_failures: int,
                   online_since: float | None, now: float | None = None) -> float:
        now = time.time() if now is None else now
        p, r = self.cfg.probe, self.cfg.retry

        if outcome is FlowOutcome.NO_NETWORK:
            return jittered(p.offline_interval_sec, p.jitter_ratio)

        if outcome in FAILURE_OUTCOMES:
            if consecutive_failures >= r.max_attempts:
                return jittered(r.deep_backoff_sec, p.jitter_ratio)
            expo = r.backoff_base_sec * (2 ** max(0, consecutive_failures - 1))
            return jittered(min(expo, r.backoff_cap_sec), p.jitter_ratio)

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
