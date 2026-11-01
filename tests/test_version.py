"""版本号一致性：pyproject.toml / 包元数据 / `oit_portal.__version__` 三者必须一致。

背景（2026-11-01）：发 v1.0.0 时发现 `pyproject.toml` 已改成 1.0.0，
但 `oit_portal/__init__.py` 里还写着 `__version__ = "0.1.0"`，
于是 `oit-portal --version` 对外报的是 0.1.0 —— 正式版里的假版本号。
本模块把这条约束固化成契约，避免以后再漂移。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from oit_portal import __version__

ROOT = Path(__file__).resolve().parent.parent

try:  # Python 3.11+ 内置；3.9/3.10 用项目已声明的 tomli
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def _pyproject_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def test_version_matches_pyproject() -> None:
    assert __version__ == _pyproject_version()


def test_version_matches_installed_distribution() -> None:
    """已安装时，__version__ 必须等于分发包元数据里的版本。"""
    from importlib.metadata import PackageNotFoundError, version as pkg_version

    try:
        dist_version = pkg_version("oit-portal")
    except PackageNotFoundError:
        pytest.skip("当前环境未安装 oit-portal（源码树直跑），跳过")
    assert __version__ == dist_version


def test_cli_reports_the_same_version() -> None:
    """`oit-portal --version` 打印的就是这个版本号。"""
    from oit_portal.cli import _build_parser

    parser = _build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--version"])
    assert exc.value.code == 0
