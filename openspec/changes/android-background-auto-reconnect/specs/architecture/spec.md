# Architecture Delta Spec

> 版本: 1.0.0 | 最后更新: 2026-10-24

## MODIFIED Requirements

### Requirement: 移动端凭据与密码生命周期

Android UI 中的密码 MUST 只短暂存在于 Composition 的 `remember` 状态并在提交回调前清空。需要保存时 MUST 通过既有 `AndroidKeystoreAccountStore` 加密存储；后台自动重连只能在用户显式开启后读取一个已保存账号，禁止明文持久化或扩大秘密使用范围。

#### Scenario: Android UI 处理用户密码

- **WHEN** Android UI 接收、提交或清理用户密码
- **THEN** 密码只保存在 Composition 的 remember 状态并在提交回调前清空；UI 本身不得把明文密码写入偏好、诊断或日志

#### Scenario: 已保存账号用于后台自动重连

- **WHEN** 用户显式开启后台自动重连且存在已保存账号
- **THEN** Service 仅通过 `AndroidKeystoreAccountStore` 解密读取按规则选中的一个账号，秘密只用于创建现有移动桥接；功能关闭、账号删除或会话失效后不得继续使用旧秘密

#### Scenario: 未开启后台功能或存储不可用

- **WHEN** 后台自动重连未开启，或 Keystore 账号存储无法安全读取
- **THEN** 不得为后台认证读取或退化保存明文密码；存储不可用时按无可用账号处理并提示人工操作
