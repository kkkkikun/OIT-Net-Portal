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


def test_remember_checkbox_defaults_unchecked_and_prefill_is_parameterized():
    assert "Checkbox(" in FORM_SOURCE
    assert "rememberCredentials" in FORM_SOURCE
    assert "initialRemember: Boolean = false" in FORM_SOURCE
    assert "initialUsername: String = " in FORM_SOURCE
    assert "initialPassword: String = " in FORM_SOURCE


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
