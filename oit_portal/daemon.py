"""守护进程：单实例锁 + 主循环（探测→登录→按策略休眠）+ 优雅停止。"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

from .auth.flow import AuthFlow, FlowOutcome
from .config import Config
from .keepalive import KeepalivePolicy
from .log import get_logger
from .paths import AppPaths, is_termux
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


def _read_current_ssid() -> str | None:
    """读取当前 WiFi SSID。平台链：Termux → Linux(nmcli/iwgetid)。

    需安装对应工具（termux-api / NetworkManager / wireless-tools）。
    命令缺失 / 异常时返回 None（feature gate 自动失效）。
    """
    if is_termux():
        return _read_ssid_termux()
    if _is_linux():
        return _read_ssid_linux()
    return None


def _is_linux() -> bool:
    """真 Linux（桌面/服务器，systemd 守护场景）。

    Termux 的 sys.platform 也是 "linux"，必须排除。
    """
    return sys.platform == "linux" and not is_termux()


def _ssid_probe_supported() -> bool:
    return is_termux() or _is_linux()


def _read_ssid_termux() -> str | None:
    """Termux：termux-wifi-connectioninfo 输出 JSON，提取 ssid 字段。"""
    try:
        out = subprocess.run(
            ["termux-wifi-connectioninfo"],
            capture_output=True, text=True, timeout=2.0,
        )
        if out.returncode != 0:
            return None
        # 输出形如 {"ssid": "...", ...} 的 JSON
        import json
        info = json.loads(out.stdout)
        return info.get("ssid")
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        return None


def _read_ssid_linux() -> str | None:
    """Linux：nmcli（NetworkManager）优先，iwgetid（wireless-tools）兜底。

    均无 / 失败时返回 None。systemd 服务下 nmcli 走 system bus 通常可用。
    """
    try:
        out = subprocess.run(
            ["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"],
            capture_output=True, text=True, timeout=2.0,
        )
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                active, _, ssid = line.partition(":")
                if active == "yes" and ssid:
                    return ssid
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    try:
        out = subprocess.run(["iwgetid", "-r"],
                             capture_output=True, text=True, timeout=2.0)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _wifi_ssid_watcher(cfg: Config, stop: threading.Event,
                       on_campus_connected: threading.Event) -> None:
    """后台线程：每 3s 轮询 SSID，匹配配置即触发 burst。

    只在 Termux / Linux + 配置了 wifi_ssid 时启用。
    """
    target = cfg.probe.wifi_ssid.strip()
    if not target:
        return
    logger.info("WiFi SSID watcher 已启用（目标 SSID=%r）", target)
    last_seen = False
    while not stop.is_set():
        try:
            ssid = _read_current_ssid()
        except Exception:  # noqa: BLE001
            ssid = None
        now_on_campus = bool(ssid) and (ssid == target)
        if now_on_campus and not last_seen:
            logger.info("检测到校园网 SSID=%r，触发 burst 探测", ssid)
            on_campus_connected.set()
        last_seen = now_on_campus
        # 用 stop.wait 替代 sleep（停止信号能 0 秒中断）
        if stop.wait(3.0):
            break
    logger.info("WiFi SSID watcher 退出")


def run_daemon(cfg: Config, paths: AppPaths) -> int:
    lock = SingleInstanceLock(paths.lock)
    if not lock.acquire():
        # 返回 0 而非 1：systemd Restart=on-failure 下退出码 1 会被当
        # 崩溃无限重启；「已有实例在跑」对服务管理器而言目标已达成。
        # 副作用：手动跑第二个 `oit-portal daemon` 的退出码从 1 变 0（见文档）。
        logger.error("已有 oit-portal 实例在运行（锁 %s），退出", paths.lock)
        return 0
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
    session.trust_env = False  # 探测/认证直连，不走系统代理
    from .auth import session_store
    session_store.load(session, paths.session)

    flow = AuthFlow(session, cfg, session_path=paths.session)
    policy = KeepalivePolicy(cfg)

    # WiFi SSID watcher 触发 burst（Termux / Linux）
    on_campus = threading.Event()
    watcher: threading.Thread | None = None
    if _ssid_probe_supported() and cfg.probe.wifi_ssid.strip():
        watcher = threading.Thread(
            target=_wifi_ssid_watcher,
            args=(cfg, stop, on_campus),
            name="wifi-ssid-watcher",
            daemon=True,
        )
        watcher.start()

    consecutive_failures = 0
    online_since: float | None = None
    last_password_login: float | None = None
    last_keepalive = 0.0
    last_outcome: FlowOutcome | None = None

    while not stop.is_set():
        # SSID 触发：连接上校园网时立即 mark_recovery 进入 burst
        if on_campus.is_set():
            on_campus.clear()
            policy.mark_recovery()

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

        # 状态迁移 + 网络恢复检测 → 触发 burst 窗口
        if outcome != last_outcome:
            if (last_outcome is FlowOutcome.NO_NETWORK
                    and outcome is not FlowOutcome.NO_NETWORK):
                policy.mark_recovery()
                logger.info("网络恢复，开启 burst 探测窗口（%ds，每 %ds 探一次）",
                            cfg.probe.recovery_burst_sec,
                            cfg.probe.recovery_burst_interval_sec)
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
            subprocess.run(["taskkill", "/PID", str(pid)], check=False,
                           capture_output=True)
        else:
            os.kill(pid, signal.SIGTERM)
        logger.info("已向 daemon（pid=%s）发送停止信号", pid)
        return 0
    except (ProcessLookupError, PermissionError, OSError) as exc:
        logger.error("停止失败（pid=%s）：%s", pid, exc)
        return 1
