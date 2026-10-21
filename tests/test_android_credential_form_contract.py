"""账号表单组件的离线源码契约检查。"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORM_PATH = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" /
    "com" / "oitnetportal" / "ui" / "PortalCredentialForm.kt"
)
FORM_SOURCE = FORM_PATH.read_text(encoding="utf-8") if FORM_PATH.is_file() else ""


def test_form_exposes_stateful_submit_callback():
    assert "@Composable" in FORM_SOURCE
    assert "fun PortalCredentialForm(" in FORM_SOURCE
    assert "onSubmit: (String, String, Boolean) -> Unit" in FORM_SOURCE
    assert "isBusy: Boolean" in FORM_SOURCE
    assert "enabled: Boolean" in FORM_SOURCE


def test_password_field_is_masked_and_single_line():
    assert "PasswordVisualTransformation" in FORM_SOURCE
    assert "KeyboardType.Password" in FORM_SOURCE
    assert "singleLine = true" in FORM_SOURCE
    assert "contentDescription" in FORM_SOURCE


def test_submit_requires_credentials_and_not_busy():
    assert "username.isBlank()" in FORM_SOURCE
    assert "password.isBlank()" in FORM_SOURCE
    assert "!isBusy" in FORM_SOURCE
    assert "enabled" in FORM_SOURCE


def test_password_state_is_cleared_before_callback():
    clear_password = 'password = ""'
    submit_call = "onSubmit("
    assert clear_password in FORM_SOURCE
    assert submit_call in FORM_SOURCE
    assert FORM_SOURCE.index(clear_password) < FORM_SOURCE.index(submit_call)


def test_save_account_checkbox_defaults_unchecked_without_prefill():
    assert "Checkbox(" in FORM_SOURCE
    assert "saveAccount" in FORM_SOURCE
    assert "prefill?.saveAccount ?: false" in FORM_SOURCE
    assert "保存此账号" in FORM_SOURCE


def test_prefill_is_driven_by_nonce_and_form_keeps_no_persistence():
    # nonce 变化驱动重新预填；表单自身不做持久化
    assert "remember(prefill?.nonce)" in FORM_SOURCE
    assert "prefill: PrefillCredentials? = null" in FORM_SOURCE


def test_account_picker_shows_metadata_only():
    assert "AccountPicker(" in FORM_SOURCE
    assert "DropdownMenu" in FORM_SOURCE
    assert "savedAccounts: List<AccountInfo>" in FORM_SOURCE
    assert "onSelectAccount: (String) -> Unit" in FORM_SOURCE
    picker_body = FORM_SOURCE.split("private fun AccountPicker", maxsplit=1)[1]
    assert "password" not in picker_body  # 下拉列表只展示别名/用户名/绑定 SSID


def test_form_does_not_persist_or_call_python_directly():
    forbidden = (
        "rememberSaveable",
        "SavedStateHandle",
        "SharedPreferences",
        "DataStore",
        "System.getenv",
        "Log.",
        "println(",
        "callAttr(",
        "Python.getInstance",
    )
    for marker in forbidden:
        assert marker not in FORM_SOURCE
