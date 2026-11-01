# tasks.md — 全局任务追踪

> 最后更新: 2026-10-31
> 与 openspec/changes/ 的关系: 大改动走 `/opsx:propose` 生成 change 提案（openspec/changes/<name>/）；这里只记跨 change 的长期事项与日常待办。

## 进行中

### 路线B：Android 原生 App（`android/`，Debug APK 第二轮真机验收全部通过）

已接线：Compose 骨架、Chaquopy 桥接工厂、脱敏探测/单次登录桥接、手动登录（账密表单）、
首装无 protocol.json 的 SSO 表单解析（fail-closed）、本地会话关闭、网络安全配置最小例外。

第一轮真机验收（2026-10-21）发现两个缺陷并已修复：
- 首次登录误判失败 → 根因：AuthFlow 上线复测单次零容错；已加有界重试（3 次/1.5s，可注入 sleeper）
- Wi-Fi 恢复状态不刷新 → 根因：无网络监听；已加 registerDefaultNetworkCallback +
  前台恢复探测（有界重试 3 次/2s，只探测不自动登录，会话结束后静默跳过）

未接通（按 android/README.md 清单）：
- [x] 设置页（2026-10-21：网络恢复/前台自动刷新两个开关，AppSettingsStore 持久化，默认开启）
- [x] 日志查看（2026-10-21：会话内诊断事件卡，最近 50 条脱敏事件，界面展示最新 10 条）
- [ ] Capture（延后：本校协议已实测确认，移动端首装可无 protocol.json fail-closed 登录，非必需）
- [x] 后台自动重连（2026-10-24：前台 Service + 有界调度器接通，默认关闭、通知授权、通知停止、60s 巡检/30s 离线兜底/CAPTIVE 才登录/300s 最小重登/三次失败人工介入；264 pytest + 48 Android 单测 + assembleDebug + lintDebug 通过；两轮审查修复启停竞态与节流重置；**真机后台验收待 ADB 设备重连**）
- [x] **Debug APK 装机（2026-10-31）**：`com.oitnetportal` v0.1.0（versionCode=1 / targetSdk=35）已装到**红米 K50 Ultra（22081212C，HyperOS 2 / Android 15 / API 35）**，`adb install -r -t -g` 全部运行时权限已授予；**验收按用户决定暂缓**，未做登录/后台重连实测）
- [x] 凭据安全存储（2026-10-21：Android Keystore AES-256/GCM；记住密码用户明示、默认不勾选、不自动登录；登录成功才保存）
- [x] 学生网 ePortal gzip 乱码修复（2026-10-22：_response_text 魔数兜底，真机 logcat 定位）
- [x] 多账号管理（2026-10-21：多账号加密存储+别名备注+SSID 绑定自动预选+账号管理对话框；旧单凭据自动迁移；API 33+ 用 NEARBY_WIFI_DEVICES 免定位权限，≤32 退回精确定位+粗略定位成对声明）
- [x] 网络恢复回调（2026-10-21）
- [x] 首次编译 → APK 构建（2026-10-21，无 Wrapper，用本机 Gradle 8.9 + 命令行代理参数）
- [x] 第二轮真机验收全部通过（2026-10-21）：首次登录直接显示在线、Wi-Fi 断开置离线、恢复后自动刷新、重试登录、结束会话后网络事件不触发重登、重新登录

## 待办

- [ ] Android UI 细节优化（2026-10-31：已修 Material3 `surfaceContainer*` 角色缺失导致的卡片配色错配、去掉恒定禁用的死按钮；原"界面不和谐"主因（设备系统字体被改成"新蒂黑板报底字"）**已解决**——红米上该字体现为可切换模块（`chalk` / `optional` / `stock` 三档），**手机端 Termux 里敲 `oit-font` 即可交互切换**（已装机实测：菜单渲染 + 切换后 bind 2↔6、命中 1↔20 正确），不和谐时一条命令切回原厂；App 侧自身配色已固定。**工具链已入库 `github.com/kkkkikun/oit-font-switch`（private，含一键部署脚本 + 机制文档；仓库不含字体本体）**）
- [ ] 阅读页 `【】` 左右不对称（2026-11-01：**已定位到 App 侧，非系统字体问题**。STOCK 对照实验证明——系统字体 100% 原厂 MiSans 时同样不对称（`【`→正文 59px vs 正文→`】` 12px），黑板报体下是 71px vs 12px，差值恰等于两种字体空格步进之差（0.11em≈12px）；根因是**原文 `【` 后带了一个空格**，由正文字体渲染。字体侧已做能做的：把透镜括号轮廓**嵌入 Hanyi 本身**（`tools/embed_bracket_glyphs.py`），括号从此与正文同字体同字号（92px→97px）、贴内缘（71→61px / 12→2px），不再是「另一个字体的粗黑楔块」。**剩余偏心量属 App 侧**，交接文档 `docs/APP-HANDOFF-BRACKET.md`（字体仓库 `kkkkikun/oit-font-switch` 内）给了 CSS `text-spacing-trim: trim-both` 与文本清洗两种修法，待开发该 App 的 Agent 处理）
- [ ] **P5：「自动重登」端到端触发无法从 App 外部制造**（2026-11-01：门户侧 `InterFace.do?method=logout` 能注销该 IP+MAC 的匿名会话（探测 204→200），但 **App 的探测带自己的 session cookie，AC 认这个 cookie**，App 状态仍是「网络在线」。即自动重登的触发条件必须由 AC 主动作废 App 的 cookie 才出现。这条同时说明 App 会话具备「抗外部注销」能力。**非缺陷，是验收方法的边界**）
- [ ] 协议 C4.6 App 侧注销功能（**端点已确认** 2026-11-01：`http://172.16.11.54/eportal/InterFace.do?method=logout`，**不需要 `userIndex`**，仅凭 IP+MAC 即可让该客户端会话失效；App 侧尚未接入该能力）

## 阻塞项

- 无

## 已完成（近期）

- [x] **P3 修复：`onCapabilitiesChanged` 去抖，诊断事件不再刷爆**（2026-11-01：新增 `core/NetworkValidationGate.kt`——只放行「验证状态从未验证翻转为已验证」这一次翻转，`onLost` 复位；`MainActivity` 的 `onCapabilitiesChanged` 改走闸门。5 个新 JUnit；红米真机回归：静置 150 秒事件数从几十条降到 0 条）
- [x] **P4 修复：后台自动重登在日志/通知里可区分**（2026-11-01：`BackgroundReconnectController.handleCaptive()` 提交凭据前发 `检测到需要校园网认证，正在自动重登`；`handleLogin` 成功后发 `自动重登成功，网络在线` / `自动重登检查完成，校园网已在线`；普通巡检仍是 `网络在线，后台巡检中`。3 个新 JUnit）
- [x] **Android 13+ 通知权限路径验收（红米 K50 Ultra / HyperOS 2 / Android 15 / API 35）**（2026-11-01：`POST_NOTIFICATIONS` 弹窗**允许与拒绝两条分支**均通过；允许→常驻通知真实展示（`dumpsys notification` `vis=PRIVATE`、标题「OIT 校园网守护」、带「停止」动作）；拒绝→服务不启动（ServiceRecord 0）+ `enabled=false` + 提示「未授予通知权限，后台自动重连保持关闭」+ 诊断事件。同时复验 P1（force-stop 后重开自动恢复服务）、P2（通知被撤销→红色警告卡 +「打开通知设置」直达 `AppNotificationSettingsActivity`）、真实校园网登录（`OIT-XUESHENG`→CONNECTED）、断网→恢复巡检、「结束本次会话」。记录：`android/validation/2026-11-01-redmi-android15/report.md`）
- [x] **P1 修复：进程被杀后重开 App 恢复后台重连服务**（2026-10-31：`BackgroundServiceRuntime` 进程内存活标记 + `PortalViewModel.restoreBackgroundReconnectIfNeeded()`；3 个 JUnit；vivo V1936A 真机复现验证通过；**2026-11-01 在 Android 15 上二次复验通过**）
- [x] **P2：App 内检测系统通知被禁用并给出提示**（2026-10-31：`NotificationStatusProvider` 三层检查 + 设置页红色警告卡 +「打开通知设置」直达；vivo 真机 A/B 验证通过）
- [x] **真实 VPN + 校园网认证真机验收**（2026-10-31：debug 变体自建"黑洞 VPN"接管默认路由，门户 100% 不可达时 App 后台探测仍在线，验证 `CampusNetworkBinder` 生效）
- [x] **Android 用户部署文档**（`docs/android-setup.md`：安装、账号、后台重连、 vivo/OPPO 通知引导、进程被杀恢复、故障排查）
- [x] **文档基线校正**（CLAUDE.md 258→294 三处；`openspec/specs/learned/spec.md` 85→294）
- [x] **Android 后台自动重连真机验收**（任务 5.3，vivo V1936A / Android 9）：默认关闭、开启+通知、通知停止、断网监控恢复、结束会话通过；CAPTIVE 认证与三次失败未自然触发（JUnit 覆盖）；vivo 划卡杀进程不重启、默认禁通知已记录；发现 P1 重开不恢复服务缺陷 — 2026-10-27（`android/validation/2026-10-27-background-reconnect/`）
- [x] VPN 分流三端落地（`network.create_session` 物理网卡绑定 + Android `CampusNetworkBinder` + 托盘/配置开关；`f4584bc` + `6688662`）— 2026-10-27 提交（改动 2026-10-25 完成并验证）
- [x] `oit-portal configure` 交互配置命令（getpass 不回显，安全 TOML 写入；`f4584bc`）— 2026-10-27 提交
- [x] Linux 离线安装包（`build_linux.sh` wheelhouse tar.gz + install 脚本重构 + 文档；`88b88d8`）— 2026-10-27 提交
- [x] Jetson Nano 端到端部署完成，正常运行 — 2026-10-27（用户确认）
- [x] 工作区积压改动拆 4 个提交 + 文档同步（`dc3c3e6`）；openspec change `android-ui-refresh` 归档 — 2026-10-27
- [x] Android UI/UX 第三轮真机验收（覆盖安装、三页导航、设置持久化、实际登录、Wi-Fi 断开/恢复、前台刷新、本地会话；视觉暂接受）— 2026-10-24（ADB 自动验证 + 截图）
- [x] Android UI/UX 重设计（连接 / 设置 / 诊断三入口、Material 3 主题）— 2026-10-23；258 pytest + 31 Android 单测 + Debug 构建 + Lint 全通过
- [x] 移动端桥接 + 首装 SSO 适配器（`mobile_bridge.py` / `mobile_sso.py`）— 2026-10-20
- [x] Linux（systemd）支持（daemon SSID 扩展 + install/uninstall + service 模板 + docs）— 2026-10-16（`4ce38a1`）
- [x] OpenSpec 项目初始化（specs 五域 + CLAUDE.md 索引）— 2026-10-16（`dbb878d`）
- [x] 品牌：SVG logo（蓝色版定稿）+ 社交预览卡 + README 重排 + MIT LICENSE — 2026-10-16（`ffa69aa`）

---

## 维护说明

- **开始新会话**: 读本文件 + SNAPSHOT.md
- **完成事项**: 从「进行中」移到「已完成」，注明日期与 commit
- **大改动**: 不要直接写代码，先 `/opsx:propose` 走 OpenSpec 流程
- **周期清理**: 条目膨胀时调用 openspec-archivist 清理
