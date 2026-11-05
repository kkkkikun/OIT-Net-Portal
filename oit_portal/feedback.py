"""App 反馈通道：载荷构造、落盘存储、自托管收集端与可选飞书转发。

安全边界：

- 反馈内容不进入 App 本地存储，不进日志（日志只记 fingerprint 与长度）。
- 诊断摘要只取 App 已有的脱敏会话事件，逐行过滤掉疑似凭据与完整 URL。
- 提交与转发都复用既有网络通道（``network.create_session()``，强制 ``trust_env = False``）。
- 收集端默认只监听回环地址；对外监听必须显式指定 host。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests

from .log import get_logger

logger = get_logger()

CATEGORY_SUGGESTION = "suggestion"
CATEGORY_ISSUE = "issue"
CATEGORY_OTHER = "other"

FEEDBACK_CATEGORIES = (CATEGORY_SUGGESTION, CATEGORY_ISSUE, CATEGORY_OTHER)

CATEGORY_LABELS = {
    CATEGORY_SUGGESTION: "建议",
    CATEGORY_ISSUE: "问题",
    CATEGORY_OTHER: "其他",
}

_MAX_DIAGNOSTIC_LINES = 10
_MAX_DIAGNOSTIC_LINE_LENGTH = 200

# 疑似凭据 / 敏感行的判定：命中任一即整行丢弃，而不是就地打码——
# 整行丢弃不会留下「这里原来有个账号」的痕迹。
_SENSITIVE_LINE_PATTERNS = (
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"\b(token|password|passwd|cookie|session|secret|authorization)\b", re.IGNORECASE),
    re.compile(r"(账号|密码|Cookie|口令|学号|工号)"),
)

# 允许保留的状态类事件前缀：只保留连接与登录的状态结论。
_ALLOWED_DIAGNOSTIC_PREFIXES = (
    "手动刷新",
    "登录结果",
    "网络恢复",
    "网络连接已断开",
    "Python 核心桥接已就绪",
    "应用已启动",
    "系统通知",
    "检测到",
    "后台服务已停止",
)


class FeedbackError(ValueError):
    """反馈内容或配置不合法。"""


@dataclass(frozen=True)
class FeedbackRecord:
    """一条已落盘的反馈。"""

    category: str
    content: str
    app_version: str
    submitted_at: str
    diagnostics: str | None = None

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "content": self.content,
            "app_version": self.app_version,
            "submitted_at": self.submitted_at,
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FeedbackRecord":
        return cls(
            category=str(data.get("category", CATEGORY_OTHER)),
            content=str(data.get("content", "")),
            app_version=str(data.get("app_version", "")),
            submitted_at=str(data.get("submitted_at", "")),
            diagnostics=data.get("diagnostics"),
        )


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_feedback_payload(
    *,
    category: str,
    content: str,
    diagnostics: str | None,
    app_version: str,
) -> dict[str, Any]:
    """构造反馈载荷。

    字段名与类型对作者侧稳定：App 与收集端版本可以错开。
    载荷只承载同学主动填写的内容与脱敏摘要，不含任何凭据字段。

    ``category_label`` 与 ``submitted_at`` 是给「直接写进飞书表格」用的：
    表格的列名就是请求体的键名，中文分类可以直接做单选列。
    """
    if category not in FEEDBACK_CATEGORIES:
        raise FeedbackError("反馈类型无效")
    text = (content or "").strip()
    if not text:
        raise FeedbackError("反馈内容不能为空")
    summary = (diagnostics or "").strip() or None
    submitted_at = _now_iso()
    return {
        "category": category,
        "category_label": CATEGORY_LABELS[category],
        "content": text,
        "with_diagnostics": summary is not None,
        "diagnostics": summary,
        "app_version": (app_version or "").strip(),
        "submitted_at": submitted_at,
        # 多维表格的日期列要数字时间戳，ISO 字符串只能当文本列用。
        "submitted_ts": int(datetime.fromisoformat(submitted_at).timestamp()),
    }


def sanitize_diagnostics(raw: str | None) -> str:
    """把 App 的会话事件压成可外发的脱敏摘要。

    只保留状态类事件；任何含账号、凭据线索或完整 URL 的行整行丢弃。
    """
    if not raw:
        return ""
    kept: list[str] = []
    for line in raw.splitlines():
        text = line.strip()
        if not text:
            continue
        if any(pattern.search(text) for pattern in _SENSITIVE_LINE_PATTERNS):
            continue
        if not text.startswith(_ALLOWED_DIAGNOSTIC_PREFIXES):
            continue
        kept.append(text[:_MAX_DIAGNOSTIC_LINE_LENGTH])
        if len(kept) >= _MAX_DIAGNOSTIC_LINES:
            break
    return "\n".join(kept)


class FeedbackStore:
    """反馈的本地权威副本：JSON Lines 追加写。"""

    def __init__(self, path: Path):
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, payload: dict[str, Any]) -> FeedbackRecord:
        record = FeedbackRecord(
            category=str(payload.get("category", CATEGORY_OTHER)),
            content=str(payload.get("content", "")),
            app_version=str(payload.get("app_version", "")),
            submitted_at=_now_iso(),
            diagnostics=payload.get("diagnostics") or None,
        )
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(record.to_json_line() + "\n")
        return record


def list_feedback_records(path: Path) -> list[FeedbackRecord]:
    """读出已落盘的反馈；坏行跳过，不让一行脏数据毁掉整份清单。"""
    store_path = Path(path)
    if not store_path.is_file():
        return []
    records: list[FeedbackRecord] = []
    for line in store_path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        records.append(FeedbackRecord.from_dict(data))
    return records


def _escape_markdown(text: str) -> str:
    """把反馈正文里的 Markdown 结构字符转义，避免导出清单被正文带偏标题层级。

    行首的 ``#`` / ``>`` / ``-`` / ``+`` 决定块结构，行内的 ``*`` / ``_`` 等决定强调，
    两类都要转义，否则同学的一段正文能把清单排版冲掉。
    """
    escaped = re.sub(r"([*_`\[\]])", r"\\\1", text)
    return re.sub(r"^(\s*)([#>+\-])", r"\1\\\2", escaped, flags=re.MULTILINE)


def format_feedback_listing(records: list[FeedbackRecord]) -> str:
    """终端里逐条列出反馈。"""
    if not records:
        return "暂无反馈。"
    lines: list[str] = []
    for index, record in enumerate(records, start=1):
        label = CATEGORY_LABELS.get(record.category, record.category)
        summary = record.content.replace("\n", " ")
        if len(summary) > 60:
            summary = summary[:60] + "…"
        time_text = record.submitted_at.replace("T", " ")[:16]
        lines.append(f"{index:>3}. [{label}] {summary}  ({time_text})")
    lines.append(f"共 {len(records)} 条反馈。")
    return "\n".join(lines)


def export_feedback_markdown(records: list[FeedbackRecord]) -> str:
    """导出成便于逐条处理与归档的 Markdown 清单。"""
    header = [
        "# App 反馈汇总",
        "",
        f"共 {len(records)} 条反馈。",
        "",
    ]
    if not records:
        header.append("暂无反馈。")
        return "\n".join(header) + "\n"
    blocks: list[str] = []
    for index, record in enumerate(records, start=1):
        label = CATEGORY_LABELS.get(record.category, record.category)
        block = [
            f"## {index}. {label}",
            "",
            f"- 时间：{record.submitted_at}",
            f"- App 版本：{record.app_version or '未知'}",
            "",
            _escape_markdown(record.content),
        ]
        if record.diagnostics:
            block += ["", "诊断摘要：", "", "```", record.diagnostics, "```"]
        blocks.append("\n".join(block))
    return "\n".join(header) + "\n\n---\n\n".join(blocks) + "\n"


def _is_feishu_group_bot(url: str) -> bool:
    """群机器人 webhook 与多维表格 webhook 的请求体格式不同，按地址形态区分。"""
    return "/open-apis/bot/" in url


def _is_feishu_table_webhook(url: str) -> bool:
    """多维表格 webhook：飞书域名且不是群机器人地址。"""
    return "feishu.cn" in url and not _is_feishu_group_bot(url)


def _feishu_signature(secret: str, timestamp: int) -> str:
    """飞书群机器人签名：HMAC-SHA256(timestamp + "\\n" + secret) 后 Base64。"""
    string_to_sign = f"{timestamp}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    return base64.b64encode(digest).decode("utf-8")


def _build_channel_request(
    *,
    url: str,
    payload: dict[str, Any],
    secret: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    """按通道形态构造请求体与请求头。

    - 群机器人：``msg_type`` + ``content.text``，签名走请求体字段。
    - 多维表格：扁平 JSON（键名即列名），凭证走 ``Authorization`` 请求头。
    - 其它（自托管收集端）：原始载荷。
    """
    headers = {"Content-Type": "application/json"}
    cleaned_secret = (secret or "").strip()

    if _is_feishu_group_bot(url):
        body: dict[str, Any] = {
            "msg_type": "text",
            "content": {"text": _render_feishu_text(payload)},
        }
        if cleaned_secret:
            timestamp = int(time.time())
            body["timestamp"] = str(timestamp)
            body["sign"] = _feishu_signature(cleaned_secret, timestamp)
        return body, headers

    if _is_feishu_table_webhook(url):
        body = {
            "content": str(payload.get("content", "")),
            "category": str(payload.get("category", "")),
            "category_label": str(payload.get("category_label", "")),
            "diagnostics": str(payload.get("diagnostics") or ""),
            "app_version": str(payload.get("app_version") or ""),
            "submitted_at": str(payload.get("submitted_at") or ""),
            "submitted_ts": payload.get("submitted_ts") or 0,
        }
        if cleaned_secret:
            headers["Authorization"] = f"Bearer {cleaned_secret}"
        return body, headers

    return dict(payload), headers


def _raise_on_channel_failure(response: Any) -> None:
    """把通道的业务级失败如实报出来。

    飞书即使 HTTP 200 也可能返回 ``code != 0``（关键词不匹配、IP 不在白名单等），
    只看状态码会把失败当成功 —— 同学以为提交了，其实没进表。
    """
    status = getattr(response, "status_code", 200)
    if status >= 400:
        raise RuntimeError(f"反馈通道拒绝了这次提交（HTTP {status}）")
    try:
        body = response.json()
    except Exception:
        return  # 通道返回空体或非 JSON：没有业务码可判，按成功处理
    if not isinstance(body, dict):
        return
    code = body.get("code")
    if code is None:
        return
    try:
        failed = int(code) != 0
    except (TypeError, ValueError):
        return
    if failed:
        raise RuntimeError("反馈通道拒绝了这次提交（请检查通道的校验设置）")


def submit_feedback(
    *,
    session: requests.Session,
    endpoint: str,
    payload: dict[str, Any],
    secret: str = "",
) -> None:
    """把反馈提交到目标通道。

    目标可以是飞书 webhook（群机器人 / 多维表格）或自托管收集端；
    请求体按目标形态自动构造。复用调用方传入的 Session
    （App 内是 ``network.create_session()``，强制不代理）。
    """
    url = (endpoint or "").strip()
    if not url:
        raise FeedbackError("反馈通道地址不能为空")
    if not url.startswith(("http://", "https://")):
        raise FeedbackError("反馈通道地址必须是 http 或 https")
    body, headers = _build_channel_request(url=url, payload=payload, secret=secret)
    try:
        response = session.post(url, json=body, headers=headers, timeout=10)
    except Exception as exc:  # 网络异常统一转成 RuntimeError，不把底层细节外泄给 UI
        raise RuntimeError("无法连接反馈通道") from exc
    _raise_on_channel_failure(response)


def forward_feedback_to_feishu(
    *,
    session: requests.Session,
    webhook_url: str,
    payload: dict[str, Any],
) -> None:
    """把一条反馈同步到飞书。

    支持两种 webhook 形态：

    - 群机器人（``open-apis/bot``）：发一条文本消息。
    - 多维表格：发扁平 JSON，键名即列名。

    可选增强：调用方负责在失败时只记日志，不影响本机落盘。
    """
    url = (webhook_url or "").strip()
    if not url:
        return
    if not url.startswith(("http://", "https://")):
        raise FeedbackError("飞书 webhook 地址必须是 http 或 https")

    # 与提交端共用同一套构造逻辑，避免两条路径的请求体形状漂移。
    body, headers = _build_channel_request(url=url, payload=payload, secret="")

    try:
        response = session.post(url, json=body, headers=headers, timeout=10)
    except Exception as exc:
        raise RuntimeError("无法连接飞书 webhook") from exc
    if response.status_code >= 400:
        raise RuntimeError(f"飞书 webhook 拒绝了这次同步（HTTP {response.status_code}）")


def _render_feishu_text(payload: dict[str, Any]) -> str:
    """把一条反馈渲染成群消息文本。"""
    label = CATEGORY_LABELS.get(str(payload.get("category", "")), "反馈")
    content = str(payload.get("content", "")).strip()
    diagnostics = str(payload.get("diagnostics") or "").strip()
    app_version = str(payload.get("app_version") or "").strip()

    lines = [f"【{label}】{content}"]
    if app_version:
        lines.append(f"App 版本：{app_version}")
    if diagnostics:
        lines.append("诊断摘要：")
        lines.append(diagnostics)
    return "\n".join(lines)


@dataclass(frozen=True)
class FeedbackCollectorConfig:
    """收集端配置。

    ``port=0`` 表示由系统分配空闲端口（测试用）。默认监听回环。
    """

    host: str = "127.0.0.1"
    port: int = 8787
    feishu_webhook_url: str = ""
    max_body_bytes: int = 64 * 1024

    @classmethod
    def max_body_bytes_default(cls) -> int:
        return cls.max_body_bytes


class _FeedbackRequestHandler(BaseHTTPRequestHandler):
    """处理 ``POST /feedback``。"""

    server_version = "OITFeedback/1.0"

    @property
    def _collector(self) -> "FeedbackCollector":
        return self.server.collector  # type: ignore[attr-defined]

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler 约定
        if self.path.rstrip("/") != "/feedback":
            self._respond(404, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._respond(400, {"ok": False, "error": "invalid content length"})
            return
        if length <= 0:
            self._respond(400, {"ok": False, "error": "invalid body size"})
            return
        if length > self._collector.config.max_body_bytes:
            # 超限时**先读完请求体再响应**：客户端还在往这写，
            # 服务端若提前应答就会把连接 RST 掉，客户端拿到的是 BrokenPipe
            # 而不是干净的 400（2026-11-04 实测复现）。
            self._drain(length)
            self._respond(400, {"ok": False, "error": "invalid body size"})
            return
        try:
            raw = self.rfile.read(length).decode("utf-8")
            data = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._respond(400, {"ok": False, "error": "invalid json"})
            return
        if not isinstance(data, dict):
            self._respond(400, {"ok": False, "error": "invalid payload"})
            return
        try:
            build_feedback_payload(
                category=str(data.get("category", "")),
                content=str(data.get("content", "")),
                diagnostics=data.get("diagnostics"),
                app_version=str(data.get("app_version", "")),
            )
        except FeedbackError as exc:
            self._respond(400, {"ok": False, "error": str(exc)})
            return

        record = self._collector.store.append(data)
        self._collector.forward_to_feishu(record.to_dict())
        self._respond(200, {"ok": True, "id": record.submitted_at})

    def log_message(self, format: str, *args: Any) -> None:
        """把访问日志静音：内容可能含同学原文，不进日志文件。"""
        return

    def _drain(self, length: int) -> None:
        """读完并丢弃请求体。

        必须读完**全部**：只读一部分就响应，客户端仍在写，
        一样会被 RST（2026-11-04 实测）。读完再应答才能拿到干净的 400。
        """
        remaining = length
        try:
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)
        except OSError:
            # 客户端自己断了就断了，响应仍会正常写出。
            pass

    def _respond(self, status: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class FeedbackCollector:
    """自托管反馈收集端。

    先落盘、后转发：转发失败只记日志，反馈本身已经收下。
    """

    def __init__(
        self,
        *,
        config: FeedbackCollectorConfig,
        store_path: Path,
        session_factory=None,
    ):
        self.config = config
        self.store = FeedbackStore(store_path)
        self._session_factory = session_factory
        self._server = ThreadingHTTPServer((config.host, config.port), _FeedbackRequestHandler)
        self._server.collector = self  # type: ignore[attr-defined]
        self._server.daemon_threads = True

    @property
    def port(self) -> int:
        return self._server.server_address[1]

    @property
    def base_url(self) -> str:
        host = self.config.host
        if host in ("0.0.0.0", "::"):
            host = "127.0.0.1"
        return f"http://{host}:{self.port}"

    def forward_to_feishu(self, payload: dict[str, Any]) -> None:
        """转发到飞书；未配置或失败都不影响已落盘的反馈。"""
        if not self.config.feishu_webhook_url:
            return
        session = self._session_factory() if self._session_factory else requests.Session()
        try:
            forward_feedback_to_feishu(
                session=session,
                webhook_url=self.config.feishu_webhook_url,
                payload=payload,
            )
        except Exception as exc:
            logger.warning("飞书同步失败（反馈已落盘）：%s", type(exc).__name__)

    def serve_forever(self) -> None:
        self._server.serve_forever()

    def shutdown(self) -> None:
        self._server.shutdown()
        self._server.server_close()


@dataclass
class FeedbackCollectorRuntime:
    """收集端运行上下文（供 CLI 使用）。"""

    collector: FeedbackCollector
    store_path: Path = field(default=Path("feedback.jsonl"))
