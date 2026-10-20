# Android 工程骨架（WIP，未编译）

本目录是路线 B 的 Android 实现：Kotlin + Jetpack Compose UI，通过 Chaquopy 17.1.0 按需复用仓库根目录的 Python 核心。

## 当前源码能力

- `MainActivity` 初始仍使用 `UnavailablePortalCoreBridge`，只在用户显式提交账号和密码后，通过捕获 Application Context 的惰性工厂创建 `ChaquopyPortalCoreBridge`。
- `PortalScreen` 已挂载独立的 `PortalCredentialForm`，表单回调接入 `PortalViewModel.loginWithCredentials()`。
- 账号表单不持久化密码：密码只保存在当前 Composition 的 `remember` 状态中，并在提交回调前清空。
- 桥接创建成功后，ViewModel 才更新 `coreAvailable`；「重试登录」和「刷新状态」仅在核心可用且非忙碌时启用。
- Python 返回值在 Kotlin 侧按白名单映射，不透传原始详情、异常、URL 或会话内容。
- Python `requests.Session` 由 `MobileProbeBridge.close()` 显式释放；Kotlin 侧先调用 Python `close()`，再释放 Chaquopy 引用。
- 用户可手动结束应用内 Python 认证会话；该操作不向校园网服务器发送退出请求，也不承诺清除界面中的用户名或实现内存级清零。
- Network Security Config 默认禁止明文 HTTP，仅对当前源码确认的固定探测域名、SSO 域名和 ePortal IP 设置最小范围例外。
- 首次安装缺少 `protocol.json` 时，移动端仅对当次页面明确可解析的 CryptoJS AES 登录表单发送加密后的密码；普通明文表单、外链/未知加密、参数不完整、跨域表单、验证码、无表单 SPA 或未知协议均安全失败。

## 明确未接通

- Capture、设置、日志查看和后台自动重连仍未实现；自动重连开关保持禁用。
- 前台 Service 仍未接管认证流程，也没有运行时通知权限和网络恢复回调接线。
- 凭据安全存储仍未实现；当前每次手动登录都需要用户输入。
- Chaquopy `requests` 是否遵守 Android 平台明文限制、动态门户跳转目标和 IP 字面量例外仍需运行时验证。
- Gradle Wrapper 尚未生成。

## 尚未验证

Gradle 插件解析、PEP 517 本地 Python 包安装、`requests`、`pycryptodome`、Android ABI、Kotlin 编译、APK 构建、前台服务真机行为和校园网登录均未验证。

当前验证仅限于无网络 Python 测试与 Android 源码静态契约测试；这些结果不能等同于 Android 构建成功或真机验收通过。
