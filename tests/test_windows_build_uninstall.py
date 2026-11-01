"""Windows 构建 / 卸载脚本的契约。

背景（2026-11-01，在用户自己的中文 Windows / PowerShell 5.1 上实测）：

1. `build_windows.ps1` 原本执行 `pip install ".[tray]" pyinstaller`，
   会**重装本项目**并重新生成 `Scripts\\oit-portal-tray.exe`；
   而托盘 App 正在运行时该 exe 被 Windows 锁住 →
   pip 报 `[WinError 5] 拒绝访问`，构建在第一步就失败。
2. `uninstall_windows.ps1` 原本用 PATH 上的 `python` 和 `oit-portal`：
   装在 venv 里时两者都不指向实际安装位置（`oit-portal` 根本不在 PATH 上），
   命令找不到被 `2>$null` 吞掉 → 什么都没卸载，却照旧打印「卸载完成。」。
3. `uninstall_windows.ps1` 没有「卸载干净了没有」的核实环节，
   与安装脚本「无条件打印完成！」是同一类假成功。

本模块把这三条固化成契约。
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
BUILD = (SCRIPTS / "build_windows.ps1").read_text(encoding="utf-8-sig")
UNINSTALL = (SCRIPTS / "uninstall_windows.ps1").read_text(encoding="utf-8-sig")


def test_build_script_does_not_reinstall_the_project() -> None:
    """构建时不得重装本项目 —— 会重写入口 exe，托盘在运行时就被锁住。"""
    assert ".[tray]" not in BUILD, "pip install .[tray] 会重装本项目，重写被占用的入口 exe"
    assert "pystray" in BUILD and "pillow" in BUILD and "pyinstaller" in BUILD
    assert "--paths" in BUILD, "应通过 --paths 从源码树导入 oit_portal，而不是靠安装"


def test_build_script_refuses_to_overwrite_a_running_exe() -> None:
    """产物正在运行时给出明确提示，而不是让 PyInstaller 报一句看不懂的错。"""
    assert "Get-Process -Name \"OIT-Portal\"" in BUILD
    assert "正在运行" in BUILD


def test_uninstall_script_takes_an_explicit_python() -> None:
    """装在 venv 里时，卸载必须知道用哪个解释器。"""
    assert "-Python" in UNINSTALL, "卸载脚本应支持 -Python 指定解释器"
    assert "$Python -m pip uninstall -y oit-portal" in UNINSTALL
    assert "$Python -m oit_portal.cli stop" in UNINSTALL


def test_uninstall_script_does_not_rely_on_path_commands() -> None:
    """PATH 上的 oit-portal / python 在 venv 场景下并不存在。"""
    for bare in ("oit-portal stop", "python -m pip uninstall"):
        assert bare not in UNINSTALL, f"不应直接调用 PATH 上的 {bare}"


def test_uninstall_script_verifies_the_result() -> None:
    """卸载完必须核实：包真的没了、自启项真的没了。"""
    assert "pip show oit-portal" in UNINSTALL
    assert "CurrentVersion\\Run" in UNINSTALL
    assert "警告" in UNINSTALL, "未清理干净时必须明确警告，而不是照报成功"


def test_uninstall_script_cleans_pip_leftovers() -> None:
    """pip 卸载会静默跳过被占用的入口 exe，并留下 ~ 前缀的临时目录。

    实测：pip 照样打印「Successfully uninstalled」，但
    `Scripts\\oit-portal*.exe` 和 `site-packages\\~it_portal*` 还在，
    用户 PATH 上仍能跑到一个指向已删包的旧启动器。
    """
    assert "oit-portal*.exe" in UNINSTALL, "必须清掉残留的入口 exe"
    assert "~it_portal*" in UNINSTALL, "必须清掉 pip 留下的 ~ 前缀临时目录"
    assert "sysconfig" in UNINSTALL, "要从解释器本身问出 scripts / purelib 路径"


def test_uninstall_script_keeps_config_unless_purged() -> None:
    """默认保留配置目录，-Purge 才删除。"""
    assert "-Purge" in UNINSTALL
    assert "Remove-Item (Join-Path $env:APPDATA \"oit-portal\")" in UNINSTALL
    assert "已保留 %APPDATA%\\oit-portal" in UNINSTALL
