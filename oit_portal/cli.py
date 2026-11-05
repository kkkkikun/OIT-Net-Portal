"""CLI 入口：oit-portal <status|once|daemon|stop|login-info|capture|configure>"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import requests

from . import __version__
from .auth.flow import AuthFlow, FlowOutcome
from .config import Config, load_config, save_account
from .daemon import run_daemon, stop_daemon
from .log import setup_logging
from .network import create_session
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
    sub.add_parser("configure", help="交互式设置或更新校园网账号密码")

    feedback = sub.add_parser(
        "feedback",
        help="App 反馈通道：起收集端 / 看已收集的反馈 / 导出清单",
    )
    feedback_sub = feedback.add_subparsers(dest="feedback_command", required=True)

    feedback_serve = feedback_sub.add_parser("serve", help="启动反馈收集端")
    feedback_serve.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    feedback_serve.add_argument("--port", type=int, default=8787, help="监听端口")
    feedback_serve.add_argument("--store", type=Path, default=None, help="反馈落盘文件路径")
    feedback_serve.add_argument("--feishu-webhook", default="", help="可选：飞书 webhook 地址")

    feedback_list = feedback_sub.add_parser("list", help="列出已收集的反馈")
    feedback_list.add_argument("--store", type=Path, default=None, help="反馈落盘文件路径")

    feedback_export = feedback_sub.add_parser("export", help="把反馈导出成 Markdown 清单")
    feedback_export.add_argument("--store", type=Path, default=None, help="反馈落盘文件路径")
    feedback_export.add_argument("--output", type=Path, default=None, help="导出文件路径（默认打印到屏幕）")
    return parser


def _load(paths: AppPaths, args: argparse.Namespace) -> Config:
    return load_config(args.config or paths.config,
                       args.credentials or paths.credentials)


def _make_session(cfg: Config) -> requests.Session:
    return create_session(cfg)


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


def cmd_configure(cfg: Config, paths: AppPaths) -> int:
    import getpass

    try:
        default = f" [{cfg.username}]" if cfg.username else ""
        username = input(f"校园网账号{default}（回车保留）: ").strip() or cfg.username or ""
        password = getpass.getpass("校园网密码（输入不回显，回车保留）: ") or cfg.password or ""
        save_account(paths.config, paths.credentials, username, password)
    except (ValueError, OSError, EOFError, KeyboardInterrupt) as exc:
        print(f"\n配置失败：{exc}", file=sys.stderr)
        return EXIT_ERROR
    print(f"配置已保存：{paths.config}")
    print(f"凭据已保存：{paths.credentials}")
    return EXIT_OK


def _feedback_store_path(paths: AppPaths, override: Path | None) -> Path:
    """反馈落盘文件路径：显式参数优先，其次用户目录下的 feedback.jsonl。"""
    if override is not None:
        return override
    return paths.home / "feedback.jsonl"


def cmd_feedback(cfg: Config, paths: AppPaths, args: argparse.Namespace) -> int:
    """App 反馈通道：起收集端 / 看已收集的反馈 / 导出清单。"""
    from .feedback import (
        FeedbackCollector,
        FeedbackCollectorConfig,
        export_feedback_markdown,
        format_feedback_listing,
        list_feedback_records,
    )

    command = args.feedback_command
    if command == "serve":
        return _cmd_feedback_serve(cfg, paths, args, FeedbackCollector, FeedbackCollectorConfig)
    if command == "list":
        store_path = _feedback_store_path(paths, args.store)
        print(format_feedback_listing(list_feedback_records(store_path)))
        return EXIT_OK
    if command == "export":
        store_path = _feedback_store_path(paths, args.store)
        markdown = export_feedback_markdown(list_feedback_records(store_path))
        output = args.output
        if output is None:
            print(markdown)
            return EXIT_OK
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(markdown, encoding="utf-8")
        except OSError as exc:
            print(f"导出失败：{exc}", file=sys.stderr)
            return EXIT_ERROR
        print(f"已导出 {output}")
        return EXIT_OK
    print("未知的反馈子命令。", file=sys.stderr)
    return EXIT_ERROR


def _cmd_feedback_serve(
    cfg: Config,
    paths: AppPaths,
    args: argparse.Namespace,
    collector_cls,
    config_cls,
) -> int:
    """启动反馈收集端。"""
    from .network import create_session

    host = (args.host or "").strip()
    if not host:
        print("监听地址不能为空。", file=sys.stderr)
        return EXIT_ERROR
    port = args.port
    if not (1 <= int(port) <= 65535):
        print("端口必须是 1-65535 之间的整数。", file=sys.stderr)
        return EXIT_ERROR

    store_path = _feedback_store_path(paths, args.store)
    config = config_cls(
        host=host,
        port=int(port),
        feishu_webhook_url=(args.feishu_webhook or "").strip(),
    )
    collector = collector_cls(
        config=config,
        store_path=store_path,
        session_factory=lambda: create_session(cfg),
    )
    print(f"反馈收集端已启动：http://{host}:{collector.port}/feedback")
    print(f"反馈落盘：{store_path}")
    if config.feishu_webhook_url:
        print("已配置飞书 webhook：每条反馈会同步一份到飞书。")
    else:
        print("未配置飞书 webhook：反馈只落本机。")
    print("按 Ctrl+C 停止。")
    try:
        collector.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        collector.shutdown()
    return EXIT_OK


COMMANDS = {
    "status": cmd_status,
    "once": cmd_once,
    "daemon": lambda cfg, paths: run_daemon(cfg, paths),
    "stop": lambda cfg, paths: stop_daemon(paths),
    "login-info": cmd_login_info,
    "capture": cmd_capture,
    "configure": cmd_configure,
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
    if args.command == "feedback":
        return cmd_feedback(cfg, paths, args)
    return COMMANDS[args.command](cfg, paths)


if __name__ == "__main__":
    sys.exit(main())
