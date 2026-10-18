# Android 工程骨架

本目录是路线 B 的初始骨架：Kotlin + Jetpack Compose UI，未来通过独立桥接层复用仓库根目录的 Python 核心。

## 当前实际范围

- `MainActivity`：应用入口，当前显式注入 `UnavailablePortalCoreBridge`。
- `ui/PortalScreen.kt`：主页面，容纳状态、手动登录、自动重连、Capture、设置和诊断区域。
- `ui/PortalViewModel.kt`：UI 状态与操作编排；未接入核心时只显示未接通信息，不伪造成功结果。
- `core/PortalCore.kt`：不依赖 Android API 的探测、认证、Capture 和守护接口，便于后续替换实现或提取共享边界。
- `service/PortalForegroundService.kt`：前台服务与常驻通知的生命周期边界；当前没有启动 Python 守护循环。

## 明确未接通

- 未配置 Chaquopy，未打包或调用 Python 核心。
- Capture、设置、日志查看和自动重连 UI 尚未实现；自动重连开关保持禁用。
- UI 不启动前台服务；服务本身也没有认证或保活能力。
- 凭据安全存储、会话持久化、网络恢复回调和运行时通知权限流程尚未实现。
- 未生成 Gradle wrapper，未配置校园网明文 HTTP 的网络安全策略。

## 未验证风险

根级和 app 级 Gradle 文件中的 Android/Kotlin/Compose 版本只是初始骨架基线，尚未经过构建验证。后续仍需单独验证 JDK/SDK/Gradle 兼容性、Chaquopy 运行时、`requests`、`pycryptodome` 的 Android ABI、目标 WiFi 网络绑定以及前台服务真机行为。

本次任务未构建、未运行测试、未安装依赖、未访问网络，也未生成 APK。
