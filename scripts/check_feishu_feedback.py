#!/usr/bin/env python3
"""飞书反馈通道自检：一眼看出对方侧哪一环没配好。

用法：
    python3 scripts/check_feishu_feedback.py --webhook-url "https://.../webhook/event/xxx" \
        [--secret "token"]

只发探测请求，不写业务数据；请先在飞书表格里确认没有多出记录（探测用 content 会带标记）。
"""

from __future__ import annotations

import argparse
import json
import sys

import requests

PROBE_CONTENT = "【通道自检】探测请求，确认后可直接删除"
PROBE_PAYLOAD = {
    "content": PROBE_CONTENT,
    "category": "other",
    "category_label": "其他",
    "diagnostics": "",
    "app_version": "self-check",
    "submitted_at": "2026-01-01T00:00:00+08:00",
    "submitted_ts": 1767225600,
}


def _post(url: str, headers: dict[str, str], payload: dict) -> tuple[int, str]:
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
    except Exception as exc:
        return 0, f"连接失败：{type(exc).__name__}"
    try:
        body = response.json()
    except Exception:
        return response.status_code, response.text[:200]
    return response.status_code, f"code={body.get('code')} msg={body.get('msg', '')}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="飞书反馈通道自检")
    parser.add_argument("--webhook-url", required=True, help="多维表格自动化 webhook 地址")
    parser.add_argument("--secret", default="", help="凭证校验 token（没开校验可不填）")
    args = parser.parse_args(argv)

    url = args.webhook_url.strip()
    headers = {"Content-Type": "application/json"}
    if args.secret.strip():
        headers["Authorization"] = f"Bearer {args.secret.strip()}"

    print("== 1. 带凭证提交 ==")
    status, detail = _post(url, headers, PROBE_PAYLOAD)
    print(f"   HTTP {status}  {detail}")

    print("\n== 2. 不带凭证提交（验凭证校验是否真的开启）==")
    status, detail = _post(url, {"Content-Type": "application/json"}, PROBE_PAYLOAD)
    print(f"   HTTP {status}  {detail}")
    if "code=0" in detail:
        print("   → 校验【未开启】：地址泄露即可写入，请在飞书「安全设置」里开启凭证校验")

    print("\n== 3. 关键结论 ==")
    print("   code=0 只代表「webhook 收到了请求」，不代表「工作流执行了」。")
    print("   若飞书表格里没有记录，请检查：")
    print("     a) 流程右上角开关是否已启用；")
    print("     b) 触发节点的「输出设置」是否配了 schema（没配 = 请求体被丢弃）；")
    print("     c) 「新增记录」节点的字段映射是否配好；")
    print("     d) 「新增记录」指向的数据表是否就是你正在看的那张。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
