"""CLI 入口：oit-portal <status|once|daemon|stop|login-info>"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

from . import __version__
from .auth.flow import AuthFlow, FlowOutcome
from .config import Config, load_config
from .daemon import run_daemon, stop_daemon
from .log import setup_logging
from .paths import AppPaths, resolve_paths
from .probe import probe

# 退出码约定：0 成功在线；1 登录失败/需人工；2 无网络；3 环境/配置错误
EXIT_OK, EXIT_FAIL, EXIT_NO_NETWORK, EXIT_ERROR = 0, 1, 2, 3

_OUTCOME_EXIT = {
    FlowOutcome.ALREADY_ONLINE: EXIT_OK,
    FlowOutcome.LOGGED_IN: EXIT_OK,
    FlowOutcome.NO_NETWORK: EXIT_NO_NETWORK,
    FlowOutcome.NEED_CREDENTIALS: EXIT_FAIL,
    FlowOutcome.CAPTCHA_REQUIRED: EXIT_FAIL,
    FlowOutcome.LOGIN_REJECTED: EXIT_FAIL,
    FlowOutcome.FAILED: EXIT_FAIL,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="oit-portal",
        description="鄂尔多斯应用技术学院校园网静默自动登录与保活（Windows/Termux）",
    )
    parser.add_argument("-V", "--version", action="version", version=__version__)
    parser.add_argument("--config", type=Path, default=None, help="配置文件路径")
    parser.add_argument("--credentials", type=Path, default=None, help="凭据文件路径")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="探测当前网络状态（在线/被劫持/无网络）")
    sub.add_parser("once", help="执行一次完整登录流程")
    sub.add_parser("daemon", help="常驻守护：自动登录 + 保活循环")
    sub.add_parser("stop", help="停止运行中的 daemon")
    sub.add_parser("login-info", help="打印人工登录引导（触发 URL 等）")
    sub.add_parser("capture", help="一键抓包向导：自动发现登录协议并自配置（校内未登录状态运行）")
    return parser


def _load(paths: AppPaths, args: argparse.Namespace) -> Config:
    return load_config(args.config or paths.config,
                       args.credentials or paths.credentials)


def _make_session(cfg: Config) -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = cfg.advanced.user_agent
    session.trust_env = False  # 探测/认证直连，不走系统代理
    return session


def cmd_status(cfg: Config, paths: AppPaths) -> int:
    result = probe(_make_session(cfg), cfg)
    print(str(result))
    return EXIT_OK


def cmd_once(cfg: Config, paths: AppPaths) -> int:
    session = _make_session(cfg)
    from .auth import session_store
    session_store.load(session, paths.session)
    flow = AuthFlow(session, cfg, session_path=paths.session)
    result = flow.ensure_online(allow_password=cfg.password is not None)
    print(f"{result.outcome.value}: {result.detail}")
    return _OUTCOME_EXIT[result.outcome]


def cmd_capture(cfg: Config, paths: AppPaths) -> int:
    from .capture import run_capture
    return run_capture(cfg, paths)


def cmd_login_info(cfg: Config, paths: AppPaths) -> int:
    """验证码/会话失效时的人工兜底引导。"""
    print("== 人工登录引导 ==")
    print("1. 连接校园 WiFi 后，浏览器访问任意 http:// 网站会自动跳到登录页")
    print("   （或直接访问: http://172.16.11.54 或 http://connect.rom.miui.com/generate_204）")
    print("2. 手动完成一次登录后，SSO 会话 cookie 会被 daemon 自动收割复用")
    print(f"3. 持久化会话文件: {paths.session}")
    print(f"4. 日志: {paths.log_file}")
    return EXIT_OK


COMMANDS = {
    "status": cmd_status,
    "once": cmd_once,
    "daemon": lambda cfg, paths: run_daemon(cfg, paths),
    "stop": lambda cfg, paths: stop_daemon(paths),
    "login-info": cmd_login_info,
    "capture": cmd_capture,
}


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    paths = resolve_paths()
    try:
        cfg = _load(paths, args)
    except (ValueError, OSError) as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return EXIT_ERROR

    # daemon 前台手动跑时也能看到日志；计划任务/后台场景 stdout 被丢弃，无副作用
    setup_logging(paths.log_file, console=True)
    return COMMANDS[args.command](cfg, paths)


if __name__ == "__main__":
    sys.exit(main())
