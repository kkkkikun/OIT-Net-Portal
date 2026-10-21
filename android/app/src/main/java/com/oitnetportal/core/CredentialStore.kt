package com.oitnetportal.core

/**
 * 记住的校园网凭据（仅内存表示）。
 *
 * password 属于秘密：不写入日志、不进入状态详情，只用于表单预填和登录提交。
 */
data class StoredCredentials(
    val username: String,
    val password: String,
)

/**
 * 凭据存储抽象。实现方负责加密与持久化；任何读写失败按"无存凭据/未保存"处理，
 * 绝不退化为明文落盘，也不向 UI 或日志泄露底层异常细节。
 */
interface CredentialStore {
    /** 读取记住的凭据；无存凭据或数据不可用时返回 null。 */
    fun load(): StoredCredentials?

    /** 覆盖式保存凭据；保存失败静默放弃（调用方按"未记住"继续）。 */
    fun save(credentials: StoredCredentials)

    /** 清除已记住的凭据；幂等。 */
    fun clear()
}
