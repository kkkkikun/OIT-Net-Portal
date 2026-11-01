"""OIT 校园网静默自动登录与保活工具（Windows / Termux 共用核心）。"""

try:
    # 版本号以包元数据为准，避免与 pyproject.toml 漂移
    # （2026-11-01：pyproject 已是 1.0.0，这里还写着 0.1.0，
    #  `oit-portal --version` 会对外报 0.1.0 —— 正式版里的假版本号）
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("oit-portal")
except Exception:
    # 未安装（源码树直跑）或极老 Python：回落到与 pyproject.toml 一致的字面量
    __version__ = "1.0.0"

__all__ = ["__version__"]
