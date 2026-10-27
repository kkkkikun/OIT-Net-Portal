# 后台自动重连真机验收报告（openspec change: android-background-auto-reconnect，任务 5.3）

- **日期**: 2026-10-27
- **设备**: vivo V1936A（Z5x），Android 9（SDK 28），Funtouch OS，USB ADB（6764b2e）
- **被测 APK**: `android/app/build/outputs/apk/debug/app-debug.apk`（2026-10-25 14:14 构建，含 CampusNetworkBinder + 后台自动重连；`assembleDebug`/`lintDebug`/`testDebugUnitTest` 已于 10-25 通过）
- **安装方式**: 覆盖安装（`install -r`），保留原有账号与设置数据
- **网络环境**: 校园网 OIT-JIAOSHI（5GHz），验收期间真实在线
- **方法**: ADB UI 驱动（uiautomator/input）+ `dumpsys activity services` / `dumpsys notification` / SharedPreferences（run-as）三方可交叉验证，关键节点截图

## 结论总览

| # | 验收路径 | 结果 | 关键证据 |
|---|---------|------|---------|
| 1 | 默认关闭 | ✅ 通过 | 首装后 prefs 无 `enabled` 键（覆盖安装前后均无）；设置页开关=false；JUnit 默认值用例覆盖 |
| 2 | 显式开启 → 前台服务 + 常驻通知 | ✅ 通过 | `ServiceRecord isForeground=true`；通知 `id=1001`（channel=校园网守护）文案=`网络在线，后台巡检中`，1 个 action；prefs `enabled=true/MONITORING` |
| 3 | 通知「停止」 | ✅ 通过 | 点击停止 → 服务停止（0 ServiceRecord）、通知移除（活跃列表 0 条）、prefs 写入 `enabled=false/STOPPED/后台自动重连已关闭` |
| 4 | 后台断网自动重连（监控/恢复） | ✅ 通过 | `svc wifi disable` 75s：detail=`等待网络恢复`（OFFLINE 不提交凭据）、服务全程存活；`svc wifi enable` 12s 内重连 OIT-JIAOSHI，探测 ONLINE 后回到 `网络在线，后台巡检中`（见 `E_offline_recovery_timeline.log`） |
| 5 | CAPTIVE 自动认证 | ⚠️ 未能自然触发 | 断网期间服务端会话保持在线，恢复后探测直接 ONLINE（不满足登录条件）；路径由 48 例 JUnit「CAPTIVE 才登录」覆盖。有意未人为注销（可能触发验证码导致真机断网） |
| 6 | 三次失败 / 人工介入 | ⚠️ 未实机执行 | 需改写真实保存的凭据或删除真实账号，不对用户真机数据做破坏性操作；路径由 JUnit 三次 FAILED/账号失效用例覆盖 |
| 7 | 结束本次会话 | ✅ 通过 | 服务停止（0 ServiceRecord）+ 开关自动置关（`enabled=false/STOPPED`），符合设计 4.2「同时停止 UI 与 Service 两侧会话」 |
| 8 | 进程回收（划卡） | ⚠️ 厂商行为，已记录 | vivo Funtouch：划卡 = 立即杀进程，**START_STICKY 不重启**（监控 70s 无复活）。符合设计预测（"厂商后台限制…真机记录实际结果，不加入绕过机制"） |
| 9 | Android 13+ 通知权限 | ⬜ 无设备 | 验收设备为 Android 9；标注未覆盖 |

## 发现的问题

### P1（缺陷候选，建议后续修复）：重开 App 不恢复服务，且状态文本陈旧

复现：服务运行中（enabled=true）→ 最近任务划卡（Funtouch 杀进程，sticky 不重启）→ 重新打开 App → UI 显示开关=开、状态=`网络在线，后台巡检中`，但 `dumpsys` 确认服务未运行（0 ServiceRecord）。

- 设计只规定"系统回收后由 START_STICKY 恢复"，未规定 Activity 重启时的行为；vivo 划卡属于强制停止语义，系统不会 sticky 重启。
- 建议修复方向：Activity/ViewModel 初始化时若 `enabled=true` 且服务未运行 → 重新 `startForegroundService`（或按产品决策纠正状态存储并提示用户）。

### P2（环境事实，已记录）：vivo 默认关闭应用通知

验收前 App 级 `importance=NONE`，通知入队 16 条、展示 0 条——前台服务静默运行。已在系统设置中开启「允许通知」（截图 `A0_vivo_notification_enabled.png`）并保留。**建议**：文档增加指引（vivo/OPPO 等厂商需手动允许通知，否则看不到常驻通知与人工介入提醒）；可考虑检测通知被系统禁用时在 App 内提示。

## 设备状态变更（验收留下的）

1. App 通知权限：关 → **开**（保留，应用预期行为需要常驻通知）
2. 后台自动重连开关：关 → （测试中多次切换）→ **关**（已恢复用户原始状态）
3. Wi-Fi：测试期间关闭约 75 秒后恢复，当前正常连接 OIT-JIAOSHI
4. 屏幕常亮（`svc power stayon usb`）：已复位

## 证据文件

| 文件 | 内容 |
|------|------|
| `A1_settings_toggle_on.png` | 开启态设置页（开关+状态文本） |
| `A2_notification_shade.png` | 常驻通知展示（网络在线，后台巡检中） |
| `A0_vivo_notification_enabled.png` | vivo 通知权限开启 |
| `B1_notification_expanded_stop.png` | 通知展开态（停止 action） |
| `C1_settings_toggle_off.png` | 关闭态设置页 |
| `D1_settings_toggle_reenabled.png` | 再次开启（阶段 D） |
| `E_offline_recovery_timeline.log` | 断网→恢复全程状态采样（prefs/dumpsys/SSID） |
| `G1_after_end_session.png` | 结束会话后 |
| `H1_recents.png` / `H2_swipe_away_watch.log` | 划卡操作与 70s 监控（进程/服务未复活） |
