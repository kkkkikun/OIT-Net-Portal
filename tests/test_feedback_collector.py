"""反馈收集端与飞书转发契约。

收集端是 HTTP 服务，测试用真实 socket 在回环上起服务，但**不访问外网**：
飞书转发用假 Session 断言请求体，不发真实请求。
"""

from __future__ import annotations

import json as json_module
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from oit_portal.feedback import (
    FeedbackCollectorConfig,
    FeedbackStore,
    build_feedback_payload,
    forward_feedback_to_feishu,
)


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return {"code": 0}


class _FakeSession:
    """记录请求的假 Session：只捕获调用，不发真实网络请求。"""

    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[tuple[str, str, dict]] = []

    def post(self, url: str, *, json: dict, headers: dict, timeout: float) -> _FakeResponse:
        # 参数名 json 遮蔽了模块，所以序列化用 json_module。
        self.calls.append((url, json_module.dumps(json, ensure_ascii=False), headers))
        return _FakeResponse(self.status_code)


def _post(url: str, payload: dict) -> tuple[int, str]:
    request = urllib.request.Request(
        url,
        data=json_module.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


@pytest.fixture()
def collector(tmp_path: Path):
    """起一个回环上的收集端，产出 (base_url, store_path)。"""
    from oit_portal.feedback import FeedbackCollector

    store_path = tmp_path / "feedback.jsonl"
    config = FeedbackCollectorConfig(host="127.0.0.1", port=0)
    collector = FeedbackCollector(config=config, store_path=store_path)
    thread = threading.Thread(target=collector.serve_forever, daemon=True)
    thread.start()
    try:
        yield collector, store_path
    finally:
        collector.shutdown()
        thread.join(timeout=5)


# ── 收集端 ──────────────────────────────────────────────────


def test_collector_accepts_valid_feedback_and_persists_it(collector) -> None:
    instance, store_path = collector
    payload = build_feedback_payload(
        category="issue",
        content="连不上校园网",
        diagnostics="连接状态：需要认证",
        app_version="1.0.0",
    )

    status, body = _post(f"{instance.base_url}/feedback", payload)

    assert status == 200
    assert "ok" in body.lower()
    assert store_path.exists()
    stored = store_path.read_text(encoding="utf-8")
    assert "连不上校园网" in stored
    assert "需要认证" in stored


def test_collector_rejects_missing_content(collector) -> None:
    instance, store_path = collector

    status, _ = _post(
        f"{instance.base_url}/feedback",
        {"category": "issue", "content": "", "app_version": "1.0.0"},
    )

    assert status == 400
    assert not store_path.exists()


def test_collector_rejects_unknown_category(collector) -> None:
    instance, store_path = collector

    status, _ = _post(
        f"{instance.base_url}/feedback",
        {"category": "complaint", "content": "随便", "app_version": "1.0.0"},
    )

    assert status == 400
    assert not store_path.exists()


def test_collector_rejects_unknown_path(collector) -> None:
    instance, _ = collector

    status, _ = _post(f"{instance.base_url}/nope", {"category": "issue", "content": "x"})

    assert status == 404


def test_collector_rejects_non_json_body(collector) -> None:
    instance, store_path = collector

    request = urllib.request.Request(
        f"{instance.base_url}/feedback",
        data=b"not json",
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(request, timeout=5)

    assert excinfo.value.code == 400
    assert not store_path.exists()


def test_collector_rejects_oversized_payload(collector) -> None:
    instance, store_path = collector

    status, _ = _post(
        f"{instance.base_url}/feedback",
        {"category": "other", "content": "x" * (FeedbackCollectorConfig.max_body_bytes + 10),
         "app_version": "1.0.0"},
    )

    assert status == 400
    assert not store_path.exists()


def test_collector_rejects_oversized_payload_reliably(collector) -> None:
    """超大载荷必须稳定拿到 400，而不是偶发的连接错误。

    回归（2026-11-04）：服务端原先在拒绝时**直接应答、不读请求体**，
    客户端还在往这写就被 RST 掉，拿到的是 BrokenPipe/ConnectionReset 而不是 400。
    正常尺寸（≤ 64KB）实测 50/50 稳定，只有「拒绝超大 body」这条路径会翻车。

    用 2MB 载荷把客户端写入缓冲撑满，让竞态必然触发。
    """
    instance, _ = collector
    oversized = "x" * (2 * 1024 * 1024)

    statuses = []
    for _ in range(5):
        status, _ = _post(
            f"{instance.base_url}/feedback",
            {"category": "other", "content": oversized, "app_version": "1.0.0"},
        )
        statuses.append(status)

    assert statuses == [400] * 5


# ── 飞书转发 ────────────────────────────────────────────────


def test_forward_posts_payload_to_feishu_multidimensional_table() -> None:
    """多维表格 webhook：请求体是扁平 JSON，键名即列名。"""
    session = _FakeSession()
    payload = {
        "category": "suggestion",
        "content": "希望能加个开机自启开关",
        "diagnostics": None,
        "app_version": "1.0.0",
        "submitted_at": "2026-11-04T10:00:00+08:00",
    }

    forward_feedback_to_feishu(
        session=session,
        webhook_url="https://example.feishu.cn/base/automation/webhook/abc",
        payload=payload,
    )

    assert len(session.calls) == 1
    url, body, headers = session.calls[0]
    assert url.startswith("https://example.feishu.cn/")
    assert "json" in headers["Content-Type"].lower()
    sent = json_module.loads(body)
    assert sent["content"] == "希望能加个开机自启开关"
    assert sent["category"] == "suggestion"
    assert sent["submitted_at"] == "2026-11-04T10:00:00+08:00"


def test_forward_posts_text_message_to_feishu_group_bot() -> None:
    """群机器人 webhook：请求体是 msg_type + content.text 形态。"""
    session = _FakeSession()
    payload = {
        "category": "issue",
        "content": "登录失败",
        "diagnostics": "登录结果：LOGGED_IN",
        "app_version": "1.0.0",
        "submitted_at": "2026-11-04T10:00:00+08:00",
    }

    forward_feedback_to_feishu(
        session=session,
        webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/abc",
        payload=payload,
    )

    url, body, headers = session.calls[0]
    assert "open-apis/bot" in url
    sent = json_module.loads(body)
    assert sent["msg_type"] == "text"
    text = sent["content"]["text"]
    assert "登录失败" in text
    assert "登录结果：LOGGED_IN" in text


def test_forward_skips_when_webhook_url_is_blank() -> None:
    session = _FakeSession()

    forward_feedback_to_feishu(session=session, webhook_url="", payload={"content": "x"})

    assert session.calls == []


def test_forward_raises_on_http_error() -> None:
    session = _FakeSession(status_code=500)

    with pytest.raises(RuntimeError):
        forward_feedback_to_feishu(
            session=session,
            webhook_url="https://example.feishu.cn/hook/abc",
            payload={"category": "other", "content": "x", "app_version": "1.0.0"},
        )


# ── 存储 ────────────────────────────────────────────────────


def test_store_appends_records_in_order(tmp_path: Path) -> None:
    store = FeedbackStore(tmp_path / "feedback.jsonl")

    store.append(
        build_feedback_payload(
            category="issue", content="第一条", diagnostics=None, app_version="1.0.0"
        )
    )
    store.append(
        build_feedback_payload(
            category="other", content="第二条", diagnostics=None, app_version="1.0.0"
        )
    )

    from oit_portal.feedback import list_feedback_records

    loaded = list_feedback_records(tmp_path / "feedback.jsonl")
    assert [item.content for item in loaded] == ["第一条", "第二条"]
