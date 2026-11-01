# Android 验收报告（2026-11-01，红米 K50 Ultra / Android 15）

> 设备：红米 K50 Ultra（22081212C / HyperOS 2 / Android 15 / API 35，1220×2712）
> 网络：校园 Wi-Fi `OIT-XUESHENG`（10.3.116.101/22）
> 系统字体：**汉仪新蒂黑板报体（chalk 模式，本轮刚部署的括号嵌入版）**
> 构建：已安装 `app-debug.apk`（versionCode 1 / versionName 0.1.0，minSdk 26 / targetSdk 35）
> 基线：pytest 300 passed（无网络）

本次验收的**主要目标**是补上 2026-10-31 报告里唯一未覆盖的遗留项 —— **Android 13+ `POST_NOTIFICATIONS`
运行时权限弹窗路径**（此前只有 Android 9 设备可用），并顺带在真实 Android 15 上复验 P1/P2 两项修复。

---

## 1. 验收矩阵

| # | 验收项 | 结果 | 证据 |
|---|--------|------|------|
| A1 | 冷启动渲染 + Hanyi 系统字体下的 UI 观感 | ✅ 通过 | `01-connect.png` |
| B1 | 开启后台自动重连 → 弹出 Android 13+ 通知权限框 | ✅ 通过 | `04-perm-dialog.png` |
| B2 | 允许通知 → 常驻通知真实展示 | ✅ 通过 | `06-notification-shade.png` |
| B3 | 撤销权限 → 设置页红色警告卡 + 跳转按钮 | ✅ 通过 | `07-notif-blocked-card.png`、`08-open-notif-settings.png` |
| B1b | 拒绝权限 → 后台重连保持关闭 + 提示 + 诊断事件 | ✅ 通过 | `11-perm-denied-result.png`、`13-diagnostics-denied.png` |
| C | P1：进程被杀后重开 App 自动恢复后台服务 | ✅ 通过 | `10-diagnostics-p1.png` + logcat |
| D | 真实校园网登录（OIT-XUESHENG） | ✅ 通过 | `14-login-result.png`、`19-restored-login.png` |
| E | 断网 → 恢复 的巡检状态机 | ✅ 通过 | logcat |
| F | 「结束本次会话」行为 | ✅ 通过 | `17-end-session.png` |
| P3 | 诊断事件刷爆 | ✅ **已修并回归** | §7 |
| P4 | 后台重登日志不可见 | ✅ **已修并回归** | §7 |
| — | 后台「自动重登」端到端触发 | ⚠️ **未能触发**（见 §4 P5） | — |

---

## 2. Android 13+ 通知权限弹窗路径（本次核心）

### 2.1 代码路径

`PortalScreen.kt:55-66` —— 开启「后台自动重连」时，若 `SDK_INT >= 33` 且 `POST_NOTIFICATIONS` 未授予，
且账号可用（`canEnableBackgroundReconnect()`），则先 `notificationPermissionLauncher.launch(...)`，
拿到结果再走 `onBackgroundNotificationPermissionResult(granted)`（`PortalViewModel.kt:544`）。

### 2.2 允许分支

```
点击开关 → mCurrentFocus=com.lbe.security.miui/...GrantPermissionsActivity
系统弹窗：「是否允许"OIT Net Portal"发送通知」/ 拒绝 / 始终允许
点「始终允许」→ POST_NOTIFICATIONS: granted=true
             → ServiceRecord=1，onState(MONITORING 网络在线，后台巡检中)
```

常驻通知真实入队并展示（`dumpsys notification`）：

```
NotificationRecord: pkg=com.oitnetportal id=1001 channel=campus_network_daemon
  flags=ONGOING_EVENT|FOREGROUND_SERVICE  vis=PRIVATE
  android.title=String (OIT 校园网守护)
  action[0] "停止" -> PendingIntent(startService)
  numPostedByApp=1  numUpdatedByApp=13
```

通知栏实测截图：`06-notification-shade.png`（标题「OIT 校园网守护」、正文「网络在线，后台巡检中」）。

### 2.3 拒绝分支（连续两次稳定复现）

```
点「拒绝」→ GrantPermissionsActivity: result=6
POST_NOTIFICATIONS: granted=false, flags=[ USER_SET | ... ]
ServiceRecord = 0                      ← 服务没有起来
prefs: enabled=false / status=STOPPED / detail=后台自动重连已关闭
界面提示：未授予通知权限，后台自动重连保持关闭
诊断事件：14:27:17 通知权限未授予，后台自动重连保持关闭
          14:27:17 已关闭后台自动重连
```

> **厂商差异记录**：MIUI/HyperOS 的权限弹窗左侧按钮在**用户拒绝过一次之后**会从「拒绝」变成
> 「拒绝且不再询问」，坐标不变（`[110,2399][591,2554]`）。自动化脚本按控件文本取坐标，别写死位置。

### 2.4 一次未能复现的现象

第一次弹窗（14:21:07，权限从未被请求过的「首次申请」态）上，点击左侧「拒绝」
（文字中心 x=349，已用像素分析核对确认点的就是「拒绝」）却返回 `result=4`（**授予**），
App 随即正常启动了后台服务。随后两次同样操作（一次 `pm revoke` 后、一次 `pm clear-permission-flags user-set`
回到「未问过」态）**均稳定返回 `result=6`（拒绝）**。该现象未能复现，判断为 MIUI 弹窗自身的一次性行为；
**App 侧的回调处理在三条路径下完全一致且正确**（授予→起服务 / 拒绝→保持关闭 + 提示 + 记录事件）。

---

## 3. P1 / P2 在 Android 15 上的复验

### 3.1 P1：进程被杀后重开 App 自动恢复后台服务 ✅

```
am force-stop com.oitnetportal
  pid after kill: []            ServiceRecord count: 0
  prefs: enabled=true  status=MONITORING  detail=网络在线，后台巡检中   ← 陈旧状态

am start com.oitnetportal/.MainActivity
  pid: 5444
  ServiceRecord: 1  isForeground=true  startRequested=true  callStart=true
  诊断事件：检测到后台服务已停止，已按原设置重新启动
```

同一场景还自然复现过一次：`pm revoke` 权限会杀掉 App 进程，重开后同样自动拉起了服务
（logcat pid 从 2680 → 2682，`收到命令 START_DAEMON enabled=true`）。

### 3.2 P2：系统通知被关闭时的 App 内检测 ✅

`pm revoke com.oitnetportal android.permission.POST_NOTIFICATIONS` 后回前台，设置页立刻出现：

> **系统通知已被关闭**
> 后台自动重连仍在运行，但常驻通知与登录失败提醒不会显示。部分厂商系统默认禁用应用通知，需要手动允许。
> ［打开通知设置］

「打开通知设置」按钮实测直达 `com.android.settings/com.android.settings.Settings$AppNotificationSettingsActivity`。

诊断事件：`14:24:46 系统通知被关闭，后台提醒不会显示`。

---

## 4. 本次新发现

### P3（缺陷·中）：`onCapabilitiesChanged` 未去抖，诊断事件被刷爆

`MainActivity.kt:70-81` 的注释写着「仅在系统完成网络验证后触发一次状态校准，**避免能力抖动反复探测**」，
但实现里没有任何去抖：只要 `onCapabilitiesChanged` 事件里 `NET_CAPABILITY_VALIDATED` 成立就会触发
`onNetworkAvailable()` → 一次完整门户探测 + 两条诊断事件。

实测：Wi-Fi 连上后**每 3~12 秒**产生一对事件（`检测到网络恢复，开始状态校准` +
`网络恢复校准（第 1 次）：ONLINE`），一分钟内把 50 条的环形缓冲区占满，
**关键的登录/异常事件会被直接挤掉**（本次「登录成功」事件就是这样消失的）。

### P4（缺陷·可观测性）：后台自动重登成功在日志里不可见

`BackgroundReconnectController.handleCaptive() → handleLogin() → healthyDelay()`，
重登成功后的状态文案是 `MONITORING / 网络在线，后台巡检中`，
与重登**之前**的文案**逐字相同**。`PortalForegroundService.kt:145-149` 虽然每次 `onState` 都打日志，
但两条日志长得一模一样，**无法区分「探测到 ONLINE」与「探测到 CAPTIVE → 提交凭据 → 重登成功」**。

后果：本次验收里「后台自动重登是否真的发生过」**只能靠门户侧的会话状态反推**，无法从 App 日志判定。
建议：在 `handleCaptive()` / `handleLogin()` 上补一条区分性日志（例如 `检测到需认证，开始自动重登`）。

### P5（澄清·非缺陷）：App 的探测带自己的 session cookie，外部注销打不掉它

门户侧用 `InterFace.do?method=logout`（见 §5）可以把该 IP+MAC 的**匿名**会话注销掉，
无 cookie 的 `curl` 探测立刻从 204 变成 200（AC 注入认证页）。但 **App 的探测请求带着自己的
session cookie，AC 认这个 cookie**，所以 App 的状态仍然是「网络在线」。

这说明：

- 「自动重登」的触发条件（探测返回 CAPTIVE）**必须由 AC 主动作废 App 的 cookie** 才会出现；
- 外部无法简单制造这个状态 —— **本次未能触发端到端的自动重登**，这是验收方法的边界，不是 App 的缺陷；
- 反过来看，App 的会话具备「抗外部注销」能力（cookie 被 AC 认账）。

### 附带：协议 C4.6 的接口层端点已确认

```
http://172.16.11.54/eportal/InterFace.do?method=logout
```

**不需要 `userIndex`**，仅凭 IP+MAC 即可让该客户端的门户会话失效（实测：调用后探测点 204 → 200）。
这补上了 2026-10-31 报告里「注销接口具体 API 端点待确认」的那一条。

---

## 5. 真实校园网验收

### 5.1 登录

连接页账号密码从 Keystore 回填（密码框 13 个圆点），点「登录」：

```
状态卡：校园网已连接 / CONNECTED / 网络已连接     右上角：已就绪
提示：  登录成功 / 账号已保存到本机加密存储
```

### 5.2 断网 → 恢复

```
svc wifi disable → 14:30:58 状态变化=MONITORING 等待网络恢复
svc wifi enable  → 14:31:18 状态变化=MONITORING 网络在线，后台巡检中
```

### 5.3 门户会话的 A/B 对照（证明恢复不是门户自愈）

```
14:36:52  force-stop App（pid 空 / ServiceRecord 0）+ InterFace.do?method=logout
          → 探测点 200（CAPTIVE）
14:36:54 ~ 14:38:39   连续 17 次采样，探测点**始终 200**   ← 对照组：没有 App 就回不来
14:37:49  系统按 START_STICKY 重启了前台服务（pid 5760）
14:38:42~45  探测点翻转 200 → 204                        ← App 侧把会话拉回来了
```

---

## 6. 未覆盖 / 仍未验证

| 项 | 原因 |
|----|------|
| 后台「自动重登」端到端触发 | 见 §4 P5：外部注销打不掉 App 自己的 cookie，无法制造 CAPTIVE 触发条件（**非缺陷**） |
| 协议 C4.5 多设备同账号互踢 | **已销项**（2026-11-01 用户确认）：校园网允许一个账号登录多个设备，无互踢需求 |
| 协议 C4.6 App 侧注销功能 | 接口层端点已确认（`InterFace.do?method=logout`），App 侧未接入该能力 |
| 长期稳定性（>24h 保活） | 单次会话内验证，未做长跑 |
| HyperOS 厂商省电策略下的存活率 | 未做（本次仅验证了 `START_STICKY` 被系统重启一次） |

---

## 7. 缺陷修复与真机回归（2026-11-01 当日）

按用户决定，P3 / P4 当场修掉并重新装机回归。

### 7.1 P3 修复：`NetworkValidationGate`

| 文件 | 改动 |
|------|------|
| `core/NetworkValidationGate.kt`（新增） | 只放行「验证状态从未验证翻转为已验证」这一次翻转；`reset()` 用于网络断开/换网时复位 |
| `MainActivity.kt` | `onCapabilitiesChanged` 改走闸门；`onLost` 先 `reset()` 再通知 ViewModel |
| `core/NetworkValidationGateTest.kt`（新增） | 5 例：首次验证通过触发一次 / 重复能力变化不触发 / 未验证不触发 / 丢失后重新验证再触发 / reset 复位 |

### 7.2 P4 修复：区分性状态文案

| 文件 | 改动 |
|------|------|
| `core/BackgroundReconnectController.kt` | `handleCaptive()` 提交凭据前发 `检测到需要校园网认证，正在自动重登`；`handleLogin()` 成功后发 `自动重登成功，网络在线` / `自动重登检查完成，校园网已在线`；普通巡检仍是 `网络在线，后台巡检中` |
| `core/BackgroundReconnectControllerTest.kt` | 3 例：重登路径可区分 / 普通巡检文案不变 / `ALREADY_ONLINE` 也可区分 |

### 7.3 真机回归（红米 K50 Ultra，同一台设备）

```
装机：adb install -r（保留账号与设置）→ Success
单测：61 例（新增 8）全绿；assembleDebug / lintDebug BUILD SUCCESSFUL
```

**P3 效果（同一场景前后对比）**：

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 静置 150 秒的「网络恢复校准」事件数 | 25~100 条（每 3~12 秒一对） | **0 条** |
| 一次真实 Wi-Fi 断开→重连后的诊断事件总数 | 50 条缓冲被占满 | **4 条**（3 条启动事件 + 1 条「网络连接已断开」） |

```
14:58:05 状态变化=MONITORING 等待网络恢复        ← Wi-Fi 断开
14:58:27 状态变化=MONITORING 网络在线，后台巡检中  ← Wi-Fi 恢复
诊断事件总数：4
```

**P4 效果**：普通巡检文案未被破坏（`后台自动重连：网络在线，后台巡检中`），
重登路径现在会打「检测到需要校园网认证，正在自动重登」/「自动重登成功，网络在线」，
与「本来就在线」逐字可分。

---

## 8. 验证基线

```
pytest                                   300 passed（无网络）
Android testDebugUnitTest                53 例（未改动）
真机                                     红米 K50 Ultra / HyperOS 2 / Android 15 / API 35
设备最终状态                             chalk 模式 / POST_NOTIFICATIONS granted / 后台自动重连 ON / MONITORING
```

---

## 9. 证据文件

| 文件 | 内容 |
|------|------|
| `01-connect.png` | 冷启动连接页（Hanyi 系统字体下） |
| `02-settings.png` / `03-settings-bg.png` | 设置页、后台自动重连开关（关） |
| `04-perm-dialog.png` | Android 13+ 通知权限弹窗（首次申请态） |
| `05-perm-denied.png` / `11-perm-denied-result.png` | 拒绝后的界面状态 |
| `06-notification-shade.png` | 通知栏「OIT 校园网守护 / 网络在线，后台巡检中」 |
| `07-notif-blocked-card.png` | 红色「系统通知已被关闭」警告卡 |
| `08-open-notif-settings.png` | 跳转系统通知设置页 |
| `09-diagnostics.png` / `10-diagnostics-p1.png` / `13-diagnostics-denied.png` | 诊断页事件 |
| `12-denied-notice.png` | 拒绝提示「未授予通知权限，后台自动重连保持关闭」 |
| `14-login-result.png` / `19-restored-login.png` | 登录成功 / 重新登录成功 |
| `15-connected.png` | 连接状态 CONNECTED |
| `16-perm-allowed.png` | 再次授权（左侧按钮已变「拒绝且不再询问」） |
| `17-end-session.png` | 结束本次会话 |
| `18-captive-detected.png` | 结束会话后的连接页 |
| `20-final-notification.png` | 验收结束时通知栏最终状态 |
