# Android 复验报告（2026-10-31）

> 设备：vivo V1936A / Android 9（SDK 28，1080×2340，density 480）
> 网络：校园 Wi-Fi `OIT-JIAOSHI`（10.3.136.34/22，已 VALIDATED）
> 构建：Gradle 8.9 + SDK 35 + Chaquopy Python 3.10，debug 变体
> 基线：pytest 300 passed（无网络）+ Android JUnit 53 例 + assembleDebug + lintDebug 全绿

本次把 2026-10-27 验收遗留的三项（P1 缺陷、vivo 通知静默、真实 VPN 验收）一次性做完，
并顺带修掉一个此前没被发现的界面配色缺陷。

---

## 1. P1：进程被杀后重开 App 不恢复后台重连服务（已修）

### 根因

持久化的 `enabled=true` 与「服务是否真的在跑」是两件事，两者在进程被杀后脱节：

- `BackgroundReconnectStateStore` 从 SharedPreferences 恢复 `enabled=true` 与上一次的状态文本；
- 厂商划卡直接杀进程，服务也没了，但磁盘上的 `MONITORING / 网络在线，后台巡检中` 还在；
- `PortalViewModel` 里没有任何重新拉起服务的路径 → 界面显示"后台巡检中"，实际 0 ServiceRecord。

### 修复

| 文件 | 改动 |
|---|---|
| `core/BackgroundServiceRuntime.kt`（新增） | 进程内存活标记；进程被杀即自动清空 |
| `service/PortalForegroundService.kt` | `onCreate` → `markRunning()`；`onDestroy` → `markStopped()` |
| `ui/PortalViewModel.kt` | `restoreBackgroundReconnectIfNeeded()`：初始化时若 `enabled=true` 而运行时标记缺失，则按原设置重新拉起服务并纠正陈旧状态文本 |
| `app/src/test/.../PortalViewModelTest.kt` | 新增 3 例（服务已死→重启 / 从未开启→不重启 / 服务仍在→不重启） |

### 真机复现与验证

```
# 步骤 1：杀掉进程（等价于厂商划卡，系统不做 START_STICKY 重启）
$ adb shell am force-stop com.oitnetportal
pid after kill: []            ServiceRecord count: 0
prefs: enabled=true  status=MONITORING  detail=网络在线，后台巡检中   ← 陈旧状态

# 步骤 2：重开 App
$ adb shell am start -n com.oitnetportal/.MainActivity
pid: 28119                    ServiceRecord count: 1
isForeground=true  startRequested=true  callStart=true              ← 服务已恢复
```

「诊断」页事件（同一次会话）：

```
16:15:11  检测到后台服务已停止，已按原设置重新启动
16:15:11  应用已启动，等待输入校园网凭据
```

截图：`02-diagnostics.png`（恢复事件）、`01-connect.png`（连接页）

---

## 2. P2：App 内检测系统通知被禁用并提示（已做）

### 背景

2026-10-27 验收记录：vivo 默认禁用应用通知时"通知入队 16 条、展示 0 条"，功能在跑但用户看不到任何提示。
本次把检测做进 App，并给出可点击的修复入口。

### 实现

| 文件 | 改动 |
|---|---|
| `core/NotificationStatusProvider.kt`（新增） | 通知状态抽象接口 |
| `core/AndroidNotificationStatusProvider.kt`（新增） | 三层检查：① `NotificationManagerCompat.areNotificationsEnabled()`（应用级开关 / 渠道被禁）② Android 13+ `POST_NOTIFICATIONS` 权限 ③ AppOps `POST_NOTIFICATION`（部分 ROM 用 `MODE_IGNORED` 让通知"入队但不展示"，而框架在 API 28 上不查这层） |
| `ui/PortalViewModel.kt` | `notificationsEnabled` 状态 + `refreshNotificationStatus()`（回前台时重新读取） |
| `ui/PortalScreen.kt` | 设置页红色警告卡 +「打开通知设置」直达系统页 |
| `app/src/test/.../PortalViewModelTest.kt` | 新增 2 例 |

### 真机验证（含 A/B 对照）

在 vivo 系统设置里关掉「允许通知」（用户真实路径）：

```
诊断事件：16:42:13  系统通知被关闭，后台提醒不会显示
设置页：  [系统通知已被关闭]  后台自动重连仍在运行，但常驻通知与登录失败提醒不会显示。
          部分厂商系统默认禁用应用通知，需要手动允许。   [打开通知设置]
```

截图：`05-notif-detected.png`

**A/B 对照**（确认是哪一层在起作用）：

| 场景 | AppOps | vivo「允许通知」 | 检测结果 |
|---|---|---|---|
| 1 | `deny`（adb 设置） | 开 | **未检出** —— `checkOpNoThrow` 不反映 CLI 写入的 deny |
| 2 | `deny` | 关 | 检出 |
| 3 | `default`（还原） | 关 | **仍检出** → 真正生效的是第 1 层 `areNotificationsEnabled()` |

结论：AppOps 层在本机不会误报，可作为其他 ROM 的保守兜底；主判定依赖第 1 层，已在用户真实路径上验证通过。

> 附带验证：App 的「打开通知设置」按钮能直达 vivo 的 `com.vivo.systemui...NotificationSettingsActivity` 页面。

---

## 3. 界面配色错配（已修）

### 现象

"界面不够和谐"的 App 侧根因：主题只定义了 `surface` / `surfaceVariant`，**没有定义 Material3 1.2 之后新增的 `surfaceContainer*` 角色**。而 1.3.1 的 `Card` 默认容器色取自这组角色，于是回落到 M3 基线的紫调灰，卡片与本应用灰蓝配色打架。

### 修复

- `ui/OitPortalTheme.kt`：补齐 `surfaceContainerLowest/Low/High/Highest`、`surfaceBright/Dim`、`surfaceTint`、`outlineVariant`，全部落在应用自己的中性灰蓝体系里；
- `ui/PortalScreen.kt`、`ui/PortalCredentialForm.kt`：5 处 `Card` 显式指定 `containerColor = surface`，不再依赖库版本的默认角色；
- 顺带把设置页里那个恒定禁用的「协议 Capture（待接入）」死按钮换成一行说明文字。

### 像素级前后对比

| 元素 | 修复前 | 修复后 | 期望 |
|---|---|---|---|
| 页面背景 | `#F5F7FB` | `#F5F7FB` | 不变 |
| 普通卡片 | `#E8E8F0`（M3 基线紫调灰） | `#FFFFFF` | 白卡片 |
| 后台重连卡片 | `#EEF2F8` | `#EEF2F8` | 保持分组色 |
| 导航栏 | `#FFFFFF` | `#FFFFFF` | 不变 |

### 另：设备系统字体

这台设备把系统字体改成了 **"新蒂黑板报底字"**（`settings get global cur_using_font_name`），
全机文字都被替换成装饰/等宽风格——这是"界面不和谐"观感的主要来源，属**系统级设置**，App 侧无法也不应覆盖。
把系统字体切回默认即可看到应用本来的字形。

---

## 4. 真实 VPN + 校园网认证验收（通过）

之前一直缺这块验收。为不依赖任何 VPN 账号，在 **debug 变体**里加了一个"黑洞 VPN"：

| 文件 | 说明 |
|---|---|
| `app/src/debug/java/com/oitnetportal/debug/BlackholeVpnService.kt` | 建立 tun 接口、接管 `0.0.0.0/0` 默认路由，读出来的包直接丢弃（黑洞） |
| `app/src/debug/java/com/oitnetportal/debug/DebugVpnControlReceiver.kt` | 由 adb 广播触发启停（VpnService 不能被外部直接启动） |
| `app/src/debug/AndroidManifest.xml` | 仅 debug 变体声明，release APK 不含任何调试入口 |

### 验收步骤与证据

```
# 1. 启动黑洞 VPN
$ adb shell am broadcast -a com.oitnetportal.debug.action.START_BLACKHOLE_VPN \
      -n com.oitnetportal/.debug.DebugVpnControlReceiver

VPN 网络数: 1
NetworkAgentInfo{ ni={[type: VPN[], state: CONNECTED/CONNECTED ...}
  lp{{InterfaceName: tun0 LinkAddresses: [10.77.0.2/32,]
      Routes: [0.0.0.0/0 -> 0.0.0.0 tun0,...] DnsAddresses: [10.77.0.1,]}}
  Uids: <{99900000-99999999, 0-99999}>          ← 覆盖 shell 与应用 uid

# 2. 对照：门户在默认路由上彻底不可达
$ adb shell ping -c 2 -W 3 172.16.11.54
2 packets transmitted, 0 received, 100% packet loss
（测试结束前复测一次，同样 100% 丢包）

# 3. App 后台巡检日志（每 60s 一轮）
17:04:10  OitPortalReconnect: 巡检结果=ONLINE
17:04:10  OitPortalService:   状态变化=MONITORING 网络在线，后台巡检中
17:05:11  OitPortalReconnect: 巡检结果=ONLINE
17:05:11  OitPortalService:   状态变化=MONITORING 网络在线，后台巡检中
```

**判定**：默认路由已被黑洞 VPN 完整接管、门户 100% 不可达的情况下，App 的后台探测仍然成功 →
`CampusNetworkBinder.withCampusNetwork()` 在探测/登录期间把进程绑回物理 Wi-Fi 的机制生效，
校园网认证流量不会被 VPN 带偏，且没有关闭或改动用户的 VPN。

> 为拿到这组证据，临时在控制器/服务里加了 logcat 打点，验收后已移除控制器内的打点，
> 保留服务侧的生命周期与状态变化打点（后台服务此前完全没有可观测出口）。

---

## 5. 顺带澄清的两个误判

| 现象 | 一度误判为 | 实际 |
|---|---|---|
| 共享状态文件 mtime 不再变化 | "后台巡检循环停了" | `SharedPreferences.apply()` 在**值未变化时不会写盘**，mtime 本就不动；日志证明 60s 循环一直正常 |
| AppOps `deny` 后 App 未检出通知被关 | "检测逻辑失效" | 本机 `checkOpNoThrow` 不反映 CLI 写入的 deny；真正生效的是 `areNotificationsEnabled()` |

---

## 6. 仍未覆盖

| 项 | 原因 |
|---|---|
| Android 13+ `POST_NOTIFICATIONS` 弹窗路径 | 验收设备为 Android 9，需 API 33+ 设备；代码路径与降级路径均已实现 |
| 协议 C4.5 多设备同账号互踢 | 需要第二台设备 |
| 协议 C4.6 注销接口具体 API 端点 | 成功页链到 `/eportal/logout.jsp?ms2g=...` 是 document 302，尚未拿到接口层端点 |

---

## 7. 验证基线

```
pytest                                   300 passed（无网络，含 6 例新增静态契约测试）
Android testDebugUnitTest                53 例（新增 5 例：P1 三例 + P2 两例）
Android assembleDebug / lintDebug        BUILD SUCCESSFUL
真机                                     vivo V1936A / Android 9，见上文各项
```
