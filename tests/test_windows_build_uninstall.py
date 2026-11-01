"""Windows 构建 / 卸载脚本的契约。

背景（2026-11-01，在用户自己的中文 Windows / PowerShell 5.1 上实测）：

1. `build_windows.ps1` 原本执行 `pip install ".[tray]" pyinstaller`，
   会**重装本项目**并重新生成 `Scripts\\oit-portal-tray.exe`；
   而托盘 App 正在运行时该 exe 被 Windows 锁住 →
   pip 报 `[WinError 5] 拒绝访问`，构建在第一步就失败。
   （更正：当时的解法是「不重装本项目」，结果在 CI 上暴露出 requests 缺失；
   真正的根因是「托盘进程在跑」，解法是**先停托盘再正常装依赖**。）
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


def test_build_script_installs_project_dependencies() -> None:
    """构建必须装项目依赖 —— 少了 requests，生成图标那步就 ModuleNotFoundError。

    回归：2026-11-01 首轮 GitHub Actions 里 Windows job 就是挂在
    `from oit_portal.tray import ...` 报 `No module named 'requests'`。
    托盘模块会间接 import requests / pycryptodome，只装 pystray+pillow+pyinstaller 不够。
    """
    assert '".[tray]"' in BUILD, "必须安装项目本体 + tray extra，否则托盘模块的依赖缺失"
    assert "pyinstaller" in BUILD


def test_build_script_stops_the_running_tray_before_installing() -> None:
    """重装会重写入口 exe，托盘在跑时 exe 被锁住 → 必须**先停托盘再装**。

    更正：先前一度以为「不重装本项目」才是解法（于是只装 pystray/pillow/pyinstaller），
    结果在 CI 上暴露出 requests 缺失。真正的根因是「托盘进程在跑」，
    不是「要重装」—— 先停托盘，正常装依赖即可。
    """
    assert 'Get-Process -Name "oit-portal-tray"' in BUILD
    assert 'Stop-Process -Name "oit-portal-tray"' in BUILD
    stop_at = BUILD.index('Stop-Process -Name "oit-portal-tray"')
    install_at = BUILD.index("pip install")
    assert stop_at < install_at, "停止托盘必须发生在 pip install 之前，否则入口 exe 仍被占用"


def test_build_script_refuses_to_overwrite_a_running_exe() -> None:
    """产物正在运行时给出明确提示，而不是让 PyInstaller 报一句看不懂的错。"""
    assert "Get-Process -Name \"OIT-Portal\"" in BUILD
    assert "正在运行" in BUILD
    assert "--paths" in BUILD, "应通过 --paths 从源码树导入 oit_portal"


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
