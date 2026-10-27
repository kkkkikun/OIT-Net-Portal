# 提案：Android 后台自动重连

## Why

Android App 当前只能在用户手动登录后建立 Python 会话，网络恢复与回到前台也只刷新状态；应用退出前台或认证失效后仍需要人工再次提交。需要在用户明确授权并开启的前提下，利用已有脱敏桥接完成后台自动认证，同时避免无界重试、重复登录和后台失控。

## What Changes

- 新增默认关闭的「后台自动重连」设置；仅存在可用的已保存账号时允许开启，Android 13+ 先取得通知运行时权限，拒绝授权则不开启。
- 接通 `PortalForegroundService`：显示低打扰常驻通知、脱敏运行状态、打开 App 与停止服务入口；用户可随时关闭，结束本地会话也必须联动停止后台服务。
- 新增 Android 侧有界调度器，组合现有 `probe()` / `loginOnce()`：在线时低频巡检，网络恢复时触发校准，仅在确认需要认证时提交已保存凭据；失败采用有上限的退避与最小重登间隔。
- 账号或密码被拒绝、需要更新凭据、需要验证码或加密方式无法安全确认时停止自动重试并提示人工处理，禁止持续提交或猜测协议。
- 服务启动时按当前 SSID 绑定账号优先、最近使用账号其次选择唯一账号；账号删除或凭据变更时使旧后台会话失效，不继续沿用旧秘密。
- 保留现有手动登录、多账号、自动刷新和诊断能力；界面展示后台开关与实际运行状态，不再把该功能标为「尚未接入」。

### Non-goals

- 不新增开机自启、`BOOT_COMPLETED`、电池优化白名单引导或绕过 OEM 后台限制的能力。
- 不把 Python daemon / Capture 暴露到移动桥接，不实现流量心跳，也不修改 SSO / ePortal 协议。
- 不实现后台多账号轮换、失败账号自动切换或人工验证码页面。
- 不承诺被系统或厂商强制停止后仍必然运行；只使用公开的前台 Service 生命周期与 `START_STICKY` 恢复语义。

## Capabilities

### New Capabilities

- `android-background-reconnect`: Android 前台 Service 的启停、通知、账号选择、网络触发、巡检/重登调度、退避、人工介入与清理约束。

### Modified Capabilities

- `architecture`: 更新移动端凭据生命周期描述，区分 Composition 中的短暂明文与既有 Keystore 加密账号存储，并约束后台服务只能在用户显式开启后读取已保存凭据；保持桥接无 daemon / Capture、返回值脱敏和 fail-closed 原则不变。

## Impact

- 主要影响 `PortalForegroundService`、`MainActivity`、`PortalViewModel`、`PortalScreen`、`SettingsStore`、账号/桥接生命周期接口及相应字符串资源。
- 新增可独立测试的 Android 调度器与 JUnit 假桥接/假时钟用例，补充 manifest、通知权限和 UI 的 pytest 静态契约；真机验证通知、后台运行、断网恢复、停止与进程回收。
- 不新增第三方依赖，不修改 `oit_portal/mobile_bridge.py` 的能力边界，不触碰 `CAPTURED`、`docs/protocol-notes.md`、SSO/ePortal 或 Python daemon。
- 凭据仍只由 `AndroidKeystoreAccountStore` 解密读取；通知、诊断、偏好和日志不得包含账号密码、Cookie、token、原始 URL 或异常详情。

## 回滚方案

用户关闭开关或结束本地会话即停止服务、注销网络回调、取消协程并释放 Python 会话。代码回滚时恢复「尚未接入」占位并停用服务入口；新增的非敏感开关/状态偏好可保留为无效数据，无需迁移或删除既有加密账号，也不影响桌面/Termux/Linux 实现。
