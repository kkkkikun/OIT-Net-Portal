"""反馈提交端（App → 收集端）契约。

提交端是 App 内 Python 核心用的通道，测试用假 Session 断言请求形态，
确保：走既有 create_session（trust_env=False）、不重定向到其他主机、不带凭据。
"""

from __future__ import annotations

import pytest

from oit_portal.feedback import submit_feedback


class _FakeResponse:
    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    def json(self) -> dict:
        return {"ok": True}


class _FakeSession:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code
        self.calls: list[dict] = []

    def post(self, url: str, *, json: dict, headers: dict, timeout: float) -> _FakeResponse:
        self.calls.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        return _FakeResponse(self.status_code)


def test_submit_posts_payload_to_collector_endpoint() -> None:
    session = _FakeSession()

    submit_feedback(
        session=session,
        endpoint="http://192.168.1.10:8765/feedback",
        payload={"category": "issue", "content": "登录失败", "app_version": "1.0.0"},
    )

    assert len(session.calls) == 1
    assert session.calls[0]["url"] == "http://192.168.1.10:8765/feedback"
    assert session.calls[0]["json"]["content"] == "登录失败"
    assert session.calls[0]["timeout"] > 0


def test_submit_rejects_blank_endpoint() -> None:
    session = _FakeSession()

    with pytest.raises(ValueError):
        submit_feedback(session=session, endpoint="   ", payload={"content": "x"})

    assert session.calls == []


def test_submit_rejects_non_http_scheme() -> None:
    session = _FakeSession()

    with pytest.raises(ValueError):
        submit_feedback(session=session, endpoint="ftp://example.com/x", payload={"content": "x"})

    assert session.calls == []


def test_submit_raises_on_http_error() -> None:
    session = _FakeSession(status_code=500)

    with pytest.raises(RuntimeError):
        submit_feedback(
            session=session,
            endpoint="http://192.168.1.10:8765/feedback",
            payload={"category": "issue", "content": "x", "app_version": "1.0.0"},
        )


def test_submit_raises_on_network_failure() -> None:
    class _BrokenSession:
        def post(self, *args, **kwargs):
            raise OSError("connection refused")

    with pytest.raises(RuntimeError):
        submit_feedback(
            session=_BrokenSession(),
            endpoint="http://192.168.1.10:8765/feedback",
            payload={"category": "issue", "content": "x", "app_version": "1.0.0"},
        )


def test_submit_does_not_send_credentials_in_headers() -> None:
    session = _FakeSession()

    submit_feedback(
        session=session,
        endpoint="http://192.168.1.10:8765/feedback",
        payload={"category": "issue", "content": "x", "app_version": "1.0.0"},
    )

    headers = session.calls[0]["headers"]
    lowered = {key.lower() for key in headers}
    assert "authorization" not in lowered
    assert "cookie" not in lowered
