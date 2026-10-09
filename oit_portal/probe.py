"""联网探测器：多 URL 探测池 → ONLINE / CAPTIVE / OFFLINE 三态。

判定规则：
- HTTP 204                          → ONLINE（generate_204 类端点）
- HTTP 200 且正文含 Success         → ONLINE（captive.apple.com 类端点）
- 30x 带 Location（被劫持到认证页）  → CAPTIVE，携带跳转 URL（登录流程的入口）
- 连接超时 / DNS 失败 / 无路由       → OFFLINE，换下一个探测 URL 再试
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

import requests

from .config import Config
from .log import get_logger

logger = get_logger()


class ProbeStatus(enum.Enum):
    ONLINE = "online"      # 已联网
    CAPTIVE = "captive"    # 被认证页劫持（需要登录）
    OFFLINE = "offline"    # 无网络（未连 WiFi / 信号问题）


@dataclass
class ProbeResult:
    status: ProbeStatus
    redirect_url: str | None = None   # CAPTIVE 时的 302 Location（登录流程入口）
    probe_url: str = ""
    detail: str = ""
    body: str | None = None           # 200 注入式认证页的 HTML（无 302 的劫持形态）

    def __str__(self) -> str:  # 便于日志/CLI 输出
        base = self.status.value.upper()
        if self.status is ProbeStatus.CAPTIVE:
            return f"{base} -> {self.redirect_url}" if self.redirect_url \
                else f"{base}（200 注入式认证页）"
        return f"{base} ({self.detail})" if self.detail else base


def _probe_one(session: requests.Session, url: str, timeout: int) -> ProbeResult:
    try:
        resp = session.get(url, timeout=timeout, allow_redirects=False)
    except requests.RequestException as exc:
        return ProbeResult(ProbeStatus.OFFLINE, probe_url=url, detail=f"{type(exc).__name__}")

    if resp.status_code == 204:
        return ProbeResult(ProbeStatus.ONLINE, probe_url=url)
    if 300 <= resp.status_code < 400:
        location = resp.headers.get("Location", "")
        if not location:
            return ProbeResult(ProbeStatus.OFFLINE, probe_url=url,
                               detail=f"{resp.status_code} 无 Location")
        return ProbeResult(ProbeStatus.CAPTIVE, redirect_url=location, probe_url=url,
                           detail=f"HTTP {resp.status_code}")
    if resp.status_code == 200:
        text = resp.text[:65536]
        if "Success" in text:
            return ProbeResult(ProbeStatus.ONLINE, probe_url=url)
        # 200 但无 Success 标记：AC 直接在探测 URL 上注入了认证页（无 302 的劫持形态）
        return ProbeResult(ProbeStatus.CAPTIVE, redirect_url=None, probe_url=url,
                           detail="HTTP 200 无 Success 标记（注入式认证页）",
                           body=text)
    return ProbeResult(ProbeStatus.OFFLINE, probe_url=url, detail=f"HTTP {resp.status_code}")


def probe(session: requests.Session, cfg: Config) -> ProbeResult:
    """轮询探测池。

    - 302 劫持（带 Location）是最强证据，立即采用并返回
    - 200 注入式劫持先记为 fallback，继续尝试其他探测点找 302 形态
      （找到则用 302——能解析出 OAuth 挑战；都没有才回落注入页）
    - 已见注入式劫持时，后续探测点的「在线」判定不可信（可能是白名单放行），忽略
    - ONLINE 时用第二个 URL 双确认，防单个探测点被白名单放行误判
    """
    fallback: ProbeResult | None = None
    for idx, url in enumerate(cfg.probe.urls):
        result = _probe_one(session, url, cfg.advanced.timeout_sec)
        logger.debug("probe %s -> %s", url, result.status.value)

        if result.status is ProbeStatus.CAPTIVE:
            if result.redirect_url:
                return result
            if fallback is None:
                fallback = result
            continue
        if result.status is ProbeStatus.ONLINE:
            if fallback is not None:
                logger.debug("已有注入式劫持记录，忽略 %s 的在线判定", url)
                continue
            if idx == 0 and len(cfg.probe.urls) > 1:
                second = _probe_one(session, cfg.probe.urls[1], cfg.advanced.timeout_sec)
                if second.status is ProbeStatus.CAPTIVE:
                    logger.info("双确认不一致（%s 判在线，%s 判劫持），按劫持处理",
                                url, cfg.probe.urls[1])
                    return second
                return result
            return result
    if fallback is not None:
        return fallback
    return ProbeResult(ProbeStatus.OFFLINE,
                       detail="全部探测点不可达（未连 WiFi 或无路由）")
