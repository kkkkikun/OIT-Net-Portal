"""反馈直发飞书：请求体形态与凭证校验契约。

背景（2026-11-04）：用户不想一直开着电脑上的一个端口服务，
因此把提交目标从「作者机器上的自托管收集端」改成「飞书 webhook」。

飞书两种 webhook 的请求体形状不同，且都支持凭证校验：

- 群自定义机器人（``/open-apis/bot/``）：``msg_type`` + ``content.text``，
  签名校验用 ``timestamp`` + ``sign``（HMAC-SHA256 后 Base64）。
- 多维表格自动化 webhook：扁平 JSON（键名即列名），凭证校验用 ``Authorization: Bearer``。

另外飞书即使 HTTP 200 也可能返回 ``code != 0``（关键词不匹配、IP 不在白名单等），
只看状态码会把失败当成功。

本模块把这些边界固化成契约。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import pytest

from oit_portal.feedback import (
    build_feedback_payload,
    submit_feedback,
)


class _FakeResponse:
    def __init__(self, status_code: int = 200, body: dict | None = None) -> None:
        self.status_code = status_code
        self.text = json.dumps(body or {}, ensure_ascii=False)
        self._body = body or {}

    def json(self) -> dict:
        return self._body


class _FakeSession:
    def __init__(self, status_code: int = 200, body: dict | None = None) -> None:
        self.status_code = status_code
        self.body = body
        self.calls: list[dict] = []

    def post(self, url: str, *, json: dict, headers: dict, timeout: float) -> _FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeResponse(self.status_code, self.body)


GROUP_BOT_URL = "https://open.feishu.cn/open-apis/bot/v2/hook/abc123"
TABLE_WEBHOOK_URL = "https://example.feishu.cn/base/automation/webhook/def456"


def _payload() -> dict:
    return build_feedback_payload(
        category="issue",
        content="换到 3 号教学楼后连不上",
        diagnostics="手动刷新：CAPTIVE",
        app_version="1.0.0",
    )


# ── 群机器人形态 ────────────────────────────────────────────


def test_group_bot_gets_text_message_body() -> None:
    session = _FakeSession()

    submit_feedback(session=session, endpoint=GROUP_BOT_URL, payload=_payload())

    body = session.calls[0]["json"]
    assert body["msg_type"] == "text"
    text = body["content"]["text"]
    assert "换到 3 号教学楼后连不上" in text
    assert "手动刷新：CAPTIVE" in text


def test_group_bot_body_has_no_flat_payload_keys() -> None:
    """群机器人不吃扁平 JSON，键名必须包在 content.text 里。"""
    session = _FakeSession()

    submit_feedback(session=session, endpoint=GROUP_BOT_URL, payload=_payload())

    body = session.calls[0]["json"]
    assert "content" in body
    assert "category" not in body


def test_group_bot_signature_is_added_when_secret_present() -> None:
    session = _FakeSession()
    secret = "my-secret"

    submit_feedback(
        session=session,
        endpoint=GROUP_BOT_URL,
        payload=_payload(),
        secret=secret,
    )

    body = session.calls[0]["json"]
    assert "timestamp" in body
    assert "sign" in body
    expected = _expected_signature(secret, str(body["timestamp"]))
    assert body["sign"] == expected


def test_group_bot_signature_absent_without_secret() -> None:
    session = _FakeSession()

    submit_feedback(session=session, endpoint=GROUP_BOT_URL, payload=_payload())

    body = session.calls[0]["json"]
    assert "sign" not in body


def _expected_signature(secret: str, timestamp: str) -> str:
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(
        string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


# ── 多维表格形态 ────────────────────────────────────────────


def test_table_webhook_gets_flat_json_body() -> None:
    session = _FakeSession()

    submit_feedback(session=session, endpoint=TABLE_WEBHOOK_URL, payload=_payload())

    body = session.calls[0]["json"]
    assert body["content"] == "换到 3 号教学楼后连不上"
    assert body["diagnostics"] == "手动刷新：CAPTIVE"
    assert body["app_version"] == "1.0.0"


def test_table_webhook_body_uses_chinese_category_label() -> None:
    """分类列要是单选列，值必须是人能看的中文标签。"""
    session = _FakeSession()

    submit_feedback(session=session, endpoint=TABLE_WEBHOOK_URL, payload=_payload())

    body = session.calls[0]["json"]
    assert body["category_label"] == "问题"
    assert body["category"] == "issue"


def test_table_webhook_body_carries_submitted_at() -> None:
    session = _FakeSession()

    submit_feedback(session=session, endpoint=TABLE_WEBHOOK_URL, payload=_payload())

    body = session.calls[0]["json"]
    assert body["submitted_at"]
    assert "T" in body["submitted_at"]


def test_table_webhook_uses_bearer_authorization_when_secret_present() -> None:
    session = _FakeSession()

    submit_feedback(
        session=session,
        endpoint=TABLE_WEBHOOK_URL,
        payload=_payload(),
        secret="bearer-token",
    )

    headers = session.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-token"


def test_table_webhook_has_no_authorization_header_without_secret() -> None:
    session = _FakeSession()

    submit_feedback(session=session, endpoint=TABLE_WEBHOOK_URL, payload=_payload())

    headers = session.calls[0]["headers"]
    assert "Authorization" not in headers


def test_table_webhook_body_has_no_msg_type_key() -> None:
    """多维表格吃扁平 JSON，不能混进群机器人的 msg_type。"""
    session = _FakeSession()

    submit_feedback(session=session, endpoint=TABLE_WEBHOOK_URL, payload=_payload())

    body = session.calls[0]["json"]
    assert "msg_type" not in body
    assert "content" not in body or isinstance(body["content"], str)


# ── 自托管收集端形态 ────────────────────────────────────────


def test_self_hosted_endpoint_keeps_raw_payload() -> None:
    session = _FakeSession()

    submit_feedback(
        session=session,
        endpoint="http://192.168.1.10:8787/feedback",
        payload=_payload(),
    )

    body = session.calls[0]["json"]
    assert body["content"] == "换到 3 号教学楼后连不上"
    assert body["category"] == "issue"
    assert "msg_type" not in body


# ── 失败判定 ────────────────────────────────────────────────


def test_feishu_code_nonzero_is_reported_as_failure() -> None:
    """HTTP 200 但 code != 0（关键词不匹配等）必须算失败。"""
    session = _FakeSession(status_code=200, body={"code": 19021, "msg": "关键词不匹配"})

    with pytest.raises(RuntimeError):
        submit_feedback(session=session, endpoint=GROUP_BOT_URL, payload=_payload())


def test_feishu_code_zero_is_success() -> None:
    session = _FakeSession(status_code=200, body={"code": 0, "msg": "success"})

    submit_feedback(session=session, endpoint=GROUP_BOT_URL, payload=_payload())


def test_failure_message_does_not_leak_payload_content() -> None:
    session = _FakeSession(status_code=200, body={"code": 19021, "msg": "关键词不匹配"})

    with pytest.raises(RuntimeError) as excinfo:
        submit_feedback(session=session, endpoint=GROUP_BOT_URL, payload=_payload())

    assert "换到 3 号教学楼后连不上" not in str(excinfo.value)


def test_http_error_status_is_failure() -> None:
    session = _FakeSession(status_code=500, body={})

    with pytest.raises(RuntimeError):
        submit_feedback(session=session, endpoint=GROUP_BOT_URL, payload=_payload())


def test_non_json_response_is_treated_as_success() -> None:
    """有些通道返回空体；不能因为解析失败就误报失败。"""

    class _EmptyResponse:
        status_code = 200
        text = ""

        def json(self) -> dict:
            raise ValueError("not json")

    class _Session:
        def post(self, url: str, *, json: dict, headers: dict, timeout: float):
            return _EmptyResponse()

    submit_feedback(session=_Session(), endpoint=TABLE_WEBHOOK_URL, payload=_payload())


# ── 载荷 ────────────────────────────────────────────────────


def test_payload_includes_chinese_label_and_submitted_at() -> None:
    payload = build_feedback_payload(
        category="suggestion",
        content="希望能加个深色模式",
        diagnostics=None,
        app_version="1.0.0",
    )

    assert payload["category_label"] == "建议"
    assert payload["submitted_at"]
    assert payload["with_diagnostics"] is False


def test_payload_includes_epoch_seconds_for_date_columns() -> None:
    """多维表格的日期列要数字时间戳，光有 ISO 字符串没法直接当日期列用。"""
    import time

    payload = build_feedback_payload(
        category="other",
        content="随手写的",
        diagnostics=None,
        app_version="1.0.0",
    )

    submitted_ts = payload["submitted_ts"]
    assert isinstance(submitted_ts, int)
    assert abs(submitted_ts - int(time.time())) < 120


def test_payload_still_has_no_credential_fields() -> None:
    payload = build_feedback_payload(
        category="other",
        content="随手写的",
        diagnostics=None,
        app_version="1.0.0",
    )

    for forbidden in ("username", "password", "cookie", "token", "session", "secret"):
        assert forbidden not in payload
