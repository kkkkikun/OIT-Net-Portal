# Android 工程（Debug APK 已构建，第二轮真机验收通过）

本目录是路线 B 的 Android 实现：Kotlin + Jetpack Compose UI，通过 Chaquopy 17.1.0 按需复用仓库根目录的 Python 核心。

## UI/UX 设计（2026-10-23）

- 主导航分为「连接 / 设置 / 诊断」三个入口，连接页优先显示状态、提示、登录表单和刷新操作。
- 采用轻量 Material 3 主题：浅灰蓝背景、蓝色品牌主色、统一圆角与间距；在线/待认证/离线/未知状态同时使用文字与颜色表达。
- 设置集中管理两个自动刷新选项、后台自动重连、已保存账号和本地会话结束；后台自动重连默认关闭，仅在用户显式开启后运行。
- 诊断页独立展示当前状态、提示和最多 10 条会话内脱敏事件。
- 桌面图标：自适应启动图标（`mipmap-anydpi-v26`，品牌蓝渐变底 + 白色 Wi-Fi 信号前景），同时提供圆角变体与 Android 13 主题图标（monochrome）；minSdk 26 无需旧版 PNG 兜底。
- UI 仅调用现有 ViewModel 回调，不新增 UI 依赖，不改 Python 认证核心或凭据存储策略。
- 详细提案、设计与验收要求见 `openspec/changes/android-ui-refresh/`。

## 当前源码能力

- `MainActivity` 初始仍使用 `UnavailablePortalCoreBridge`，只在用户显式提交账号和密码后，通过捕获 Application Context 的惰性工厂创建 `ChaquopyPortalCoreBridge`。
- 网络变化监听：`registerDefaultNetworkCallback`（onCreate 注册、onDestroy 注销、幂等）；Wi-Fi 断开直接置离线，恢复/能力验证通过时做有界重试探测（3 次/2s），回到前台单次探测；只探测不自动登录。
- 凭据安全存储：`AndroidKeystoreCredentialStore`（AES-256/GCM，Keystore 密钥不可导出，私目录偏好只落密文）；「记住密码」默认不勾选、不自动登录，仅登录确认成功后按勾选保存/清除。
- 设置页：网络恢复/回到前台自动刷新两个开关（`AppSettingsStore` 持久化，默认开启）。
- 后台自动重连：默认关闭；用户显式开启后由前台 Service 显示常驻通知，复用脱敏 `probe/loginOnce` 做 60 秒在线巡检、30 秒离线兜底和 CAPTIVE 自动认证；300 秒最小重登间隔、指数退避、连续三次失败后人工介入。通知可停止，结束本地会话会同时停止 UI 与后台会话；不新增开机自启或厂商后台限制绕过。
- 诊断事件：会话内最近 50 条脱敏事件（时间戳 + 登录/探测/网络/会话/设置变更），界面展示最新 10 条。
- `PortalScreen` 已挂载独立的 `PortalCredentialForm`，表单回调接入 `PortalViewModel.loginWithCredentials()`。
- 账号表单不持久化密码：密码只保存在当前 Composition 的 `remember` 状态中，并在提交回调前清空。
- 桥接创建成功后，ViewModel 才更新 `coreAvailable`；「重试登录」和「刷新状态」仅在核心可用且非忙碌时启用。
- Python 返回值在 Kotlin 侧按白名单映射，不透传原始详情、异常、URL 或会话内容。
- Python `requests.Session` 由 `MobileProbeBridge.close()` 显式释放；Kotlin 侧先调用 Python `close()`，再释放 Chaquopy 引用。
- 用户可手动结束应用内与后台 Python 认证会话；该操作不向校园网服务器发送退出请求，也不承诺清除界面中的用户名或实现内存级清零。
- Network Security Config 默认禁止明文 HTTP，仅对当前源码确认的固定探测域名、SSO 域名和 ePortal IP 设置最小范围例外。
- 首次安装缺少 `protocol.json` 时，移动端仅对当次页面明确可解析的 CryptoJS AES 登录表单发送加密后的密码；普通明文表单、外链/未知加密、参数不完整、跨域表单、验证码、无表单 SPA 或未知协议均安全失败。

## 明确未接通（有意延后）

- Capture：本校协议已实测确认，移动端首装可无 `protocol.json` fail-closed 登录，非必需；待协议变动或换校适配时再接入。

后台自动重连代码已接通，但尚未完成真机后台生命周期验收。厂商强杀、用户强制停止后的行为以系统实际表现为准，不承诺必然恢复。

## 构建方式

无 Gradle Wrapper，使用本机 Gradle 8.9（`~/.gradle/wrapper/dists/`）+ `ANDROID_HOME=~/Android/Sdk`；
依赖解析经 HTTP 代理时只通过命令行 `-Dhttp(s).proxyHost/-Dhttp(s).proxyPort` 传入，不写入项目配置。
依赖已缓存且当前网络不可达时，可在 Gradle 命令加 `--offline`，避免直连 Maven 重试造成长时间等待。

## 验证状态

- 2026-10-24：pytest 264 用例全绿（无网络）+ Android `testDebugUnitTest` 48 例通过 + `assembleDebug`/`lintDebug` 通过。
- 真机验收：第一、二轮已通过；第三轮新版 UI 的覆盖安装、三页导航、设置持久化、实际登录、Wi-Fi 断开/恢复、前台刷新和本地会话已通过 ADB 验证，视觉暂时接受，细节后续再优化。
- 后台自动重连的开启/通知停止、后台断网自动认证、人工介入、结束会话和进程回收仍待真机验证；当前 ADB 设备未连接，未将这些路径记为通过。Android 13+ 通知权限路径也待可用设备验证。
