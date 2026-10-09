"""入口链路发现：从未认证状态出发，穿过 30x / 注入页 / 页面级跳转，停在登录表单页。

真实校园网的入口形态（实测确认）：
  探测请求 → AC 注入 JS 跳转页（200，<script>location.href='…index.jsp…'</script>）
           → ePortal index.jsp（可能再 JS 跳 SSO authorize）
           → OAuth authorize（302 链）
           → SSO 登录表单（200，含 <form>）
三种页面级跳转都要能跟：meta refresh、location.href 赋值、location.replace()。
遇到 authorize 形态的 URL（含 client_id & redirect_uri）时顺手解析出 PortalChallenge。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import SimpleNamespace
from urllib.parse import parse_qs, urljoin, urlsplit

import requests

from .auth.models import PortalChallenge
from .config import Config

_MAX_HOPS = 10
_MAX_PAGE_BYTES = 65536

# 页面级跳转的识别模式（按顺序尝试）
_REDIRECT_TARGET_RES = (
    # <meta http-equiv="refresh" content="0;url=...">
    re.compile(r"http-equiv=['\"]?refresh['\"]?[^>]*content=['\"]?\d+\s*;\s*url=([^'\">]+)",
               re.I),
    # location.href='...' / top.self.location.href='...' / window.location='...'
    re.compile(r"location(?:\.href)?\s*=\s*['\"]([^'\"]+)['\"]", re.I),
    # location.replace('...')
    re.compile(r"location\.replace\(\s*['\"]([^'\"]+)['\"]\s*\)", re.I),
)


def redirect_target(html: str) -> str | None:
    """从页面 HTML 中提取页面级跳转目标（meta refresh / JS location）。"""
    head = html[:_MAX_PAGE_BYTES]
    for pattern in _REDIRECT_TARGET_RES:
        m = pattern.search(head)
        if m:
            return m.group(1).strip()
    return None


def looks_authorize(url: str) -> bool:
    """是否为 OAuth authorize 形态（含 client_id 与 redirect_uri 参数）。"""
    try:
        qs = parse_qs(urlsplit(url).query)
    except ValueError:
        return False
    return "client_id" in qs and "redirect_uri" in qs


def cookie_names(resp) -> str:
    raw = resp.headers.get("Set-Cookie", "") if getattr(resp, "headers", None) else ""
    names = [part.split("=", 1)[0].strip() for part in raw.split(",") if "=" in part]
    return ",".join(n for n in names if n) or "-"


@dataclass
class EntryResult:
    challenge: PortalChallenge | None   # 链路中发现的 OAuth 挑战（可能为 None）
    resp: object                        # 最终页面响应（至少是注入页本体的替身）
    final_url: str


def _blank(url: str, text: str = ""):
    return SimpleNamespace(text=text, headers={}, status_code=200, url=url)


def follow_entry(session: requests.Session, cfg: Config, hops: list[str] | None, *,
                 redirect_url: str | None = None,
                 page_url: str | None = None,
                 page_body: str | None = None) -> EntryResult:
    """跟随入口链路直到登录表单页。

    - redirect_url 模式（302 劫持）：从该 URL 开始，challenge 立即解析
    - page_url + page_body 模式（200 注入）：注入页作为第一页
    - 30x 跟 Location；200 页面若有跳转目标且无 <form> 则继续跟
    - 链路中出现的 authorize URL 会被解析为 challenge
    - 停止条件：无跳转目标的 200 页面（即表单页/死胡同）或跳数耗尽
    """
    hops = hops if hops is not None else []
    challenge = None

    if redirect_url:
        challenge = PortalChallenge.from_redirect(redirect_url)  # 可能抛 ProtocolMismatch
        url = redirect_url
        resp = None
    else:
        url = page_url or ""
        resp = _blank(url, page_body or "")

    for _ in range(_MAX_HOPS):
        if resp is None:
            resp = session.get(url, allow_redirects=False,
                               timeout=cfg.advanced.timeout_sec)
            hops.append(f"GET {url} -> {resp.status_code}"
                        + (f" (Location: {resp.headers.get('Location', '')[:160]})"
                           if 300 <= resp.status_code < 400 else "")
                        + f" [Set-Cookie: {cookie_names(resp)}]")
            if 300 <= resp.status_code < 400:
                location = resp.headers.get("Location", "")
                if not location:
                    break
                nxt = urljoin(url, location)
                if challenge is None and looks_authorize(nxt):
                    challenge = PortalChallenge.from_redirect(nxt)
                url, resp = nxt, None
                continue
            if resp.status_code != 200:
                break
        # 200 页面：有 <form> 即视为到达登录页；否则跟页面级跳转
        body = resp.text[:_MAX_PAGE_BYTES]
        if "<form" in body.lower():
            break
        target = redirect_target(body)
        if not target:
            break
        nxt = urljoin(url, target)
        if challenge is None and looks_authorize(nxt):
            challenge = PortalChallenge.from_redirect(nxt)
        hops.append(f"页面跳转 -> {nxt[:160]}")
        url, resp = nxt, None

    if resp is None:  # 跳数耗尽在重定向上
        resp = _blank(url)
    return EntryResult(challenge=challenge, resp=resp, final_url=url)
