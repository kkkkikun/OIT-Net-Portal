"""Android Gradle 配置不变量的离线静态回归测试。"""

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROOT_GRADLE = (PROJECT_ROOT / "android" / "build.gradle.kts").read_text(encoding="utf-8")
APP_GRADLE = (PROJECT_ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
README = (PROJECT_ROOT / "android" / "README.md").read_text(encoding="utf-8")


def test_plugin_versions_are_pinned_to_validated_baseline():
    assert 'id("com.android.application") version "8.7.3" apply false' in ROOT_GRADLE
    assert 'id("org.jetbrains.kotlin.android") version "2.0.21" apply false' in ROOT_GRADLE
    assert 'id("org.jetbrains.kotlin.plugin.compose") version "2.0.21" apply false' in ROOT_GRADLE
    assert 'id("com.chaquo.python") version "17.1.0" apply false' in ROOT_GRADLE
    assert "Chaquopy 17.1.0" in README


def test_chaquopy_config_is_top_level_and_uses_python_310():
    assert "chaquopy {" in APP_GRADLE
    assert 'version = "3.10"' in APP_GRADLE
    android_section = APP_GRADLE.split("chaquopy {", maxsplit=1)[0]
    assert "python {" not in android_section


def test_python_package_install_uses_staged_minimal_project():
    assert 'val pythonProjectDir = layout.buildDirectory.dir("pythonProject")' in APP_GRADLE
    assert 'tasks.register<Copy>("stagePythonProject")' in APP_GRADLE
    assert "from(rootProject.projectDir.parentFile)" in APP_GRADLE
    assert 'include("pyproject.toml")' in APP_GRADLE
    assert 'include("oit_portal/**/*.py")' in APP_GRADLE
    assert "install(pythonProjectDir.get().asFile.absolutePath)" in APP_GRADLE
    assert "dependsOn(stagePythonProject)" in APP_GRADLE


def test_pip_index_can_be_overridden_without_changing_default_build():
    assert 'providers.environmentVariable("PIP_INDEX_URL")' in APP_GRADLE
    assert 'options("--index-url", customIndex.get())' in APP_GRADLE
    assert 'providers.environmentVariable("PIP_EXTRA_INDEX_URL")' in APP_GRADLE
    assert 'options("--extra-index-url", extraIndex.get())' in APP_GRADLE
    assert 'providers.environmentVariable("PIP_FIND_LINKS")' in APP_GRADLE
    assert 'options("--find-links", findLinks.get())' in APP_GRADLE


def test_no_literal_placeholder_path_remains():
    placeholder = 'install("' + "." * 3 + '")'
    assert placeholder not in APP_GRADLE


def test_repository_is_not_used_as_broad_python_sourceset():
    """不能把仓库根目录整体当 sourceset。

    注意：这条约束针对的是 **Python** sourceset —— 之前 `srcDir("..")` 会让 Gradle
    扫描整个仓库（含 build 产物与 .git）。Java/Kotlin 侧允许指向 **build 目录下的
    生成产物**（本项目用它注入构建期配置），只要不是仓库根目录。
    """
    assert "python.srcDir" not in APP_GRADLE
    assert 'srcDir("..")' not in APP_GRADLE
    assert "srcDir(rootProject.projectDir" not in APP_GRADLE
    assert "srcDir(rootProject.projectDir.parentFile)" not in APP_GRADLE
    # 唯一允许的 srcDir 指向 build 目录下的生成产物
    src_dirs = re.findall(r"java\.srcDir\(([^)]+)\)", APP_GRADLE)
    assert src_dirs, "预期存在生成源码目录的注册"
    for expression in src_dirs:
        assert "buildDirectory" in expression, (
            f"srcDir 只能指向 build 目录下的生成产物，实际是 {expression}"
        )
