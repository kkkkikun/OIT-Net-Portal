"""Windows 侧 PowerShell 脚本的编码契约。

背景（2026-11-01，在用户自己的中文 Windows 上实测）：
`Windows PowerShell 5.1`（中文系统的默认 `powershell.exe`）读取**没有 BOM** 的
`.ps1` 时，会按系统 ANSI 代码页（本机 cp936 / GBK）解码，而不是按 UTF-8。
脚本里的中文提示因此变成乱码，并且 GBK 解码产生的替换字节会把字符串的
引号吃掉，导致脚本**直接语法错误**、一行都跑不起来：

    install_windows.ps1        → 2 处解析错误
    install_windows_tray.ps1   → 2 处解析错误
    uninstall_windows.ps1      → 1 处解析错误

也就是说，文档推荐的「托盘安装」「卸载」方式在中文 Windows 上是不可用的。
微软的官方约定就是：**含非 ASCII 内容的 .ps1 必须存成 UTF-8 with BOM**。

本模块把这个约定固化成静态契约测试，防止有人用不带 BOM 的编辑器保存后
悄悄把脚本改回坏掉的状态。
"""

from __future__ import annotations

from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
UTF8_BOM = b"\xef\xbb\xbf"
POWERSHELL_SCRIPTS = sorted(SCRIPTS_DIR.glob("*.ps1"))


def test_there_are_powershell_scripts_to_check() -> None:
    assert POWERSHELL_SCRIPTS, "scripts/ 下找不到任何 .ps1 脚本"


@pytest.mark.parametrize("path", POWERSHELL_SCRIPTS, ids=lambda p: p.name)
def test_powershell_script_is_utf8_with_bom(path: Path) -> None:
    """每个 .ps1 都必须带 UTF-8 BOM，且 BOM 之后是合法 UTF-8。"""
    raw = path.read_bytes()
    assert raw.startswith(UTF8_BOM), (
        f"{path.name} 缺少 UTF-8 BOM：Windows PowerShell 5.1 会按系统 ANSI "
        f"代码页解码，中文提示变乱码并吃掉引号，脚本直接语法错误"
    )
    body = raw[len(UTF8_BOM) :]
    try:
        body.decode("utf-8")
    except UnicodeDecodeError as exc:  # pragma: no cover - 失败即回归
        pytest.fail(f"{path.name} 去掉 BOM 后不是合法 UTF-8：{exc}")


def test_scripts_containing_ansi_unsafe_chinese_require_the_bom() -> None:
    """这些脚本面向中文用户，输出中文提示 —— 正因如此才必须带 BOM。

    若哪天有人把脚本全部改成英文，本测试会失败；那时请同步删除它并复核编码契约。
    """
    for path in POWERSHELL_SCRIPTS:
        raw = path.read_bytes()
        body = raw[len(UTF8_BOM) :] if raw.startswith(UTF8_BOM) else raw
        text = body.decode("utf-8")
        assert any("一" <= ch <= "鿿" for ch in text), (
            f"{path.name} 没有中文文本：若已全部改为英文，请同步删除本测试并复核编码契约"
        )
