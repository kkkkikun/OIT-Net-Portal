"""Windows 托盘启动链路的契约。

背景（2026-11-01，在用户自己的中文 Windows / PowerShell 5.1 上实测）：

1. 用户这台机器的 Python 3.13 **没有安装 tkinter**（连 `tcl` 目录都没有，
   是最小化安装）。托盘 App 启动即崩，退出码 3。
2. 而 `install_windows_tray.ps1` 当时照旧打印「完成！请在首次弹出的窗口中
   输入账号密码。」——用户只会等一个永远不弹出的窗口。
3. 托盘原本的报错文案是「托盘依赖未安装，请执行 pip install .[tray]」，
   但 **tkinter 根本不是 pip 包**，让用户去 pip install 是把人引向死路。

本模块把这三条固化成契约。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oit_portal.tray import _dependency_error_message

SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "install_windows_tray.ps1"
).read_text(encoding="utf-8-sig")


def test_missing_tkinter_points_at_the_python_installer() -> None:
    """缺 tkinter 时必须指向 Python 安装程序，而不是 pip install。"""
    exc = ModuleNotFoundError("No module named 'tkinter'", name="tkinter")

    msg = _dependency_error_message(exc)

    assert "tkinter" in msg
    assert "Modify" in msg and "tcl/tk" in msg, "应说明如何在 Python 安装程序里补上 tcl/tk"
    assert "pip install .[tray]" not in msg, "tkinter 不是 pip 包，不能把用户引到 pip install .[tray]"
    assert "不是 pip 包" in msg, "应明确说明 tkinter 无法通过 pip 安装"
    assert "configure" in msg, "应给出不装托盘时的替代路径（命令行 configure）"


def test_other_missing_dependencies_still_point_at_pip() -> None:
    """pystray / Pillow 这类真正的 pip 包，仍然提示 pip install。"""
    exc = ModuleNotFoundError("No module named 'pystray'", name="pystray")

    msg = _dependency_error_message(exc)

    assert "pip install" in msg
    assert "Modify" not in msg


def test_install_script_preflights_tkinter_before_installing() -> None:
    """安装脚本必须在动手前就检查 tkinter，并给出可执行的指引。"""
    assert "import tkinter" in SCRIPT
    assert "tcl/tk" in SCRIPT, "应说明 tkinter 要通过 Python 安装程序补上"


def test_install_script_verifies_the_tray_actually_started() -> None:
    """启动后必须验证进程存活，不能无条件报「完成」。"""
    assert "Start-Sleep -Seconds" in SCRIPT
    assert "Get-Process" in SCRIPT
    assert "立即退出" in SCRIPT, "托盘启动即退出时应有明确报错"


@pytest.mark.parametrize("needle", ["[1/4]", "[2/4]", "[3/4]", "[4/4]"])
def test_install_script_has_four_numbered_steps(needle: str) -> None:
    assert needle in SCRIPT
