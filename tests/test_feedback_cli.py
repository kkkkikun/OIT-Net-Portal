"""``oit-portal feedback`` 子命令契约。

反馈收集与集中处理都通过 CLI 暴露，测试只验证参数解析与命令路由，
不真的起服务（收集端本身在 tests/test_feedback_collector.py 覆盖）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oit_portal.cli import main


def _write_feedback(path: Path, count: int = 2) -> None:
    lines = []
    for index in range(count):
        lines.append(
            json.dumps(
                {
                    "category": "issue" if index % 2 == 0 else "suggestion",
                    "content": f"第 {index + 1} 条反馈",
                    "diagnostics": None,
                    "app_version": "1.0.0",
                    "submitted_at": f"2026-11-0{index + 1}T10:00:00+08:00",
                },
                ensure_ascii=False,
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def test_feedback_list_prints_stored_feedback(tmp_path: Path, capsys) -> None:
    store = tmp_path / "feedback.jsonl"
    _write_feedback(store)

    exit_code = main(["feedback", "list", "--store", str(store)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "第 1 条反馈" in out
    assert "第 2 条反馈" in out
    assert "共 2 条反馈" in out


def test_feedback_list_without_store_reports_empty(tmp_path: Path, capsys) -> None:
    exit_code = main(["feedback", "list", "--store", str(tmp_path / "none.jsonl")])

    assert exit_code == 0
    assert "暂无反馈" in capsys.readouterr().out


def test_feedback_export_writes_markdown(tmp_path: Path) -> None:
    store = tmp_path / "feedback.jsonl"
    _write_feedback(store)
    target = tmp_path / "feedback.md"

    exit_code = main(["feedback", "export", "--store", str(store), "--output", str(target)])

    assert exit_code == 0
    markdown = target.read_text(encoding="utf-8")
    assert "第 1 条反馈" in markdown
    assert "# App 反馈汇总" in markdown


def test_feedback_export_without_output_prints_to_stdout(tmp_path: Path, capsys) -> None:
    store = tmp_path / "feedback.jsonl"
    _write_feedback(store)

    exit_code = main(["feedback", "export", "--store", str(store)])

    assert exit_code == 0
    assert "第 1 条反馈" in capsys.readouterr().out


def test_feedback_export_reports_unwritable_target(tmp_path: Path, capsys) -> None:
    store = tmp_path / "feedback.jsonl"
    _write_feedback(store)
    blocker = tmp_path / "blocker"
    blocker.write_text("这是个文件，不是目录", encoding="utf-8")
    target = blocker / "feedback.md"

    exit_code = main(["feedback", "export", "--store", str(store), "--output", str(target)])

    assert exit_code == 3
    assert "导出失败" in capsys.readouterr().err


def test_feedback_serve_rejects_invalid_port(tmp_path: Path, capsys) -> None:
    exit_code = main(
        ["feedback", "serve", "--store", str(tmp_path / "feedback.jsonl"), "--port", "0"]
    )

    assert exit_code == 3
    assert "端口" in capsys.readouterr().err


def test_feedback_serve_rejects_blank_host(tmp_path: Path, capsys) -> None:
    exit_code = main(
        ["feedback", "serve", "--store", str(tmp_path / "feedback.jsonl"), "--host", " "]
    )

    assert exit_code == 3
    assert "监听地址" in capsys.readouterr().err


def test_feedback_serve_starts_and_serves_feedback(tmp_path: Path) -> None:
    """真的起服务并提交一条，确认 CLI 接线是通的。"""
    import socket
    import threading
    import time
    import urllib.request

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    store = tmp_path / "feedback.jsonl"
    args = [
        "feedback", "serve",
        "--store", str(store),
        "--host", "127.0.0.1",
        "--port", str(port),
    ]

    thread = threading.Thread(target=lambda: main(args), daemon=True)
    thread.start()
    try:
        payload = json.dumps(
            {"category": "issue", "content": "来自 CLI 的反馈", "app_version": "1.0.0"}
        ).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/feedback",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        # 服务是后台线程起的，等它开始监听再提交。
        last_error: Exception | None = None
        for _ in range(50):
            try:
                with urllib.request.urlopen(request, timeout=5) as response:
                    assert response.status == 200
                break
            except OSError as exc:
                last_error = exc
                time.sleep(0.1)
        else:
            raise AssertionError(f"收集端始终没起来：{last_error}")
    finally:
        thread.join(timeout=1)

    assert "来自 CLI 的反馈" in store.read_text(encoding="utf-8")


def test_feedback_subcommand_is_registered() -> None:
    from oit_portal.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["feedback", "list"])

    assert args.command == "feedback"
    assert args.feedback_command == "list"


@pytest.mark.parametrize("command", ["serve", "list", "export"])
def test_all_feedback_subcommands_exist(command: str) -> None:
    from oit_portal.cli import _build_parser

    parser = _build_parser()
    args = parser.parse_args(["feedback", command])

    assert args.feedback_command == command
