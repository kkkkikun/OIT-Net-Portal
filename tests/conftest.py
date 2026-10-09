"""测试夹具：FakeSession 模拟 HTTP 层（按路由队列回放响应），全部用例无网络。"""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Callable

import pytest
import requests

from oit_portal.config import Config


class FakeResponse:
    def __init__(self, status_code=200, headers=None, text="", url=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.text = text
        self.url = url


class FakeSession:
    """routes: [(predicate(url, method) -> bool, deque([resp|exc, ...]))]，
    命中后依次弹出；队列耗尽则重复最后一个。cookies/headers 兼容 requests.Session 接口。
    """

    def __init__(self):
        self.cookies = requests.cookies.RequestsCookieJar()
        self.headers: dict[str, str] = {}
        self.routes: list[tuple[Callable, deque]] = []
        self.calls: list[tuple[str, str]] = []

    def add(self, predicate, *responses):
        self.routes.append((predicate, deque(responses)))

    def add_url(self, url_prefix, *responses):
        self.add(lambda u, m, p=url_prefix: u.startswith(p), *responses)

    def _dispatch(self, method: str, url: str, data=None, **kwargs):
        self.calls.append((method, url))
        for predicate, queue in self.routes:
            if predicate(url, method):
                if len(queue) > 1:
                    item = queue.popleft()
                else:
                    item = queue[0]
                if isinstance(item, Exception):
                    raise item
                return item
        return FakeResponse(status_code=404, text=f"no route for {url}")

    def get(self, url, **kwargs):
        return self._dispatch("GET", url, **kwargs)

    def post(self, url, data=None, **kwargs):
        return self._dispatch("POST", url, data, **kwargs)


def make_config(tmp_path: Path = None, **overrides) -> Config:
    cfg = Config(username="20230001", password="secret-pass",
                 config_path=tmp_path / "config.toml" if tmp_path else None,
                 credentials_path=tmp_path / "credentials.toml" if tmp_path else None)
    cfg.probe.jitter_ratio = 0.0  # 测试中关闭抖动，断言精确值
    for section, values in overrides.items():
        for key, value in values.items():
            getattr(cfg, section).__setattr__(key, value)
    return cfg


@pytest.fixture
def fake_session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def cfg(tmp_path) -> Config:
    return make_config(tmp_path)


# 与真实结构一致的测试用 authorize URL（参数为无害假值）
AUTHORIZE_URL = (
    "http://open.oit.edu.cn:8090/auth/oauth/authorize"
    "?response_type=code&client_id=b50485d1-test"
    "&redirect_uri=http%3A%2F%2F172.16.11.54%2Feportal%2Flogin_sso.jsp"
    "%3Fwlanuserip%3Ddeadbeef%26wlanacname%3Dcafe1234%26t%3Dwireless-v2"
    "%26url%3D709db9dc"
)
EPORTAL_CODE_URL = (
    "http://172.16.11.54/eportal/login_sso.jsp"
    "?code=CODE123&wlanuserip=deadbeef&wlanacname=cafe1234&t=wireless-v2&url=709db9dc"
)
