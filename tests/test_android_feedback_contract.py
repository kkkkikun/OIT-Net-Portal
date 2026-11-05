"""Android 端反馈通道契约。

反馈入口必须在 App 内（不跳浏览器），表单字段固定，诊断摘要必须脱敏，
提交通道复用既有 Python 桥接契约。
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ANDROID_ROOT = PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "oitnetportal"

SCREEN = (ANDROID_ROOT / "ui" / "PortalScreen.kt").read_text(encoding="utf-8")
FORM = (ANDROID_ROOT / "ui" / "FeedbackForm.kt").read_text(encoding="utf-8")
VIEW_MODEL = (ANDROID_ROOT / "ui" / "PortalViewModel.kt").read_text(encoding="utf-8")
BRIDGE = (ANDROID_ROOT / "core" / "FeedbackBridge.kt").read_text(encoding="utf-8")
SETTINGS_STORE = (ANDROID_ROOT / "core" / "FeedbackSettingsStore.kt").read_text(encoding="utf-8")


def test_settings_page_has_feedback_entry_card() -> None:
    assert "意见反馈" in SCREEN
    assert "onOpenFeedback" in SCREEN


def test_feedback_entry_is_inside_settings_page() -> None:
    """入口卡片必须挂在设置页里，而不是连接页或诊断页。"""
    settings_block = SCREEN.split("private fun SettingsPage", 1)[1]
    assert "意见反馈" in settings_block


def test_feedback_form_is_native_and_has_three_fields() -> None:
    assert "FeedbackForm(" in SCREEN or "FeedbackForm(" in FORM
    for field in ("category", "content", "withDiagnostics"):
        assert field in FORM, f"反馈表单缺少字段 {field}"


def test_feedback_form_offers_three_categories() -> None:
    for label in ("建议", "问题", "其他"):
        assert label in FORM


def test_feedback_form_rejects_empty_content() -> None:
    assert "内容不能为空" in FORM


def test_feedback_form_disables_duplicate_submit() -> None:
    assert "isSubmitting" in FORM


def test_feedback_form_does_not_collect_credentials() -> None:
    """表单不得出现账号/密码输入控件（注释里的说明文字不算）。"""
    code_lines = [
        line for line in FORM.splitlines()
        if not line.strip().startswith(("*", "//", "/*"))
    ]
    code = "\n".join(code_lines)
    assert 'label = { Text("账号") }' not in code
    assert 'label = { Text("密码") }' not in code
    assert "PasswordVisualTransformation" not in code
    # 表单里唯一的文本输入是反馈正文
    assert code.count("OutlinedTextField(") == 1


def test_bridge_contract_exposes_submit_only() -> None:
    assert "interface FeedbackBridge" in BRIDGE
    assert "suspend fun submit(" in BRIDGE
    assert "close()" in BRIDGE


def test_bridge_has_unavailable_implementation() -> None:
    assert "UnavailableFeedbackBridge" in BRIDGE


def test_settings_store_keeps_service_endpoint_locally() -> None:
    """OpenFeedback 服务地址存在本机，同学换了网络或作者换了通道时可自行改。"""
    assert "serviceEndpoint" in SETTINGS_STORE
    assert "SharedPreferences" in SETTINGS_STORE


def test_settings_store_keeps_no_channel_secret() -> None:
    """OpenFeedback 的提交接口不需要客户端密钥 —— 设置里不得再存任何凭证。

    这是迁移到 OpenFeedback 后的核心安全边界：APK 里只剩公开的 appId 与服务地址。
    """
    assert "Secret" not in SETTINGS_STORE
    assert "secret" not in SETTINGS_STORE
    assert "Token" not in SETTINGS_STORE
    assert "token" not in SETTINGS_STORE


def test_feedback_defaults_come_from_build_time_injection() -> None:
    """真实服务地址必须构建期注入，不能写进入库的源码。"""
    gradle = (PROJECT_ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert "oit.feedback.endpoint" in gradle
    assert "generateFeedbackConfig" in gradle
    # OpenFeedback 不需要客户端密钥，构建期也不再注入任何 secret
    assert "oit.feedback.secret" not in gradle
    # 入库的源码里不能出现写死的真实地址
    assert "open.feishu.cn/open-apis/bot/v2/hook/" not in SETTINGS_STORE
    assert "feishu.cn" not in SETTINGS_STORE


def test_local_properties_is_ignored_and_example_is_tracked() -> None:
    """本机配置不入库，模板要入库。"""
    import subprocess

    root = PROJECT_ROOT
    ignored = subprocess.run(
        ["git", "check-ignore", "android/local.properties"],
        cwd=root, capture_output=True, text=True,
    )
    assert ignored.returncode == 0, "android/local.properties 必须被 .gitignore 忽略"

    template = root / "android" / "local.properties.example"
    assert template.is_file(), "缺少 local.properties.example 模板"
    assert "oit.feedback.endpoint" in template.read_text(encoding="utf-8")


def test_bridge_receives_channel_secret() -> None:
    """凭证要在 Chaquopy 实现里带上，否则飞书一开校验就投递失败。"""
    chaquopy_bridge = (ANDROID_ROOT / "core" / "ChaquopyFeedbackBridge.kt").read_text(
        encoding="utf-8"
    )
    assert "secret" in chaquopy_bridge
    assert "create_mobile_feedback_bridge" in chaquopy_bridge


def test_feedback_form_does_not_claim_local_only_storage() -> None:
    """反馈现在发往 OpenFeedback 后台，界面不能说「只保存在作者本机」。"""
    assert "只保存在作者本机" not in FORM
    assert "OpenFeedback" in FORM
    # 也要如实说明断网时的行为：先存在手机里，联网后自动补发
    assert "断网" in FORM
    assert "自动补发" in FORM


def test_feedback_form_uses_openfeedback_categories() -> None:
    """分类与服务端一致：bug / feature / experience / other。"""
    for wire in ("bug", "feature", "experience", "other"):
        assert f'"{wire}"' in FORM


def test_viewmodel_wires_feedback_submission() -> None:
    assert "submitFeedback" in VIEW_MODEL
    assert "feedbackBridge" in VIEW_MODEL


def test_viewmodel_builds_sanitized_diagnostics() -> None:
    """诊断摘要必须经过脱敏，不能直接拼原始事件。"""
    assert "sanitizeDiagnostics" in VIEW_MODEL
    assert "events" in VIEW_MODEL


def test_android_bridge_is_openfeedback() -> None:
    """Android 侧注入的桥接实现已换成 OpenFeedback（回滚才换回 Chaquopy）。"""
    main = (ANDROID_ROOT / "MainActivity.kt").read_text(encoding="utf-8")
    assert "OpenFeedbackBridge.create(" in main


def test_openfeedback_bridge_carries_no_credentials() -> None:
    """OpenFeedback 的桥接实现里不得出现任何密钥/令牌字段。"""
    bridge = (ANDROID_ROOT / "core" / "OpenFeedbackBridge.kt").read_text(encoding="utf-8")
    for forbidden in ("secret", "token", "apikey", "password", "authorization"):
        assert forbidden not in bridge.lower(), f"桥接实现里不应出现 {forbidden}"


def test_android_depends_on_openfeedback_core_not_compose() -> None:
    """本 App 保留自己的表单，只用 SDK 的传输层（core），不引入 compose 模块。"""
    gradle = (PROJECT_ROOT / "android" / "app" / "build.gradle.kts").read_text(encoding="utf-8")
    assert "com.kkkkikun.openfeedback:openfeedback-core" in gradle
    assert "com.kkkkikun.openfeedback:openfeedback-compose" not in gradle
    # 版本必须固定，不用动态版本号
    assert "openfeedback-core:+" not in gradle


def test_settings_keeps_openfeedback_maven_repository() -> None:
    """SDK 仓库地址由 Gradle 属性注入，可指向本地目录做离线构建。"""
    settings = (PROJECT_ROOT / "android" / "settings.gradle.kts").read_text(encoding="utf-8")
    assert "openfeedback" in settings
    assert "oit.openfeedback.mavenUrl" in settings
