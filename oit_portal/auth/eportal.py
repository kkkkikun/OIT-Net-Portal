"""锐捷 ePortal 适配器（172.16.11.54）。

═══════════════════════════════════════════════════════════════════
★ <CAPTURE> 隔离区：抓包后只改 CAPTURED 常量块（protocol-notes C3/C4）★
双分支预实现，U3 抓包结论出来后用 online_mode 二选一：
  - "sso_pass"：GET login_sso.jsp?code=... 由服务端直接完成上线（默认预设）
  - "interface_do"：页面 JS 需再 POST /eportal/InterFace.do?method=login
═══════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import requests

from ..config import Config
from ..log import get_logger
from ..protocol_overrides import apply_overrides
from .models import (AuthCode, OnlineResult, PortalChallenge,
                     PortalUnreachable, ProtocolMismatch)

logger = get_logger()

CAPTURED = SimpleNamespace(
    online_mode="sso_pass",  # "sso_pass" | "interface_do"   <CAPTURE:C3.2>
    interface_endpoint="/eportal/InterFace.do?method=login",  # 锐捷标准，C3.3 校准
    interface_fields={       # interface_do 模式的表单（C3.3 抓包校准）
        "userId": "<CAPTURE:C3.3>",
        "password": "",
        "passwordEncrypt": "true",
        "queryString": "{querystring}",   # 占位符，运行时替换为当次挑战参数
        "service": "",
        "operatorPwd": "",
        "operatorUserId": "",
        "validcode": "",
    },
    success_markers=["成功", "success"],              # <CAPTURE:C3.4> 响应体成功标记
    user_index_pattern=r"userIndex['\"]?\s*[:=]\s*['\"]?([0-9A-Za-z]+)",
    keepalive_pattern=r"keepaliveInterval['\"]?\s*[:=]\s*['\"]?(\d+)",
    logout_endpoint="/eportal/InterFace.do?method=logout",
)


def _sub_placeholders(text: str) -> bool:
    return "<CAPTURE" in text


class EportalAdapter:
    def __init__(self, session: requests.Session, cfg: Config):
        self.session = session
        self.cfg = cfg
        apply_overrides(CAPTURED, "eportal")  # capture 向导自动发现的协议覆盖

    def online(self, code: AuthCode, challenge: PortalChallenge) -> OnlineResult:
        if not code.code:  # 表单直登模式：登录 POST 已直接上线，无需再调 ePortal
            return OnlineResult(success=True, mode="direct",
                                message="表单直登，跳过 ePortal 调用")
        if CAPTURED.online_mode == "sso_pass":
            return self._online_sso_pass(code, challenge)
        return self._online_interface_do(code, challenge)

    def _online_sso_pass(self, code: AuthCode, challenge: PortalChallenge) -> OnlineResult:
        """预设分支：GET login_sso.jsp?code=...（跟随重定向）即完成上线。"""
        url = challenge.eportal_sso_url(code.code)
        try:
            resp = self.session.get(url, timeout=self.cfg.advanced.timeout_sec,
                                    allow_redirects=True)
        except requests.RequestException as exc:
            raise PortalUnreachable(f"ePortal 上线请求失败: {type(exc).__name__}") from exc
        return self._judge(resp, mode="sso_pass")

    def _online_interface_do(self, code: AuthCode,
                             challenge: PortalChallenge) -> OnlineResult:
        """备用分支：login_sso.jsp 页面 JS 再调 InterFace.do（锐捷标准接口）。"""
        form = {}
        for key, value in CAPTURED.interface_fields.items():
            if _sub_placeholders(value):
                raise ProtocolMismatch(f"interface_fields.{key} 尚未填充（C3.3）")
            form[key] = value.replace("{querystring}", challenge.eportal_querystring) \
                if key == "queryString" else value
        url = challenge.eportal_base + CAPTURED.interface_endpoint
        try:
            resp = self.session.post(url, data=form, timeout=self.cfg.advanced.timeout_sec)
        except requests.RequestException as exc:
            raise PortalUnreachable(f"ePortal InterFace.do 失败: {type(exc).__name__}") from exc
        return self._judge(resp, mode="interface_do")

    def _judge(self, resp: requests.Response, *, mode: str) -> OnlineResult:
        body = resp.text[:8192]
        user_index = keepalive = None
        m = re.search(CAPTURED.user_index_pattern, body)
        if m:
            user_index = m.group(1)
        m = re.search(CAPTURED.keepalive_pattern, body)
        if m:
            keepalive = int(m.group(1))
        hit = any(marker in body for marker in CAPTURED.success_markers)
        success = hit or resp.status_code == 200 and user_index is not None
        snippet = re.sub(r"\s+", " ", body)[:200]
        if success:
            logger.info("ePortal 上线成功（mode=%s, userIndex=%s, keepalive=%ss）",
                        mode, user_index, keepalive)
        else:
            logger.warning("ePortal 响应未见成功标记（HTTP %s）：%.200s",
                           resp.status_code, snippet)
        return OnlineResult(success=success, message=snippet, user_index=user_index,
                            keepalive_interval=keepalive, mode=mode, raw=body)

    def logout(self, base_url: str, user_index: str) -> None:
        url = base_url + CAPTURED.logout_endpoint
        try:
            self.session.post(url, data={"userIndex": user_index},
                              timeout=self.cfg.advanced.timeout_sec)
            logger.info("已请求 ePortal 注销（userIndex=%s…）", user_index[:6])
        except requests.RequestException as exc:
            raise PortalUnreachable(f"注销请求失败: {type(exc).__name__}") from exc
