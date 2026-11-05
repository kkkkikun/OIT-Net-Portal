"""移动端反馈桥接契约。

App 侧的反馈提交走 Python 桥接，因此桥接边界必须与认证桥接同等级别脱敏：
只暴露「提交一条反馈」，不暴露收集端地址、异常细节或同学原文。
"""

from __future__ import annotations

import pytest

from oit_portal.mobile_feedback import MobileFeedbackBridge, create_mobile_feedback_bridge


class _FakeSession:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict] = []

    def post(self, url: str, *, json: dict, headers: dict, timeout: float):
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})

        class _Response:
            def __init__(self, code: int) -> None:
                self.status_code = code
                self.text = ""

        return _Response(self.status_code)

    def close(self) -> None:
        return None


def test_submit_sends_payload_to_collector() -> None:
    session = _FakeSession()
    bridge = MobileFeedbackBridge(
        endpoint="http://192.168.1.10:8765/feedback",
        app_version="1.0.0",
        session=session,
    )

    bridge.submit(category="issue", content="连不上", diagnostics="手动刷新：ONLINE")

    assert len(session.calls) == 1
    payload = session.calls[0]["json"]
    assert payload["category"] == "issue"
    assert payload["content"] == "连不上"
    assert payload["diagnostics"] == "手动刷新：ONLINE"
    assert payload["with_diagnostics"] is True
    assert payload["app_version"] == "1.0.0"


def test_submit_without_diagnostics_marks_it_absent() -> None:
    session = _FakeSession()
    bridge = MobileFeedbackBridge(
        endpoint="http://192.168.1.10:8765/feedback",
        app_version="1.0.0",
        session=session,
    )

    bridge.submit(category="other", content="随手写的", diagnostics=None)

    payload = session.calls[0]["json"]
    assert payload["with_diagnostics"] is False
    assert payload["diagnostics"] is None


def test_submit_rejects_blank_content() -> None:
    session = _FakeSession()
    bridge = MobileFeedbackBridge(
        endpoint="http://192.168.1.10:8765/feedback",
        app_version="1.0.0",
        session=session,
    )

    with pytest.raises(ValueError):
        bridge.submit(category="issue", content="   ", diagnostics=None)

    assert session.calls == []


def test_submit_rejects_blank_endpoint() -> None:
    bridge = MobileFeedbackBridge(endpoint="", app_version="1.0.0", session=_FakeSession())

    with pytest.raises(ValueError):
        bridge.submit(category="issue", content="连不上", diagnostics=None)


def test_submit_failure_is_reported_without_leaking_details() -> None:
    class _BrokenSession(_FakeSession):
        def post(self, *args, **kwargs):
            raise OSError("connection refused to 10.0.0.5:8765")

    bridge = MobileFeedbackBridge(
        endpoint="http://192.168.1.10:8765/feedback",
        app_version="1.0.0",
        session=_BrokenSession(),
    )

    with pytest.raises(RuntimeError) as excinfo:
        bridge.submit(category="issue", content="连不上", diagnostics=None)

    assert "10.0.0.5" not in str(excinfo.value)


def test_bridge_close_is_idempotent() -> None:
    bridge = MobileFeedbackBridge(
        endpoint="http://192.168.1.10:8765/feedback",
        app_version="1.0.0",
        session=_FakeSession(),
    )

    bridge.close()
    bridge.close()


def test_create_bridge_validates_endpoint() -> None:
    with pytest.raises(ValueError):
        create_mobile_feedback_bridge("", "1.0.0")


def test_create_bridge_uses_trust_env_disabled_session() -> None:
    bridge = create_mobile_feedback_bridge("http://192.168.1.10:8765/feedback", "1.0.0")

    assert bridge.is_available is True
    bridge.close()


def test_submit_passes_channel_secret_to_request() -> None:
    """通道凭证必须随请求发出，否则对方一开校验就全部投递失败。"""
    session = _FakeSession()
    bridge = MobileFeedbackBridge(
        endpoint="https://example.feishu.cn/base/automation/webhook/abc",
        app_version="1.0.0",
        secret="bearer-token",
        session=session,
    )

    bridge.submit(category="issue", content="连不上", diagnostics=None)

    headers = session.calls[0]["headers"]
    assert headers["Authorization"] == "Bearer bearer-token"


def test_submit_without_secret_sends_no_authorization() -> None:
    session = _FakeSession()
    bridge = MobileFeedbackBridge(
        endpoint="https://example.feishu.cn/base/automation/webhook/abc",
        app_version="1.0.0",
        session=session,
    )

    bridge.submit(category="issue", content="连不上", diagnostics=None)

    assert "Authorization" not in session.calls[0]["headers"]
