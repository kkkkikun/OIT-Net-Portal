package com.oitnetportal.core

/**
 * 保存的校园网账号（仅内存表示）。
 *
 * password 属于秘密：不写入日志、不进入状态详情，只用于表单预填和登录提交。
 * id 取用户名（校园网账号天然唯一）；boundSsid 为空字符串表示不绑定 Wi-Fi。
 */
data class StoredAccount(
    val id: String,
    val alias: String = "",
    val username: String,
    val password: String,
    val boundSsid: String = "",
)

/** 账号列表展示用元数据（不含密码）。 */
data class AccountInfo(
    val id: String,
    val alias: String,
    val username: String,
    val boundSsid: String,
)

/** StoredAccount 的脱敏视图。 */
fun StoredAccount.toInfo(): AccountInfo = AccountInfo(id, alias, username, boundSsid)

/**
 * 多账号存储抽象。实现方负责加密与持久化；任何读写失败按"无存账号/未保存"处理，
 * 绝不退化为明文落盘，也不向 UI 或日志泄露底层异常细节。
 */
interface AccountStore {
    /** 读取全部已存账号；无存账号或数据不可用时返回空列表。 */
    fun loadAccounts(): List<StoredAccount>

    /** 按 id（用户名）覆盖式保存或更新账号；失败静默放弃。 */
    fun upsert(account: StoredAccount)

    /** 删除指定账号；幂等。 */
    fun remove(accountId: String)

    /** 最近成功登录使用的账号 id；无记录返回 null。 */
    fun loadLastUsedId(): String?

    /** 记录最近使用的账号 id。 */
    fun saveLastUsedId(accountId: String)
}

/**
 * 当前 Wi-Fi 标识来源。权限缺失、非 Wi-Fi 连接或系统不透露 SSID 时返回 null，
 * 调用方据此退化为"最近使用账号"预选，绝不阻塞任何功能。
 */
interface WifiIdentityProvider {
    /** 当前是否具备读取 SSID 的运行时权限。 */
    fun canReadSsid(): Boolean

    /** 当前连接的 Wi-Fi SSID（已去引号）；不可用时返回 null。 */
    fun currentSsid(): String?
}
