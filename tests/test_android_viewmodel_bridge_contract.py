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
        "fun loginWithCredentials(", maxsplit=1)[1].split(
        "private fun applyLoginResult", maxsplit=1)[0]


def _cleared_body() -> str:
    return VIEW_MODEL_SOURCE.split("override fun onCleared()", maxsplit=1)[1]


def _apply_result_body() -> str:
    return VIEW_MODEL_SOURCE.split("private fun applyLoginResult", maxsplit=1)[1].split(
        "private suspend fun releaseCore", maxsplit=1)[0]


def _end_session_body() -> str:
    return VIEW_MODEL_SOURCE.split("fun endLocalSession()", maxsplit=1)[1].split(
        "private fun applyLoginResult", maxsplit=1)[0]


def test_viewmodel_accepts_replaceable_core_and_injectable_factory():
    assert "private var core: PortalCoreBridge" in VIEW_MODEL_SOURCE
    assert "bridgeFactory" in VIEW_MODEL_SOURCE
    assert "suspend" in VIEW_MODEL_SOURCE
    assert "ChaquopyPortalCoreBridge" in VIEW_MODEL_SOURCE


def test_login_with_credentials_is_explicit_and_validated():
    assert "fun loginWithCredentials(username: String, password: String, remember: Boolean)" \
        in VIEW_MODEL_SOURCE
    assert "username.isBlank()" in VIEW_MODEL_SOURCE
    assert "password.isBlank()" in VIEW_MODEL_SOURCE
    assert "请输入校园网账号和密码" in VIEW_MODEL_SOURCE


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


def test_end_local_session_replaces_and_releases_core_safely():
    body = _end_session_body()
    assert "runOperation" in body
    assert "val endingCore = core" in body
    assert "core = UnavailablePortalCoreBridge()" in body
    assert "coreAvailable = false" in body
    assert "status = PortalStatus.UNKNOWN" in body
    assert "releaseCore(endingCore)" in body
    assert "disposed = true" not in body


def test_account_store_is_injected_and_prefill_is_passive():
    assert "private val accountStore: AccountStore? = null" in VIEW_MODEL_SOURCE
    assert "private val wifiIdentity: WifiIdentityProvider? = null" in VIEW_MODEL_SOURCE
    assert "savedAccounts" in VIEW_MODEL_SOURCE
    # 预填之外不存在自动提交：初始化路径不会调用登录
    init_part = VIEW_MODEL_SOURCE.split("private fun initialUiState", maxsplit=1)[1].split(
        "fun refresh()", maxsplit=1)[0]
    assert "loginOnce" not in init_part
    assert "loginWithCredentials" not in init_part
    assert "login_password" not in init_part


def test_account_state_is_metadata_only_and_prefill_carries_nonce():
    assert "val savedAccounts: List<AccountInfo>" in VIEW_MODEL_SOURCE
    assert "val prefill: PrefillCredentials? = null" in VIEW_MODEL_SOURCE
    assert "val nonce: Int" in VIEW_MODEL_SOURCE
    assert "nextNonce()" in VIEW_MODEL_SOURCE


def test_ssid_preselect_prefers_bound_account_then_last_used():
    body = VIEW_MODEL_SOURCE.split("private fun choosePrefill", maxsplit=1)[1].split(
        "private fun nextNonce", maxsplit=1)[0]
    assert "it.boundSsid.isNotBlank() && it.boundSsid == currentSsid" in body
    assert "loadLastUsedId()" in body
    # SSID 绑定匹配优先于最近使用
    assert body.index("boundSsid == currentSsid") < body.index("loadLastUsedId()")


def test_accounts_persisted_only_after_confirmed_login_success():
    body = VIEW_MODEL_SOURCE.split(
        "private fun persistAccount", maxsplit=1)[1].split(
        "private fun applyLoginResult", maxsplit=1)[0]
    assert "LoginOutcome.ALREADY_ONLINE, LoginOutcome.LOGGED_IN" in body
    assert "store.upsert(" in body
    assert "store.remove(username)" in body
    assert "saveLastUsedId(username)" in body
    assert "else -> Unit" in body  # 失败不动已存账号
    # 保存发生在登录结果确认之后
    login_body = _login_body()
    apply_call = "applyLoginResult(result)"
    persist_call = "persistAccount(username, password, remember, result)"
    assert apply_call in login_body
    assert persist_call in login_body
    assert login_body.index(apply_call) < login_body.index(persist_call)


def test_password_is_not_stored_by_viewmodel():
    """凭据加密存储在独立 core 类中，ViewModel 不得直接触碰持久化/加密 API。

    注意：PrefillCredentials 内存载荷含 val password 属正常设计（仅表单预填），
    这里只禁止持久化与加密原语。"""
    forbidden = (
        "SavedStateHandle",
        "SharedPreferences",
        "getSharedPreferences",
        "DataStore",
        "Base64",
        "Cipher",
        "KeyStore",
        "System.getenv",
        "Log.",
        "println(",
    )
    for marker in forbidden:
        assert marker not in VIEW_MODEL_SOURCE
