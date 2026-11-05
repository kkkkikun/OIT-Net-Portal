"""反馈通道核心契约。

背景（2026-11-04）：App 要分发给同学们使用，需要一个 App 内的快速反馈入口。
反馈要落到作者本机（自托管收集端），可选同步一份到飞书多维表格。

本模块把三条边界固化成契约：

1. 载荷稳定：字段名与类型对作者侧固定，App 与收集端版本可以错开。
2. 脱敏边界：诊断摘要只允许出现状态类事件，不得带账号/密码/Cookie/完整 URL。
3. 落盘优先：转发飞书是可选增强，飞书抖动不能导致反馈丢失。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oit_portal.feedback import (
    CATEGORY_LABELS,
    FeedbackRecord,
    build_feedback_payload,
    export_feedback_markdown,
    format_feedback_listing,
    list_feedback_records,
    sanitize_diagnostics,
)


# ── 载荷构造 ────────────────────────────────────────────────


def test_payload_has_stable_field_names_and_types() -> None:
    payload = build_feedback_payload(
        category="suggestion",
        content="希望能记住上次连的 Wi-Fi",
        diagnostics=None,
        app_version="1.0.0",
    )

    assert payload["category"] == "suggestion"
    assert payload["content"] == "希望能记住上次连的 Wi-Fi"
    assert payload["with_diagnostics"] is False
    assert payload["diagnostics"] is None
    assert payload["app_version"] == "1.0.0"


def test_payload_marks_diagnostics_presence() -> None:
    payload = build_feedback_payload(
        category="issue",
        content="登录一直失败",
        diagnostics="连接状态：需要认证",
        app_version="1.0.0",
    )

    assert payload["with_diagnostics"] is True
    assert payload["diagnostics"] == "连接状态：需要认证"


def test_payload_rejects_unknown_category() -> None:
    with pytest.raises(ValueError):
        build_feedback_payload(
            category="complaint",
            content="随便写点什么",
            diagnostics=None,
            app_version="1.0.0",
        )


def test_payload_rejects_blank_content() -> None:
    with pytest.raises(ValueError):
        build_feedback_payload(
            category="other",
            content="   \n\t ",
            diagnostics=None,
            app_version="1.0.0",
        )


def test_payload_never_carries_credential_fields() -> None:
    payload = build_feedback_payload(
        category="issue",
        content="连不上",
        diagnostics=None,
        app_version="1.0.0",
    )

    for forbidden in ("username", "password", "cookie", "token", "session"):
        assert forbidden not in payload


# ── 诊断摘要脱敏 ─────────────────────────────────────────────


def test_diagnostics_drop_lines_looking_like_credentials() -> None:
    raw = "\n".join(
        [
            "手动刷新：ONLINE",
            "登录结果：LOGGED_IN",
            "已保存账号到本机加密存储",
            "请求 URL https://open.oit.edu.cn/eportal/portal/page/xyz?token=abcdef",
        ]
    )

    cleaned = sanitize_diagnostics(raw)

    assert "手动刷新：ONLINE" in cleaned
    assert "登录结果：LOGGED_IN" in cleaned
    assert "token=abcdef" not in cleaned
    assert "https://" not in cleaned


def test_diagnostics_drop_lines_mentioning_account_names() -> None:
    raw = "\n".join(
        [
            "手动刷新：ONLINE",
            "已选择账号：张三",
            "已更新账号备注",
        ]
    )

    cleaned = sanitize_diagnostics(raw)

    assert "手动刷新：ONLINE" in cleaned
    assert "张三" not in cleaned
    assert "已选择账号" not in cleaned


def test_diagnostics_cap_line_count_and_length() -> None:
    raw = "\n".join(f"状态事件 {index}：ONLINE" for index in range(50))

    cleaned = sanitize_diagnostics(raw)

    assert len(cleaned.splitlines()) <= 10
    assert all(len(line) <= 200 for line in cleaned.splitlines())


def test_diagnostics_empty_input_yields_empty_text() -> None:
    assert sanitize_diagnostics("") == ""
    assert sanitize_diagnostics(None) == ""


# ── 存储 ────────────────────────────────────────────────────


def test_records_round_trip_through_jsonl(tmp_path: Path) -> None:
    store = tmp_path / "feedback.jsonl"

    record = FeedbackRecord(
        category="issue",
        content="登录失败",
        app_version="1.0.0",
        submitted_at="2026-11-04T10:00:00+08:00",
    )
    store.write_text(record.to_json_line(), encoding="utf-8")

    loaded = list_feedback_records(store)

    assert len(loaded) == 1
    assert loaded[0].content == "登录失败"
    assert loaded[0].category == "issue"


def test_listing_skips_corrupted_lines(tmp_path: Path) -> None:
    store = tmp_path / "feedback.jsonl"
    store.write_text(
        "\n".join(
            [
                json.dumps({"category": "issue", "content": "好的", "app_version": "1.0.0",
                            "submitted_at": "2026-11-04T10:00:00+08:00"}),
                "{ 这行坏了",
                json.dumps({"category": "other", "content": "第二条", "app_version": "1.0.0",
                            "submitted_at": "2026-11-04T11:00:00+08:00"}),
            ]
        ),
        encoding="utf-8",
    )

    loaded = list_feedback_records(store)

    assert [item.content for item in loaded] == ["好的", "第二条"]


def test_listing_missing_file_is_empty(tmp_path: Path) -> None:
    assert list_feedback_records(tmp_path / "nope.jsonl") == []


# ── 展示与导出 ──────────────────────────────────────────────


def test_listing_shows_category_label_and_time(tmp_path: Path) -> None:
    store = tmp_path / "feedback.jsonl"
    store.write_text(
        json.dumps(
            {
                "category": "suggestion",
                "content": "希望支持深色模式",
                "app_version": "1.0.0",
                "submitted_at": "2026-11-04T10:00:00+08:00",
            }
        ),
        encoding="utf-8",
    )

    text = format_feedback_listing(list_feedback_records(store))

    assert CATEGORY_LABELS["suggestion"] in text
    assert "希望支持深色模式" in text
    assert "2026-11-04" in text


def test_export_markdown_contains_every_field(tmp_path: Path) -> None:
    store = tmp_path / "feedback.jsonl"
    store.write_text(
        json.dumps(
            {
                "category": "issue",
                "content": "后台重连没反应",
                "diagnostics": "连接状态：需要认证",
                "app_version": "1.0.0",
                "submitted_at": "2026-11-04T10:00:00+08:00",
            }
        ),
        encoding="utf-8",
    )

    markdown = export_feedback_markdown(list_feedback_records(store))

    assert "后台重连没反应" in markdown
    assert "需要认证" in markdown
    assert "1.0.0" in markdown
    assert "2026-11-04T10:00:00+08:00" in markdown
    assert CATEGORY_LABELS["issue"] in markdown


def test_export_markdown_handles_empty_store(tmp_path: Path) -> None:
    markdown = export_feedback_markdown([])

    assert markdown.strip()
    assert "暂无" in markdown


def test_exported_markdown_escapes_markdown_headings() -> None:
    record = FeedbackRecord(
        category="other",
        content="# 标题注入\n- 列表注入",
        app_version="1.0.0",
        submitted_at="2026-11-04T10:00:00+08:00",
    )

    markdown = export_feedback_markdown([record])

    assert "\n# 标题注入" not in markdown
    assert "\n- 列表注入" not in markdown
