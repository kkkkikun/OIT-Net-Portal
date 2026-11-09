# tasks.md — 全局任务追踪

> 最后更新: 2026-11-09
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
- [x] 后台自动重连（2026-10-24：前台 Service + 有界调度器接通，默认关闭、通知授权、通知停止、60s 巡检/30s 离线兜底/CAPTIVE 才登录/300s 最小重登/三次失败人工介入；264 pytest + 48 Android 单测 + assembleDebug + lintDebug 通过；两轮审查修复启停竞态与节流重置；真机后台验收已于 2026-10-27 完成，见下「已完成」）
- [x] **Debug APK 装机（2026-10-31）**：`com.oitnetportal` v0.1.0（versionCode=1 / targetSdk=35）已装到**红米 K50 Ultra（22081212C，HyperOS 2 / Android 15 / API 35）**，`adb install -r -t -g` 全部运行时权限已授予；**验收按用户决定暂缓**，未做登录/后台重连实测）
- [x] 凭据安全存储（2026-10-21：Android Keystore AES-256/GCM；记住密码用户明示、默认不勾选、不自动登录；登录成功才保存）
- [x] 学生网 ePortal gzip 乱码修复（2026-10-22：_response_text 魔数兜底，真机 logcat 定位）
- [x] 多账号管理（2026-10-21：多账号加密存储+别名备注+SSID 绑定自动预选+账号管理对话框；旧单凭据自动迁移；API 33+ 用 NEARBY_WIFI_DEVICES 免定位权限，≤32 退回精确定位+粗略定位成对声明）
- [x] 网络恢复回调（2026-10-21）
- [x] 首次编译 → APK 构建（2026-10-21，无 Wrapper，用本机 Gradle 8.9 + 命令行代理参数）
- [x] 第二轮真机验收全部通过（2026-10-21）：首次登录直接显示在线、Wi-Fi 断开置离线、恢复后自动刷新、重试登录、结束会话后网络事件不触发重登、重新登录

## 待办

**无待实现项。**

- [x] 协议 C4.6 App 侧注销功能 —— **2026-11-01 用户确认暂不做**（当前没有需求）。端点已确认可用备查：`http://172.16.11.54/eportal/InterFace.do?method=logout`，**不需要 `userIndex`**，仅凭 IP+MAC 即可让该客户端会话失效。App 侧现「结束本次会话」只关本地 Python 会话，界面已明确说明「不会向校园网服务器发送退出请求」；真要接这个能力时按此端点实现即可

## 待决策（需要用户操作，Agent 无法代做）

- [ ] **Windows 端「真实静默登录」验收** —— 需要校园网密码。托盘已装好并运行中（`D:\oit-portal-venv312`，账号已从 `config.toml` 预填），在设置窗口里输入密码 → 点「保存并连接」→ 托盘图标应先变「检测中」再变「在线」。密码不经过 Agent，全程在用户本机输入。验收清单第 1/2/3 项都依赖这一步。**2026-11-09 更新**：用户计划另找一台电脑实测，拿到结果后回填此项


## 阻塞项

- [ ] **阅读页 `【】` 左右不对称 —— 等待用户转交给开发「超级看书」的 Agent**（2026-11-01：**已定位到 App 侧，非系统字体问题**。STOCK 对照实验证明——系统字体 100% 原厂 MiSans 时同样不对称（`【`→正文 59px vs 正文→`】` 12px），黑板报体下是 71px vs 12px，差值恰等于两种字体空格步进之差（0.11em≈12px）；根因是**原文 `【` 后带了一个空格**，由正文字体渲染。字体侧已做能做的：把透镜括号轮廓**嵌入 Hanyi 本身**（`tools/embed_bracket_glyphs.py`），括号从此与正文同字体同字号（92px→97px）、贴内缘（71→61px / 12→2px），不再是「另一个字体的粗黑楔块」。**剩余偏心量属 App 侧**，交接文档 `docs/APP-HANDOFF-BRACKET.md`（字体仓库 `kkkkikun/oit-font-switch` 内）给了 CSS `text-spacing-trim: trim-both` 与文本清洗两种修法）

## 已知边界（不是待办，不用做）

- **「自动重登」端到端触发无法从 App 外部制造**（2026-11-01）：门户侧 `InterFace.do?method=logout` 能注销该 IP+MAC 的**匿名**会话（探测 204→200），但 **App 的探测带自己的 session cookie，AC 认这个 cookie**，App 状态仍是「网络在线」。自动重登的触发条件必须由 **AC 主动作废 App 的 cookie** 才出现，外部造不出来。**这是验收方法的边界，不是缺陷** —— 反过来还说明 App 会话具备「抗外部注销」能力。要验这条，只能等校园网会话自然过期时观察
- **长期稳定性（>24h 保活）未做长跑**：本次只在单次会话内验证
- **HyperOS 厂商省电策略下的存活率未测**：只验证过 `START_STICKY` 被系统重启一次
- **P3/P4 的新 APK 只在红米（Android 15）复验**：vivo（Android 9）上仍是旧版本，下次接 vivo 时顺带回归

## 已完成（近期）

- [x] **v1.0.1 发版（2026-11-09，tag → `7481acd`）**：OpenFeedback 反馈通道 + CI 地址注入修复随版本发布，Release 已挂 `OIT-Portal-debug.apk`（versionCode 3，反馈地址为域名版）与 `OIT-Portal-windows.exe`。发版过程：CI 三 job 全绿（run 42624904324，android job 验证了从国际出口拉取域名版 Maven 仓库成功）→ 推 tag → Release workflow 三 job 全绿（run 42626497224）。**发版前补的两个缺口**：①CI android job 此前会整行覆写 `local.properties` 丢掉反馈地址、且 SDK Maven 地址会退占位符 → 改为从仓库变量 `OIT_FEEDBACK_ENDPOINT` / `OIT_OPENFEEDBACK_MAVEN_URL` 注入 + fail-fast 校验 + 契约测试（pytest 435→436）；②OpenFeedback 服务从裸 IP 切换到域名（IP 已停 HTTPS），两个仓库变量与本机 `local.properties` 已同步为域名值。**大陆侧可达性已真机验证通过**（2026-11-09，手机不开代理：根路径返回服务 JSON、`/admin/` 后台可打开）——开发机 WSL 出口与代理出口对域名的 TLS 重置属本机网络环境特例，不影响同学端
- [x] **App 内嵌反馈通道全链路完成并归档（2026-11-04 → 2026-11-09）**：演进路径 = 自托管收集端（`e5d7436`，CLI `feedback serve|list|export` 保留至今）→ 飞书直发（2026-11-04，解决「作者要常驻端口服务」）→ **OpenFeedback 统一服务**（`9779839`，2026-11-05 迁移，解决「无统一后台 / 无截图 / 断网即丢 / webhook 即凭据」四问题）。OpenFeedback 版：断网落本机队列 + WorkManager 自动补发、服务端按 `submissionId` 去重、APK 零凭据（只有公开 `appId` 与地址）；真机闭环验收通过（在线提交 / 断网排队 / 补发无重复，红米 K50 Ultra / Android 15）；修掉「提交过一次弹窗打不开」bug（`18e42d1`）。**飞书时代遗留的「分发前必须开凭证校验」警告已随迁移销项**——APK 已不含飞书 webhook、token 已删且无代码读取，该前提不复存在（若日后回滚到 `ChaquopyFeedbackBridge` 飞书直发，需重新执行该警告）。change 已归档：`openspec/changes/archive/2026-11-09-switch-feedback-to-openfeedback/`（归档时补回被 delta 整体替换误删的两个仍有效 scenario：业务码失败判定 / 自托管收集端投递）

- [x] **v1.0.0 发布 + GitHub Actions 落地（2026-11-01）**：`android-app` 纯快进合并进 `main`（两分支现已同步）；版本号 1.0.0（`versionCode` 2）；新增 `CHANGELOG.md` + README 徽章 + Gradle Wrapper 入库；`.github/workflows/ci.yml` 与 `release.yml`。**首轮 CI 全红 → 修 5 个真问题 → 第三轮三 job 全绿（run 41307746362）**：①pytest ≥9.2 往 `propagate=False` 的 logger 挂 `LogCaptureHandler` → `setup_logging` 的 `if logger.handlers` 误判 → 日志文件从未创建（本地 pytest 9.0.3 无此行为，本地绿 CI 红）→ 改用自有 handler 标记（`oit_portal/log.py`）；②`build_windows.ps1` 只装第三方依赖 → 托盘 import requests 失败 → 更正为「先停运行中的托盘再正常装 `.[tray]`」；③`android-actions/setup-android` 去装下架的 `tools` 包 → 改用 runner 预装 SDK + `yes | sdkmanager --licenses`；④Chaquopy 要求构建机 Python 与 App 内嵌版本一致（3.10）→ Android job 补装 Python 3.10；⑤发版说明 awk 正则 `"^## \["` 匹配不到任何行 → 改用 `index()`。新增 `tests/test_ci_workflow_contract.py`（6 例）守住这四条约束。pytest 324→**332**
- [x] **发版后的三处收尾（2026-11-01）**：①`oit_portal/__init__.py` 的 `__version__` 还写着 0.1.0（pyproject 已是 1.0.0）→ `oit-portal --version` 对外报假版本号 → 改为以 `importlib.metadata` 包元数据为准 + `tests/test_version.py`（3 例）；②`install_windows_tray.ps1` 与 `build_windows.ps1` 同一个坑：托盘在跑时重装撞 WinError 5 → 补「先停托盘再装」；③校内网 pypi 读超时导致 `pip install "[tray]"` 失败 → 加 `--no-build-isolation` 离线兜底。真机复验：重跑安装脚本 → 常规失败 → 兜底成功 → 托盘重新拉起并存活，`oit-portal --version` = 1.0.0，自启项完好。pytest 332→**337**

- [x] **Windows 端 PC 侧全链路实测与 4 个真缺陷修复**（2026-11-01，在用户自己的中文 Windows / PowerShell 5.1.26100.9711 上实测）：①4 个 `.ps1` 是 UTF-8 无 BOM + 含中文 → PS 5.1 按 ANSI 解码吞掉引号 → 语法错误，**文档推荐的托盘安装/卸载方式在中文 Windows 上完全不可用** → 全部加 UTF-8 BOM（`tests/test_windows_script_encoding.py` 守住）；②`stop` 在无 daemon 时打 ERROR 到 stderr → PS 5.1 在 `$ErrorActionPreference="Stop"` 下把 stderr 当终止错误 → 安装脚本第 2 步被打断、**托盘根本没启动** → `stop` 改幂等返回 0 + INFO（`tests/test_daemon_stop.py`）；③缺 tkinter 只提示 `pip install .[tray]`（tkinter 不是 pip 包）且托盘崩了仍照报「完成！」→ 区分 tkinter/其他依赖 + 安装脚本改 4 步带存活校验（`tests/test_windows_tray_startup.py`）；④`build_windows.ps1` 重装本项目撞被占用的入口 exe（WinError 5）、`uninstall_windows.ps1` 用 PATH 上的 `python`/`oit-portal`（venv 场景下不存在）却照报「卸载完成」→ 改为只装第三方依赖 + `-Python` 参数 + 卸载核实（`tests/test_windows_build_uninstall.py`）。实测通过：4 脚本 PS 解析全 OK、托盘安装 4 步全绿且进程存活、独立 exe 自包含能弹窗、卸载后包/自启项/入口 exe/`~` 临时目录全清干净、`-Purge` 用假 APPDATA 验证生效。pytest 309→324
- [x] **公开历史里残留的未遮盖原图 —— 已于 2026-11-01 重写历史清除**（原为待决策）：
    - **实际只有 1 个文件**进了公开历史：`android/validation/2026-10-27-background-reconnect/00_screen_state.png`
      （引入提交 `5c4e1c2`）。里面是**真实姓名 + 工号**（教师账号），比单纯学号更敏感。
    - 另两个目录（`2026-10-31-android-followup` / `2026-11-01-redmi-android15`）的引入提交
      （`ce1b042` / `4dcbdf0`）是在**推送前就已遮盖**，历史里是干净版本，本就没进过公开历史。
    - 处置：`git filter-repo --blob-callback` 把旧 blob `97d8f49` 替换成遮盖版 `6085539c`
      并强推 `android-app`（`40a9d72 → e484110`）。**所有提交的 SHA 都变了**，
      旧分支尖端已不在任何 ref 上。
    - 核验：旧 blob 已从本地对象库消失；**全新克隆里该文件在所有历史提交中都只有遮盖版**，
      旧 blob 不在克隆的对象库里 ✅。
    - **残留边界**：GitHub 自己仍会在 GC 前短暂保留不可达对象（`gh api .../git/blobs/97d8f49`
      目前仍返回 200），随后由平台自动清除；必要时可向 GitHub Support 申请加速。
- [x] **验收截图的学号遮盖**（2026-11-01：本仓库 `kkkkikun/OIT-Net-Portal` 是**公开仓库**，截图里原本直接可见学号）：按用户决定用新提交遮盖 8 张图 / 17 处（整串 13 处用模板匹配定位，最近任务卡片里被遮挡的片段 4 处手工补），标签与界面结构完整保留；复检整串与 4 位前缀在 25 张图多尺度下均 0 命中；补录 5 张此前未入库的证据（HyperOS 最近任务界面 + 阅读页【异能】实拍，`25` 更名为 `25-bracket-reading-page.png`）
- [x] **Android UI 细节优化**（2026-10-31 修完，2026-11-01 销项：Material3 `surfaceContainer*` 角色缺失导致的卡片配色错配、恒定禁用的死按钮；原「界面不和谐」主因——设备系统字体被改成「新蒂黑板报底字」——**已解决**：红米上该字体现为可切换模块（`chalk` / `optional` / `stock` 三档），**手机端 Termux 里敲 `oit-font` 即可交互切换**（已装机实测：菜单渲染 + 切换后 bind 2↔6、命中 1↔20 正确），不和谐时一条命令切回原厂；App 侧自身配色已固定。**工具链已入库 `github.com/kkkkikun/oit-font-switch`（private，含一键部署脚本 + 机制文档；仓库不含字体本体）**）

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
