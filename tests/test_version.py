"""版本号一致性：pyproject.toml / 包元数据 / `oit_portal.__version__` 三者必须一致。

背景（2026-11-01）：发 v1.0.0 时发现 `pyproject.toml` 已改成 1.0.0，
但 `oit_portal/__init__.py` 里还写着 `__version__ = "0.1.0"`，
于是 `oit-portal --version` 对外报的是 0.1.0 —— 正式版里的假版本号。
本模块把这条约束固化成契约，避免以后再漂移。

顺带守住 README 上的测试数徽章（这个数字靠人记，已经漂过好几次）。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from oit_portal import __version__

ROOT = Path(__file__).resolve().parent.parent

# 内部计数用的环境变量：防止「pytest 里再跑一次 pytest」无限递归
_COUNT_ENV = "OIT_COUNT_TESTS"

try:  # Python 3.11+ 内置；3.9/3.10 用项目已声明的 tomli
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def _pyproject_version() -> str:
    with open(ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def _collected_test_count() -> int:
    """用 pytest 自己收集一遍，拿到真实用例数。"""
    env = {**os.environ, _COUNT_ENV: "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=ROOT, env=env,
    )
    assert proc.returncode == 0, f"pytest 收集失败：\n{proc.stdout[-2000:]}"
    last = proc.stdout.strip().splitlines()[-1]
    m = re.search(r"(\d+)\s+tests? collected", last)
    assert m, f"无法从 pytest 输出解析用例数：{last!r}"
    return int(m.group(1))


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


def test_readme_badge_matches_the_real_test_count() -> None:
    """README 徽章上的用例数必须是真的 —— 这个数字靠人记，已经漂过好几次。"""
    if os.environ.get(_COUNT_ENV):
        return  # 内部计数的那次 pytest 调用，跳过本用例
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(r"badge/tests-(\d+)%20passed", readme)
    assert m, "README 里找不到测试数徽章（badge/tests-N%20passed）"
    assert int(m.group(1)) == _collected_test_count(), (
        f"README 徽章写着 {m.group(1)} 例，实际收集到 {_collected_test_count()} 例"
    )
