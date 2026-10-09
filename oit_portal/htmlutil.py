"""登录表单 HTML 解析工具（无 bs4 依赖，正则实现，供 capture 向导与 sso 隐藏字段刷新共用）。"""

from __future__ import annotations

import re

INPUT_RE = re.compile(r"<input\b[^>]*>", re.I)
FORM_RE = re.compile(r"<form\b[^>]*>", re.I)
SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)

# RSA 公钥的常见形态：PEM / base64 DER（MIGf 开头）/ JS 变量赋值
_RSA_PEM_RE = re.compile(r"-----BEGIN PUBLIC KEY-----.*?-----END PUBLIC KEY-----", re.S)
_RSA_B64_RE = re.compile(r"MIGfMA0GCSqGSIb3[A-Za-z0-9+/=\s]{100,}")
_RSA_JS_RE = re.compile(
    r"""(?:publicKey|pubKey|public_key|rsaPublicKey)\s*[:=]\s*['"]([A-Za-z0-9+/=\s]{100,})['"]"""
)
# 页面/JS 中出现即提示「密码有前端 RSA 加密」的关键词
RSA_JS_HINTS = ("jsencrypt", "JSEncrypt", "setPublicKey", "RSAKey", "encryptedString")

CAPTCHA_NAME_RE = re.compile(
    r"(captcha|validcode|verifycode|checkcode|randcode|smscode|imgcode|vcode)", re.I)
CAPTCHA_IMG_RE = re.compile(
    r"<img\b[^>]*(?:src|id|class|alt)\s*=\s*[\"'][^\"']*(?:captcha|validcode|verify|checkcode|randcode)",
    re.I)


def attr(tag: str, name: str) -> str | None:
    """提取标签属性（支持双/单引号与无引号）。"""
    m = (re.search(rf'\b{name}\s*=\s*"([^"]*)"', tag, re.I)
         or re.search(rf"\b{name}\s*=\s*'([^']*)'", tag, re.I)
         or re.search(rf"\b{name}\s*=\s*([^\s>]+)", tag, re.I))
    return m.group(1) if m else None


def form_action(html: str) -> str | None:
    for tag in FORM_RE.finditer(html):
        action = attr(tag.group(0), "action")
        if action is not None:
            return action
    return None


def inputs(html: str) -> list[tuple[str, str, str]]:
    """返回 [(name, value, type)]，type 缺省按 text 处理。"""
    result = []
    for m in INPUT_RE.finditer(html):
        tag = m.group(0)
        name = attr(tag, "name")
        if not name:
            continue
        value = attr(tag, "value") or ""
        itype = (attr(tag, "type") or "text").lower()
        result.append((name, value, itype))
    return result


def hidden_values(html: str, names: list[str]) -> dict[str, str]:
    """按 input 名重新提取当前隐藏字段值（CAS lt/execution 等动态 token 刷新用）。"""
    wanted = set(names)
    found = {}
    for name, value, itype in inputs(html):
        if name in wanted and itype == "hidden" and value:
            found[name] = value
    return found


def find_rsa_key(text: str) -> tuple[str | None, str]:
    """在文本中寻找 RSA 公钥。返回 (key|None, 来源说明)。"""
    m = _RSA_PEM_RE.search(text)
    if m:
        return m.group(0).strip(), "PEM 块"
    m = _RSA_JS_RE.search(text)
    if m:
        return m.group(1).strip(), "JS 变量 publicKey"
    m = _RSA_B64_RE.search(text)
    if m:
        return re.sub(r"\s+", "", m.group(0)), "base64 DER"
    return None, ""


# AES 前端加密检测（CryptoJS 惯用形态，实测见用户登录页内联脚本）：
#   key = CryptoJS.enc.Utf8.parse('563a...800'.substr(0,16));
#   iv  = CryptoJS.enc.Utf8.parse('563a...800'.substr(0,16));
#   CryptoJS.AES.encrypt(str, key, {iv: iv, mode: CBC, padding: ZeroPadding})
_AES_ENCRYPT_RE = re.compile(r"CryptoJS\.AES\.encrypt", re.I)
_UTF8_PARSE_RE = re.compile(
    r"Utf8\.parse\(\s*['\"]([^'\"]+)['\"]\s*(?:\.\s*substr\(\s*(\d+)\s*,\s*(\d+)\s*\))?",
    re.I)
_CRYPTOJS_PAD_RE = re.compile(r"padding:\s*CryptoJS\.pad\.(\w+)", re.I)
_CRYPTOJS_MODE_RE = re.compile(r"mode:\s*CryptoJS\.mode\.(\w+)", re.I)


def find_aes(text: str) -> dict | None:
    """检测 CryptoJS AES 前端加密。返回 {key, iv, padding, mode} 或 None。"""
    if not _AES_ENCRYPT_RE.search(text):
        return None
    parses = _UTF8_PARSE_RE.findall(text)
    if not parses:
        return None

    def _apply(raw: str, start: str, length: str) -> str:
        if not length:
            return raw
        return raw[int(start or 0):int(start or 0) + int(length)]

    key = _apply(*parses[0])
    iv = _apply(*parses[1]) if len(parses) > 1 else key
    pad = _CRYPTOJS_PAD_RE.search(text)
    mode = _CRYPTOJS_MODE_RE.search(text)
    return {
        "key": key,
        "iv": iv,
        "padding": "pkcs7" if pad and pad.group(1).lower() == "pkcs7" else "zero",
        "mode": mode.group(1).upper() if mode else "CBC",
    }


def has_rsa_hint(text: str) -> bool:
    low = text.lower()
    return any(hint.lower() in low for hint in RSA_JS_HINTS)


def looks_like_captcha(html: str) -> tuple[bool, str]:
    """启发式判断登录表单是否有验证码。"""
    for name, _value, itype in inputs(html):
        if itype not in ("hidden", "submit", "button") and CAPTCHA_NAME_RE.search(name):
            return True, f"输入框 {name}"
    if CAPTCHA_IMG_RE.search(html):
        return True, "验证码图片"
    return False, ""


def script_sources(html: str) -> list[str]:
    return [m.group(1) for m in SCRIPT_SRC_RE.finditer(html)]
