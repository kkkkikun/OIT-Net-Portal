"""守护进程：单实例锁 + 主循环（探测→登录→按策略休眠）+ 优雅停止。"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

import requests

from .auth.flow import AuthFlow, FlowOutcome
from .config import Config
from .keepalive import KeepalivePolicy
from .log import get_logger
from .paths import AppPaths
from .probe import ProbeStatus

logger = get_logger()


class SingleInstanceLock:
    """跨平台单实例文件锁（posix: flock / windows: msvcrt.locking）。"""

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self._fh.close()
            self._fh = None
            return False

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._fh.close()
            self._fh = None


def _write_pid(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(os.getpid()), encoding="ascii")
    except OSError:
        pass


def run_daemon(cfg: Config, paths: AppPaths) -> int:
    lock = SingleInstanceLock(paths.lock)
    if not lock.acquire():
        logger.error("已有 oit-portal 实例在运行（锁 %s），退出", paths.lock)
        return 1
    _write_pid(paths.pid)
    logger.info("daemon 启动（pid=%s，配置=%s）", os.getpid(), paths.config)

    stop = threading.Event()

    def _on_signal(signum, _frame):
        logger.info("收到信号 %s，准备退出", signum)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):  # 非主线程 / 平台不支持
            pass

    session = requests.Session()
    session.headers["User-Agent"] = cfg.advanced.user_agent
    from .auth import session_store
    session_store.load(session, paths.session)

    flow = AuthFlow(session, cfg, session_path=paths.session)
    policy = KeepalivePolicy(cfg)

    consecutive_failures = 0
    online_since: float | None = None
    last_password_login: float | None = None
    last_keepalive = 0.0
    last_outcome: FlowOutcome | None = None

    while not stop.is_set():
        allow_password = (cfg.password is not None
                          and policy.allow_password(last_password_login))
        try:
            result = flow.ensure_online(allow_password=allow_password)
        except Exception:  # noqa: BLE001 - 兜底，守护永不崩
            logger.exception("ensure_online 未捕获异常")
            result = None

        now = time.time()
        if result is None:
            consecutive_failures += 1
            outcome = FlowOutcome.FAILED
        else:
            outcome = result.outcome
            if outcome in (FlowOutcome.LOGGED_IN, FlowOutcome.ALREADY_ONLINE):
                if outcome is FlowOutcome.LOGGED_IN and result.via == "password":
                    last_password_login = now
                if online_since is None:
                    online_since = now
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if online_since is not None:
                    logger.warning("网络中断（%s: %s），进入重登流程",
                                   outcome.value, result.detail)
                online_since = None

        # 状态迁移与告警日志
        if outcome != last_outcome:
            level = logger.info
            if consecutive_failures >= cfg.retry.max_attempts:
                level = logger.error
                level("连续失败 %d 次（最新：%s %s）。深度退避 %ss。"
                      "建议：人工浏览器登录一次排查（验证码/密码/协议变化）",
                      consecutive_failures, outcome.value,
                      result.detail if result else "",
                      cfg.retry.deep_backoff_sec)
            else:
                level("状态迁移：%s → %s（%s）",
                      last_outcome.value if last_outcome else "<start>",
                      outcome.value, result.detail if result else "内部异常")
            last_outcome = outcome

        # 空闲流量保活（可选，依抓包结论开启）
        if (cfg.keepalive.traffic_keepalive and cfg.keepalive.keepalive_url
                and online_since is not None
                and now - last_keepalive >= cfg.keepalive.keepalive_interval_sec):
            _traffic_keepalive(session, cfg)
            last_keepalive = now

        delay = policy.next_delay(outcome=outcome,
                                  consecutive_failures=consecutive_failures,
                                  online_since=online_since)
        stop.wait(delay)

    logger.info("daemon 退出")
    lock.release()
    try:
        paths.pid.unlink(missing_ok=True)
    except OSError:
        pass
    return 0


def _traffic_keepalive(session: requests.Session, cfg: Config) -> None:
    try:
        resp = session.get(cfg.keepalive.keepalive_url,
                           timeout=cfg.advanced.timeout_sec)
        logger.debug("流量保活 HTTP %s", resp.status_code)
    except requests.RequestException as exc:
        logger.debug("流量保活失败（忽略）：%s", type(exc).__name__)


def stop_daemon(paths: AppPaths) -> int:
    try:
        pid = int(paths.pid.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        logger.error("未发现运行中的 daemon（无 pid 文件 %s）", paths.pid)
        return 1
    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "/PID", str(pid)], check=False,
                           capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        logger.info("已向 daemon（pid=%s）发送停止信号", pid)
        return 0
    except (ProcessLookupError, PermissionError, OSError) as exc:
        logger.error("停止失败（pid=%s）：%s", pid, exc)
        return 1
