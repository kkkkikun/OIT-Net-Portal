"""PortalViewModel 桥接生命周期的离线源码契约检查。"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIEW_MODEL_PATH = (
    PROJECT_ROOT / "android" / "app" / "src" / "main" / "java" /
    "com" / "oitnetportal" / "ui" / "PortalViewModel.kt"
)
VIEW_MODEL_SOURCE = VIEW_MODEL_PATH.read_text(encoding="utf-8")


def _login_body() -> str:
    return VIEW_MODEL_SOURCE.split(
        "fun loginWithCredentials(username: String, password: String)", maxsplit=1)[1].split(
        "private fun applyLoginResult", maxsplit=1)[0]


def _cleared_body() -> str:
    return VIEW_MODEL_SOURCE.split("override fun onCleared()", maxsplit=1)[1]


def _apply_result_body() -> str:
    return VIEW_MODEL_SOURCE.split("private fun applyLoginResult", maxsplit=1)[1].split(
        "private suspend fun releaseCore", maxsplit=1)[0]


def test_viewmodel_accepts_replaceable_core_and_injectable_factory():
    assert "private var core: PortalCoreBridge" in VIEW_MODEL_SOURCE
    assert "bridgeFactory" in VIEW_MODEL_SOURCE
    assert "suspend" in VIEW_MODEL_SOURCE
    assert "ChaquopyPortalCoreBridge" in VIEW_MODEL_SOURCE


def test_login_with_credentials_is_explicit_and_validated():
    assert "fun loginWithCredentials(username: String, password: String)" in VIEW_MODEL_SOURCE
    assert "username.isBlank()" in VIEW_MODEL_SOURCE
    assert "password.isBlank()" in VIEW_MODEL_SOURCE
    assert "请输入校园网账号和密码" in VIEW_MODEL_SOURCE


def test_password_is_not_stored_by_viewmodel():
    forbidden = (
        "val password",
        "var password",
        "SavedStateHandle",
        "SharedPreferences",
        "DataStore",
        "System.getenv",
        "Log.",
        "println(",
    )
    for marker in forbidden:
        assert marker not in VIEW_MODEL_SOURCE


def test_operations_are_serialized_and_factory_runs_on_io():
    assert "operationMutex.tryLock()" in VIEW_MODEL_SOURCE
    assert "operationMutex.unlock()" in VIEW_MODEL_SOURCE
    assert "withContext(Dispatchers.IO)" in VIEW_MODEL_SOURCE


def test_factory_adoption_stays_inside_io_ownership_scope():
    body = _login_body()
    assert "val adopted = withContext(Dispatchers.IO)" in body
    assert "factory(username, password)" in body
    assert "if (disposed)" in body
    assert "core = createdCore" in body
    assert "val createdCore = withContext(Dispatchers.IO)" not in body


def test_replacement_and_unadopted_cleanup_are_non_cancellable():
    body = _login_body()
    assert "releaseCore(oldCore)" in body
    assert "newCore?.let { releaseCore(it) }" in body
    assert "withContext(NonCancellable)" in VIEW_MODEL_SOURCE
    assert "NonCancellable + Dispatchers.IO" not in VIEW_MODEL_SOURCE


def test_new_bridge_replaces_old_core_before_old_shutdown():
    body = _login_body()
    replacement = "core = createdCore"
    old_shutdown = "releaseCore(oldCore)"
    assert replacement in body
    assert old_shutdown in body
    assert body.index(replacement) < body.index(old_shutdown)


def test_viewmodel_cleanup_shares_operation_mutex_and_uses_independent_scope():
    body = _cleared_body()
    assert "disposed = true" in body
    assert "CoroutineScope(" in body
    assert "Dispatchers.IO" in body
    assert "operationMutex.withLock" in body
    assert "val finalCore = core" in body
    assert "core = UnavailablePortalCoreBridge()" in body
    assert "releaseCore(finalCore)" in body
    assert "viewModelScope.launch" not in body
    assert "runBlocking" not in VIEW_MODEL_SOURCE


def test_failed_login_never_preserves_previous_online_state():
    body = _apply_result_body()
    assert "LoginOutcome.ALREADY_ONLINE, LoginOutcome.LOGGED_IN -> PortalStatus.ONLINE" in body
    assert "LoginOutcome.NO_NETWORK -> PortalStatus.OFFLINE" in body
    assert "LoginOutcome.NEED_CREDENTIALS -> PortalStatus.CAPTIVE" in body
    assert "LoginOutcome.CAPTCHA_REQUIRED -> PortalStatus.CAPTIVE" in body
    assert "LoginOutcome.LOGIN_REJECTED -> PortalStatus.CAPTIVE" in body
    assert "LoginOutcome.FAILED -> PortalStatus.UNKNOWN" in body
    assert "else -> it.status" not in body


def test_adopting_new_credentials_resets_status_until_verified():
    body = _login_body()
    replacement = "core = createdCore"
    reset = "status = PortalStatus.UNKNOWN"
    assert replacement in body
    assert reset in body
    assert body.index(replacement) < body.index(reset)
    assert "正在验证校园网登录状态" in body
