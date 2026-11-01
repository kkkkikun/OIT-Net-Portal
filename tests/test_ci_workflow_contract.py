r"""GitHub Actions 工作流的契约。

背景（2026-11-01，本项目首轮 CI 三条根因全部在这里）：

1. **Android job 的构建机 Python 必须和 App 内嵌的 Python 同版本**。
   Chaquopy 要求「构建机的 Python 大小版本 == App 内嵌的 Python 版本」，
   App 内嵌版本在 `android/app/build.gradle.kts` 的 `chaquopy { version = ... }`。
   runner 镜像自带 Python 3.12，App 要 3.10 → 构建报 `Couldn't find Python 3.10`。
2. **Android SDK 许可要显式接受**：`sdkmanager` 是交互式的，
   不先 `yes | sdkmanager --licenses` 就会卡在 `(y/N)?` 上。
3. **不要再用 `android-actions/setup-android`**：它默认去装早已下架的
   `tools` 包，sdkmanager 以 exit 1 挂掉整步。
4. **发布说明按标签小节抽取时别用正则**：`'['` 在 ERE 里是字符类开头，
   `awk '$0 ~ "^## \["'` 实测一行都匹配不到 → 发布说明退化成一句占位话。

本模块把这四条固化成契约，防止 workflow 与 App 配置再次走偏。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CI_YML = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
RELEASE_YML = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
GRADLE_KTS = (ROOT / "android/app/build.gradle.kts").read_text(encoding="utf-8")

WORKFLOWS = {"ci.yml": CI_YML, "release.yml": RELEASE_YML}


def _app_python_version() -> str:
    """App 内嵌的 Python 版本（Chaquopy chaquopy { defaultConfig { version = ... } }）。"""
    m = re.search(r'version\s*=\s*"(\d+\.\d+)"', GRADLE_KTS)
    assert m, "android/app/build.gradle.kts 里找不到 chaquopy 的 version 配置"
    return m.group(1)


def _workflow_python_versions(text: str) -> list[str]:
    """workflow 里 setup-python 声明的 python-version 列表。"""
    return re.findall(r'python-version:\s*"([\d.]+)"', text)


def test_app_python_version_is_pinned_and_documented() -> None:
    """App 内嵌的 Python 版本必须显式写死，且带上原因注释。"""
    assert _app_python_version(), "chaquopy 的 Python 版本不应为空"
    assert "构建机的 Python 大小版本必须与这里一致" in GRADLE_KTS


def test_android_job_python_matches_app_python() -> None:
    """CI / 发版 workflow 装的 Python 必须与 App 内嵌版本一致。"""
    app_py = _app_python_version()
    for name, text in WORKFLOWS.items():
        versions = _workflow_python_versions(text)
        assert app_py in versions, (
            f"{name} 的 setup-python 版本 {versions} 里没有 App 需要的 {app_py} —— "
            f"Chaquopy 会报 \"Couldn't find Python {app_py}\""
        )


def test_android_job_accepts_sdk_licenses() -> None:
    """sdkmanager 是交互式的，必须显式接受许可。"""
    for name, text in WORKFLOWS.items():
        assert "sdkmanager" in text, f"{name} 里没有 sdkmanager"
        assert "--licenses" in text, f"{name} 没有接受 Android SDK 许可的步骤"


def test_android_job_does_not_use_the_retired_tools_package_action() -> None:
    """android-actions/setup-android 会去装早已下架的 tools 包 → 会把整步搞挂。"""
    for name, text in WORKFLOWS.items():
        assert "uses: android-actions/setup-android" not in text, (
            f"{name} 还在用 android-actions/setup-android，它会去装下架的 tools 包"
        )


def test_release_notes_use_index_not_regex() -> None:
    """抽取 CHANGELOG 小节要用 index()，正则里的 '[' 是字符类开头。"""
    assert "index($0," in RELEASE_YML, "发布说明抽取应改用 index() 做前缀匹配"
    assert '$0 ~ "^## \\["' not in RELEASE_YML, "不要再用带方括号的正则匹配标题"


def test_release_job_checks_out_the_tag() -> None:
    """手动触发发版时，构建与说明都应按标签内容走。"""
    assert RELEASE_YML.count("ref: ${{ inputs.tag || github.ref_name }}") >= 3
