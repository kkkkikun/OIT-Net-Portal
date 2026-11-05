"""移动端反馈桥接。

与 ``mobile_bridge`` 同一层边界：只暴露「提交一条反馈」，
不暴露收集端地址、底层异常细节或同学原文。
"""

from __future__ import annotations

import requests

from .config import Config
from .feedback import build_feedback_payload, submit_feedback
from .network import create_session


class MobileFeedbackBridge:
    """可注入 Session 的反馈提交接口。

    外部传入的 Session 由调用方管理；桥接自行创建的 Session 会禁用环境代理，
    并由 close() 负责释放。
    """

    def __init__(
        self,
        *,
        endpoint: str,
        app_version: str,
        secret: str = "",
        session: requests.Session | None = None,
    ):
        self._endpoint = (endpoint or "").strip()
        self._app_version = (app_version or "").strip()
        self._secret = (secret or "").strip()
        self._owns_session = session is None
        self._session = session if session is not None else create_session(Config())
        self._closed = False

    @property
    def is_available(self) -> bool:
        return not self._closed and bool(self._endpoint)

    def submit(self, *, category: str, content: str, diagnostics: str | None) -> None:
        """提交一条反馈。参数无效直接抛 ValueError，网络失败抛 RuntimeError。"""
        if self._closed:
            raise RuntimeError("反馈桥接已关闭")
        payload = build_feedback_payload(
            category=category,
            content=content,
            diagnostics=diagnostics,
            app_version=self._app_version,
        )
        submit_feedback(
            session=self._session,
            endpoint=self._endpoint,
            payload=payload,
            secret=self._secret,
        )

    def close(self) -> None:
        """关闭自有 Session；多次调用安全，外部注入的 Session 不会被关闭。"""
        if self._closed:
            return
        self._closed = True
        if not self._owns_session:
            return
        try:
            self._session.close()
        except Exception:  # noqa: BLE001 - 关闭失败不影响调用方生命周期
            pass


def create_mobile_feedback_bridge(
    endpoint: str,
    app_version: str,
    secret: str = "",
) -> MobileFeedbackBridge:
    """用通道地址创建反馈桥接；不读取外部配置文件或环境变量。

    ``secret`` 是通道的凭证校验值：群机器人用签名密钥，多维表格用 Bearer token。
    """
    cleaned = (endpoint or "").strip()
    if not cleaned:
        raise ValueError("反馈通道地址无效")
    return MobileFeedbackBridge(endpoint=cleaned, app_version=app_version, secret=secret)


__all__ = ["MobileFeedbackBridge", "create_mobile_feedback_bridge"]
