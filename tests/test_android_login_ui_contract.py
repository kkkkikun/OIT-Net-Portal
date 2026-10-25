"""首次手动登录 UI 接线的离线源码契约检查。"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE_ROOT = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" / "com" / "oitnetportal"
)
ACTIVITY_SOURCE = (APP_SOURCE_ROOT / "MainActivity.kt").read_text(encoding="utf-8")
SCREEN_SOURCE = (APP_SOURCE_ROOT / "ui" / "PortalScreen.kt").read_text(encoding="utf-8")
VIEW_MODEL_SOURCE = (APP_SOURCE_ROOT / "ui" / "PortalViewModel.kt").read_text(encoding="utf-8")
FORM_SOURCE = (APP_SOURCE_ROOT / "ui" / "PortalCredentialForm.kt").read_text(encoding="utf-8")


def test_activity_provides_lazy_application_context_bridge_factory():
    assert "val appContext = applicationContext" in ACTIVITY_SOURCE
    assert "bridgeFactory = { username, password ->" in ACTIVITY_SOURCE
    assert "ChaquopyPortalCoreBridge.create(" in ACTIVITY_SOURCE
    assert "appContext, username, password" in ACTIVITY_SOURCE
    assert "UnavailablePortalCoreBridge()" in ACTIVITY_SOURCE


def test_activity_does_not_start_python_during_oncreate():
    body = ACTIVITY_SOURCE.split("override fun onCreate", maxsplit=1)[1]
    assert "Python.start" not in body
    assert "ChaquopyPortalCoreBridge.create" not in body
    assert "loginWithCredentials" not in body


def test_screen_mounts_existing_credential_form():
    assert "onCredentialsSubmit: (String, String, Boolean) -> Unit" in SCREEN_SOURCE
    assert "onCredentialsSubmit = viewModel::loginWithCredentials" in SCREEN_SOURCE
    assert "PortalCredentialForm(" in SCREEN_SOURCE
    assert "onSubmit = onCredentialsSubmit" in SCREEN_SOURCE
    assert "isBusy = state.isBusy" in SCREEN_SOURCE


def test_retry_and_refresh_require_connected_core():
    assert 'Text("重试登录")' in SCREEN_SOURCE
    assert SCREEN_SOURCE.count("state.coreAvailable && !state.isBusy") >= 2


def test_ui_wiring_does_not_persist_credentials():
    sources = (ACTIVITY_SOURCE, SCREEN_SOURCE)
    forbidden = (
        "rememberSaveable",
        "SavedStateHandle",
        "SharedPreferences",
        "DataStore",
        "System.getenv",
        "Log.",
        "println(",
    )
    for source in sources:
        for marker in forbidden:
            assert marker not in source


def test_viewmodel_gives_credential_first_prompt_when_factory_exists():
    assert "请输入校园网账号和密码" in VIEW_MODEL_SOURCE
    assert "bridgeFactory == null" in VIEW_MODEL_SOURCE
    assert "Python 核心桥接尚未接入" in VIEW_MODEL_SOURCE
    assert "请先输入校园网账号和密码" in VIEW_MODEL_SOURCE


def test_screen_exposes_local_session_close_without_server_logout_claim():
    assert "onEndSession: () -> Unit" in SCREEN_SOURCE
    assert "onEndSession = viewModel::endLocalSession" in SCREEN_SOURCE
    assert 'Text("结束本次会话")' in SCREEN_SOURCE
    assert "不会向校园网服务器发送退出请求" in SCREEN_SOURCE
    assert "(state.coreAvailable || state.backgroundAutoReconnectEnabled) && !state.isBusy" in SCREEN_SOURCE


def test_screen_wires_account_management_and_prefill():
    assert "onSelectAccount = viewModel::selectAccount" in SCREEN_SOURCE
    assert "onDeleteAccount = viewModel::deleteAccount" in SCREEN_SOURCE
    assert "onUpdateAccountMeta = viewModel::updateAccountMeta" in SCREEN_SOURCE
    assert "prefill = state.prefill" in SCREEN_SOURCE
    assert "savedAccounts = state.savedAccounts" in SCREEN_SOURCE
    assert "AccountManagementDialog(" in SCREEN_SOURCE
    assert "管理已保存账号" in SCREEN_SOURCE


def test_wifi_permission_requested_only_via_user_initiated_entry():
    assert "RequestPermission()" in SCREEN_SOURCE
    assert "onWifiPermissionResult()" in SCREEN_SOURCE
    assert "AndroidWifiIdentityProvider.requiredPermission()" in SCREEN_SOURCE
    # 权限申请只发生在用户点击回调里，不在组合/启动路径自动发起
    assert "onRequestWifiPermission = {" in SCREEN_SOURCE
    dialog_source = (APP_SOURCE_ROOT / "ui" / "PortalAccountManager.kt").read_text(
        encoding="utf-8")
    assert "授权 Wi-Fi 名称读取" in dialog_source
    assert "password" not in dialog_source  # 管理对话框只展示脱敏元数据
