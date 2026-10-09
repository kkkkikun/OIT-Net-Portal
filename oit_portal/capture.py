"""一键协议抓取向导：`oit-portal capture`。

在校内（校园 WiFi 未登录状态）运行，交互输一次账密，自动完成：
  1. 探测触发，拿到 302 跳转链与登录挑战
  2. 解析登录表单：端点、字段名、验证码检测、RSA 加密检测（含外链 JS 扫描）
  3. 按发现结果自动尝试登录（明文 / RSA），跟随 code 回跳完成 ePortal 上线
  4. 成功 → 写 protocol.json 自配置 + 持久化 SSO 会话（之后 daemon 全程免密）
  5. 无论成败 → 生成脱敏报告 capture-report.txt（不含密码，cookie 只留 4 位）

失败时把报告发给维护者即可替代全部手动 F12 抓包工作。
"""

from __future__ import annotations

import getpass
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urljoin, urlsplit

import requests

from . import htmlutil
from .auth import session_store
from .auth.eportal import EportalAdapter
from .auth.models import AuthCode, PortalChallenge, ProtocolMismatch
from .auth.sso import _rsa_encrypt
from .config import Config
from .discover import cookie_names, follow_entry
from .log import get_logger
from .paths import AppPaths
from .probe import ProbeStatus, probe

logger = get_logger()

_MAX_HOPS = 10
_MAX_JS_FILES = 6
_MAX_JS_BYTES = 300_000
_USERNAME_HINT_RE = ("user", "account", "username", "xh", "stu", "login")

# 注入式认证页的页面级跳转（meta refresh / JS location）由 discover.redirect_target 统一识别


@dataclass
class FormInfo:
    page_url: str = ""
    endpoint: str = ""                 # 绝对 URL
    inputs: dict[str, str] = field(default_factory=dict)     # name -> value（隐藏字段预填值）
    visible: list[str] = field(default_factory=list)
    username_field: str | None = None
    password_field: str | None = None
    has_captcha: bool = False
    captcha_reason: str = ""
    rsa_key: str | None = None
    rsa_source: str = ""
    rsa_hint_only: bool = False        # 有加密迹象但未提取到公钥
    aes_key: str | None = None         # CryptoJS AES（Vue/SPA 登录页常见）
    aes_iv: str | None = None
    aes_padding: str = "zero"          # zero | pkcs7
    aes_mode: str = "CBC"
    aes_source: str = ""
    candidates: list[str] = field(default_factory=list)  # JS 扫描出的登录接口候选
    evidence: list[str] = field(default_factory=list)    # 候选的来源上下文（排障用）


def _crypto_available() -> bool:
    try:
        import Crypto  # noqa: F401
        return True
    except ImportError:
        return False


def _make_session(cfg: Config) -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = cfg.advanced.user_agent
    # 探测与认证必须直连：系统代理会劫持 captive 检测与登录跳转链
    session.trust_env = False
    return session


def _walk(session: requests.Session, url: str, cfg: Config,
          hops: list[str]) -> tuple[requests.Response, str]:
    """手动跟随 30x 并记录每一跳，直到 200 / 出现 code / 跳数耗尽。"""
    resp = None
    for _ in range(_MAX_HOPS):
        try:
            resp = session.get(url, allow_redirects=False, timeout=cfg.advanced.timeout_sec)
        except requests.RequestException as exc:
            hops.append(f"GET {url} -> 异常 {type(exc).__name__}")
            raise
        hops.append(f"GET {url} -> {resp.status_code}"
                    + (f" (Location: {resp.headers.get('Location', '')[:160]})"
                       if 300 <= resp.status_code < 400 else "")
                    + f" [Set-Cookie: {cookie_names(resp)}]")
        if 300 <= resp.status_code < 400:
            location = resp.headers.get("Location", "")
            if not location:
                break
            url = urljoin(url, location)
            continue
        break
    return resp, url


def _code_in(url: str) -> str | None:
    qs = parse_qs(urlsplit(url).query)
    if qs.get("code") and qs["code"][0]:
        return qs["code"][0]
    return None


def analyze_form(session: requests.Session, cfg: Config, page_url: str,
                 html: str) -> FormInfo:
    """分析登录页。Vue/SPA 页面无 <form> 也继续：加密信息与接口候选仍可提取。"""
    info = FormInfo(page_url=page_url)
    action = htmlutil.form_action(html)
    if action:
        info.endpoint = urljoin(page_url, action)

        for name, value, itype in htmlutil.inputs(html):
            info.inputs[name] = value
            if itype not in ("hidden", "submit", "button", "checkbox", "radio"):
                info.visible.append(name)
            if itype == "password" and info.password_field is None:
                info.password_field = name

        captcha_names = {n for n, _v, t in htmlutil.inputs(html)
                         if t not in ("hidden", "submit", "button")
                         and htmlutil.CAPTCHA_NAME_RE.search(n)}
        info.has_captcha, img_reason = htmlutil.looks_like_captcha(html)
        info.captcha_reason = info.captcha_reason or img_reason

        # 用户名字段：名字含常见提示词的非密码可见输入，排除验证码
        candidates = [n for n in info.visible
                      if n != info.password_field and n not in captcha_names]
        info.username_field = next(
            (n for n in candidates
             if any(h in n.lower() for h in _USERNAME_HINT_RE)),
            candidates[0] if candidates else None,
        )

    # 加密检测（无论有无表单都执行——Vue 页面的加密脚本在 head 内联）
    aes = htmlutil.find_aes(html)
    if aes:
        info.aes_key, info.aes_iv = aes["key"], aes["iv"]
        info.aes_padding, info.aes_mode = aes["padding"], aes["mode"]
        info.aes_source = "页面内联脚本"
    rsa_key, rsa_source = htmlutil.find_rsa_key(html)
    if rsa_key:
        info.rsa_key, info.rsa_source = rsa_key, f"页面内联（{rsa_source}）"
    else:
        hint = htmlutil.has_rsa_hint(html)
        for src in htmlutil.script_sources(html)[:_MAX_JS_FILES]:
            js_url = urljoin(page_url, src)
            if urlsplit(js_url).netloc != urlsplit(page_url).netloc:
                continue
            try:
                js = session.get(js_url, timeout=cfg.advanced.timeout_sec).text
            except requests.RequestException:
                continue
            rsa_key, rsa_source = htmlutil.find_rsa_key(js[:_MAX_JS_BYTES])
            if rsa_key:
                info.rsa_key, info.rsa_source = rsa_key, f"外链 JS {src}（{rsa_source}）"
                break
            hint = hint or htmlutil.has_rsa_hint(js[:_MAX_JS_BYTES])
        info.rsa_hint_only = hint and info.rsa_key is None
    return info


_FRAMEWORK_JS_HINTS = ("framework", "jquery", "vue", "lodash", "weui", "qtip",
                       "crypto", "keyboard", "weixin", "backstretch")
# JS 里出现的登录类接口路径（SPA 的 axios/fetch 调用串）
_LOGIN_EP_RE = re.compile(
    r"['\"](?:https?://[^'\"\\\s]+)?(/[\w\-./]*(?:login|signin|token|doLogin)"
    r"[\w\-./]*)['\"]", re.I)
_STATIC_EXT = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
               ".woff", ".woff2", ".ttf", ".map")


def scan_login_endpoints(session: requests.Session, cfg: Config, page_url: str,
                         html: str) -> tuple[list[str], list[str]]:
    """无 <form> 的 SPA 登录页：收集登录接口路径候选。

    先扫页面内联脚本（Vue 应用的登录调用常写在内联 <script> 里），
    再扫外链 JS（auth/login 相关文件优先，框架库靠后）。
    返回 (候选列表, 证据上下文列表)。
    """
    candidates: list[str] = []
    evidence: list[str] = []

    def harvest(text: str, source: str) -> None:
        for m in _LOGIN_EP_RE.finditer(text[:_MAX_JS_BYTES]):
            path = m.group(1).split("?")[0]
            if path.lower().endswith(_STATIC_EXT) or path in candidates:
                continue
            candidates.append(path)
            ctx = text[max(0, m.start() - 100):m.end() + 100]
            evidence.append(f"{source}: …{re_sp(ctx)}…")

    harvest(html, "页面内联")
    srcs = dict.fromkeys(htmlutil.script_sources(html))

    def priority(src: str) -> int:
        low = src.lower()
        if any(k in low for k in ("auth", "login", "app.", "main", "index")):
            return 0
        if any(k in low for k in _FRAMEWORK_JS_HINTS):
            return 2   # 框架库放最后甚至跳过
        return 1

    for src in sorted(srcs, key=priority)[:12]:
        js_url = urljoin(page_url, src)
        if urlsplit(js_url).netloc != urlsplit(page_url).netloc:
            continue
        try:
            js = session.get(js_url, timeout=cfg.advanced.timeout_sec).text
        except requests.RequestException:
            continue
        harvest(js, f"外链 {src}")
    # 页面自身路径作为末位候选（部分 SPA 提交回当前地址）
    own = urlsplit(page_url).path
    if own and own not in candidates:
        candidates.append(own)
    return candidates, evidence


def _transform_password(password: str, mode: str, info: FormInfo) -> str:
    if mode == "rsa":
        return _rsa_encrypt(password, info.rsa_key or "")
    if mode in ("aes_cbc", "aes_ecb"):
        from .auth.sso import _aes_encrypt
        return _aes_encrypt(password, info.aes_key or "", info.aes_iv or "",
                            mode, info.aes_padding)
    return password


def _attempt_login(session: requests.Session, cfg: Config, info: FormInfo,
                   endpoint: str, kind: str, username: str, password: str,
                   mode: str, hops: list[str]) -> tuple[str | None, requests.Response]:
    payload = {k: v for k, v in info.inputs.items()
               if k not in (info.username_field, info.password_field)}
    payload[info.username_field] = username
    payload[info.password_field] = _transform_password(password, mode, info)
    hops.append(f"POST {endpoint} [{kind}] 字段[{','.join(payload)}] 加密={mode}")
    kwargs = {"json" if kind == "json" else "data": payload}
    post = session.post(endpoint, allow_redirects=False,
                        timeout=cfg.advanced.timeout_sec, **kwargs)
    hops.append(f"  -> {post.status_code}"
                + (f" (Location: {post.headers.get('Location', '')[:160]})"
                   if 300 <= post.status_code < 400 else ""))
    if 300 <= post.status_code < 400 and post.headers.get("Location"):
        final, final_url = _walk(session, urljoin(endpoint,
                                                  post.headers["Location"]), cfg, hops)
        return _code_in(final_url), final
    # SPA JSON 响应：跳转 URL 藏在响应体里（{redirect:"http://...code=..."}）
    for m in re.finditer(r"https?://[^'\"\\\s<>]+", post.text[:4096]):
        url = m.group(0)
        if any(k in url for k in ("code=", "authorize", "login_sso", "redirect")):
            hops.append(f"  响应体发现跳转：{url[:160]}")
            final, final_url = _walk(session, url, cfg, hops)
            return _code_in(final_url), final
    return None, post


def _write_report(path: Path, title: str, sections: list[tuple[str, list[str]]]) -> None:
    lines = [f"# OIT-Portal 抓包报告：{title}", f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}", ""]
    for header, items in sections:
        lines.append(f"## {header}")
        lines.extend(items or ["（空）"])
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"报告已写入：{path}")


def _summarize_form(info: FormInfo) -> list[str]:
    if info.rsa_key:
        rsa_desc = f"公钥来源={info.rsa_source}"
    elif info.rsa_hint_only:
        rsa_desc = "仅发现加密迹象，未提取到公钥"
    else:
        rsa_desc = "未发现"
    if info.aes_key:
        aes_desc = (f"AES-{info.aes_mode}（{info.aes_padding} 填充，"
                    f"key={info.aes_key[:6]}***，来源={info.aes_source}）")
    else:
        aes_desc = "未发现"
    lines = [
        f"表单页：{info.page_url}",
        f"提交端点：{info.endpoint or '无（SPA 动态渲染）'}",
        f"全部字段：{','.join(info.inputs)}",
        f"用户名字段：{info.username_field}（可见字段：{','.join(info.visible)}）",
        f"密码字段：{info.password_field}",
        f"验证码：{'有（' + info.captcha_reason + '）' if info.has_captcha else '未发现'}",
        f"RSA：{rsa_desc}",
        f"AES：{aes_desc}",
    ]
    if info.candidates:
        lines.append(f"JS 扫描接口候选：{','.join(info.candidates)}")
    return lines


def run_capture(cfg: Config, paths: AppPaths) -> int:
    if not sys.stdin.isatty():
        print("capture 向导需要交互式终端（要输入账号密码）", file=sys.stderr)
        return 1

    session = _make_session(cfg)
    report = paths.home / "capture-report.txt"
    hops: list[str] = []

    # ── 1. 前置状态检查 ──────────────────────────────────────
    print("== 第 1 步：探测网络状态 ==")
    pr = probe(session, cfg)
    print(f"当前状态：{pr}")
    pr_lines = [
        f"状态：{pr.status.value}（{pr.detail or '无'}）",
        f"探测点：{pr.probe_url or '（池内全部不可达）'}",
        f"302 Location：{pr.redirect_url or '无（200 注入式认证页）'}",
    ]
    if pr.status is ProbeStatus.ONLINE:
        print("已在线。请先让设备回到未登录状态：在认证成功页点「注销」，"
              "或断开重连校园 WiFi，然后重新运行本向导。")
        return 2
    if pr.status is ProbeStatus.OFFLINE:
        print("未检测到网络。请先连接校园 WiFi 再运行。")
        return 2

    # ── 2. 入口链路：穿过 30x / 注入页 / 页面级跳转，停在登录表单 ──
    print("== 第 2 步：跟随入口链路，定位登录表单 ==")
    if pr.redirect_url:
        hops.append(f"探测点 {pr.probe_url} -> 302 (Location: {pr.redirect_url[:200]})")
    else:
        hops.append(f"探测点 {pr.probe_url} -> 200 注入页（跟随页面跳转链）")
    try:
        entry = follow_entry(session, cfg, hops,
                             redirect_url=pr.redirect_url,
                             page_url=None if pr.redirect_url else pr.probe_url,
                             page_body=None if pr.redirect_url else pr.body)
    except requests.RequestException as exc:
        _write_report(report, "入口链路中断", [("探测", pr_lines), ("跳转链", hops)])
        print(f"入口链路请求失败：{exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - from_redirect 等协议错误
        _write_report(report, "入口解析失败",
                      [("探测", pr_lines), ("跳转链", hops),
                       ("错误", [f"{type(exc).__name__}: {exc}"])])
        print(f"入口链路解析失败：{exc}\n请把 {report} 发给维护者。")
        return 1
    challenge, resp, final_url = entry.challenge, entry.resp, entry.final_url

    if _code_in(final_url):
        # 会话仍有效，authorize 直接发了 code——无需账密即可验证整条链路
        # （_walk 跟随时已 GET 过 login_sso.jsp?code=... 完成上线，无需重复请求）
        print("检测到 SSO 会话仍有效（跳转链直接发出 code），正在验证……")
        code = _code_in(final_url)
        verify = probe(session, cfg)
        sections = [("探测", pr_lines), ("跳转链", hops),
                    ("结论", [f"code={code[:6]}***",
                              f"最终页面片段：{re_sp(resp.text)}",
                              f"复测：{verify}"])]
        _write_report(report, "会话有效（免密路径可用）", sections)
        session_store.save(session, paths.session)
        if verify.status is ProbeStatus.ONLINE:
            print("✅ 会话免密路径验证成功，会话已保存。直接运行 daemon 即可。")
            return 0
        print("⚠️ code 已获取但复测未在线，请把报告发给维护者。")
        return 1

    info = analyze_form(session, cfg, final_url, resp.text)
    for line in _summarize_form(info):
        print(f"  {line}")
    hops.append(f"表单页 {final_url} [Set-Cookie: {cookie_names(resp)}]")

    if not info.endpoint:
        # Vue/SPA 页面无 <form>：扫描内联脚本与外链 JS 寻找登录接口候选
        print("  页面无 <form>（Vue/JS 动态渲染），扫描脚本寻找登录接口……")
        info.candidates, info.evidence = scan_login_endpoints(session, cfg,
                                                              final_url, resp.text)
        for line in _summarize_form(info):
            print(f"  {line}")
        hops.append(f"JS 扫描接口候选：{info.candidates or '无'}")
        if not info.candidates:
            _write_report(report, "未找到登录表单与接口", [
                ("探测", pr_lines),
                ("跳转链", hops),
                ("最终页面片段", [resp.text[:20000].replace("\n", " ")]),
            ])
            print(f"未找到登录表单，脚本扫描也无接口候选。请把 {report} 发给维护者。")
            return 1
        # SPA 无输入框可解析：字段名按通行约定猜测（用户名 username / 密码 password）
        info.username_field = info.username_field or "username"
        info.password_field = info.password_field or "password"
    if info.has_captcha:
        _write_report(report, "发现验证码", [("探测", pr_lines), ("跳转链", hops),
                                             ("表单分析", _summarize_form(info))])
        print("登录页有验证码，无法全自动处理。请把报告发给维护者走人工适配。")
        return 1
    if info.rsa_hint_only:
        _write_report(report, "RSA 痕迹但无公钥", [("探测", pr_lines), ("跳转链", hops),
                                                   ("表单分析", _summarize_form(info))])
        print("发现密码加密迹象但未提取到公钥。请把报告发给维护者。")
        return 1

    # ── 3. 交互输入凭据 ──────────────────────────────────────
    # 前置检查：检测到前端加密但缺少加密库时，明确提示而不是中途崩溃
    if (info.aes_key or info.rsa_key) and not _crypto_available():
        print("⚠️ 检测到密码前端加密，但当前 Python 环境缺少 pycryptodome，无法加密密码。")
        print("   请先执行：pip install pycryptodome")
        print("   然后重新运行本向导。")
        _write_report(report, "缺少 pycryptodome",
                      [("探测", pr_lines), ("表单分析", _summarize_form(info))])
        return 1
    print("== 第 3 步：输入凭据（密码输入不回显；不会写入任何报告）==")
    default_user = cfg.username
    prompt = f"账号[{default_user}]：" if default_user else "账号："
    entered = input(prompt).strip()
    username = entered or default_user
    if cfg.password:
        use_saved = input("使用已保存的密码？[Y/n]：").strip().lower()
        password = cfg.password if use_saved in ("", "y", "yes") else getpass.getpass("密码：")
    else:
        password = getpass.getpass("密码：")

    # ── 4. 自动尝试登录 ──────────────────────────────────────
    print("== 第 4 步：自动尝试登录 ==")
    # 尝试矩阵：接口候选 × 请求形态(form/json) × 加密模式（按可能性排序，逐个试到在线为止）
    # 候选为相对路径（JS 扫描结果），统一基于表单页转为绝对 URL
    endpoints = [urljoin(final_url, e) for e in (info.candidates or [info.endpoint])]
    modes: list[str] = []
    if info.aes_key:
        modes.append("aes_ecb" if info.aes_mode == "ECB" else "aes_cbc")
    if info.rsa_key:
        modes.append("rsa")
    modes.append("none")
    logged_in = False
    tried: list[str] = []
    used_endpoint = used_mode = ""
    code: str | None = None
    final = None
    for endpoint in endpoints:
        for kind in ("form", "json"):
            for mode in modes:
                try:
                    code, final = _attempt_login(session, cfg, info, endpoint, kind,
                                                 username, password, mode, hops)
                except requests.RequestException as exc:
                    tried.append(f"{endpoint}[{kind}] {mode}: 请求异常 {type(exc).__name__}")
                    continue
                except ProtocolMismatch as exc:
                    tried.append(f"{endpoint}[{kind}] {mode}: {exc}")
                    continue
                verify = probe(session, cfg)
                tried.append(f"{endpoint}[{kind}] {mode}: "
                             f"code={'有' if code else '无'}，登录后状态={verify.status.value}")
                if verify.status is ProbeStatus.ONLINE:
                    logged_in = True
                    used_endpoint, used_mode = endpoint, mode
                    # 成功页信息直接从最终响应解析，不再重复请求 ePortal
                    from .auth.eportal import CAPTURED as E_CAP
                    body = (final.text or "")[:8192]
                    ui = re.search(E_CAP.user_index_pattern, body)
                    ka = re.search(E_CAP.keepalive_pattern, body)
                    hops.append(f"成功（接口={endpoint}，{kind}，加密={mode}，"
                                f"userIndex={ui.group(1) if ui else '未发现'}，"
                                f"keepalive={ka.group(1) + 's' if ka else '未发现'}）")
                    break
                # 记录失败响应片段供分析（不含密码——密码只在请求里，不在响应里）
                hops.append(f"  失败响应片段：{re_sp(final.text)}")
            if logged_in:
                break
        if logged_in:
            break

    sections = [("探测", pr_lines), ("跳转链", hops),
                ("表单分析", _summarize_form(info)),
                ("JS 证据", info.evidence or ["（无）"]),
                ("尝试记录", tried), ("结论", [])]
    if logged_in:
        protocol = {
            "sso": {
                "login_endpoint": _relative_if_possible(used_endpoint, info.page_url),
                "username_field": info.username_field,
                "password_field": info.password_field,
                "extra_fields": {k: v for k, v in info.inputs.items()
                                 if k not in (info.username_field, info.password_field)},
                "password_encrypt": used_mode,
                "rsa_public_key": info.rsa_key or "",
                "aes_key": info.aes_key or "",
                "aes_iv": info.aes_iv or "",
                "aes_padding": info.aes_padding,
                "has_captcha": False,
            },
            "eportal": {"online_mode": "sso_pass" if code else "direct"},
        }
        protocol_path = paths.home / "protocol.json"
        protocol_path.parent.mkdir(parents=True, exist_ok=True)
        protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        session_store.save(session, paths.session)
        sections[3] = ("结论", [
            f"✅ 登录成功（接口={used_endpoint}，加密={used_mode}）",
            f"已写自配置：{protocol_path}",
            f"已保存 SSO 会话：{paths.session}（免密复用直至次日失效）",
            "下一步：oit-portal daemon 即可全自动保活",
        ])
        _write_report(report, "登录成功", sections)
        print("\n✅ 登录成功！协议已自动配置，会话已保存。")
        print("之后直接运行 oit-portal daemon 即可全自动保活。")
        return 0

    sections[3] = ("结论", ["❌ 自动登录未成功。请把本报告发给维护者人工分析。"])
    _write_report(report, "登录失败", sections)
    print(f"\n❌ 自动登录未成功。请把 {report} 发给维护者。")
    return 1


def re_sp(text: str) -> str:
    return re.sub(r"\s+", " ", text)[:200]


def _relative_if_possible(endpoint: str, page_url: str) -> str:
    """端点尽量存相对路径（跨设备更稳），同源时转换。"""
    ep, pg = urlsplit(endpoint), urlsplit(page_url)
    if ep.netloc == pg.netloc and ep.path.startswith("/"):
        return ep.path + (f"?{ep.query}" if ep.query else "")
    return endpoint
