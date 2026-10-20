# Android 工程骨架（WIP，未编译）

本目录是路线 B 的 Android 实现：Kotlin + Jetpack Compose UI，通过 Chaquopy 17.1.0 按需复用仓库根目录的 Python 核心。

## 当前源码能力

- `MainActivity` 初始仍使用 `UnavailablePortalCoreBridge`，只在用户显式提交账号和密码后，通过捕获 Application Context 的惰性工厂创建 `ChaquopyPortalCoreBridge`。
- `PortalScreen` 已挂载独立的 `PortalCredentialForm`，表单回调接入 `PortalViewModel.loginWithCredentials()`。
- 账号表单不持久化密码：密码只保存在当前 Composition 的 `remember` 状态中，并在提交回调前清空。
- 桥接创建成功后，ViewModel 才更新 `coreAvailable`；「重试登录」和「刷新状态」仅在核心可用且非忙碌时启用。
- Python 返回值在 Kotlin 侧按白名单映射，不透传原始详情、异常、URL 或会话内容。
- Python `requests.Session` 由 `MobileProbeBridge.close()` 显式释放；Kotlin 侧先调用 Python `close()`，再释放 Chaquopy 引用。

## 明确未接通

- Capture、设置、日志查看和后台自动重连仍未实现；自动重连开关保持禁用。
- 前台 Service 仍未接管认证流程，也没有运行时通知权限和网络恢复回调接线。
- 凭据安全存储仍未实现；当前每次手动登录都需要用户输入。
- 校园网明文 HTTP 的 Android 网络安全策略尚未配置。
- Gradle Wrapper 尚未生成。

## 尚未验证

Gradle 插件解析、PEP 517 本地 Python 包安装、`requests`、`pycryptodome`、Android ABI、Kotlin 编译、APK 构建、前台服务真机行为和校园网登录均未验证。

当前验证仅限于无网络 Python 测试与 Android 源码静态契约测试；这些结果不能等同于 Android 构建成功或真机验收通过。
