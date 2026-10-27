# tasks.md — 全局任务追踪

> 最后更新: 2026-10-27
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
- [x] 凭据安全存储（2026-10-21：Android Keystore AES-256/GCM；记住密码用户明示、默认不勾选、不自动登录；登录成功才保存）
- [x] 学生网 ePortal gzip 乱码修复（2026-10-22：_response_text 魔数兜底，真机 logcat 定位）
- [x] 多账号管理（2026-10-21：多账号加密存储+别名备注+SSID 绑定自动预选+账号管理对话框；旧单凭据自动迁移；API 33+ 用 NEARBY_WIFI_DEVICES 免定位权限，≤32 退回精确定位+粗略定位成对声明）
- [x] 网络恢复回调（2026-10-21）
- [x] 首次编译 → APK 构建（2026-10-21，无 Wrapper，用本机 Gradle 8.9 + 命令行代理参数）
- [x] 第二轮真机验收全部通过（2026-10-21）：首次登录直接显示在线、Wi-Fi 断开置离线、恢复后自动刷新、重试登录、结束会话后网络事件不触发重登、重新登录

## 待办

- [ ] **P1 缺陷修复**：进程被厂商杀死后重开 App 不恢复后台重连服务，且状态文本陈旧（enabled=true 但服务未运行，UI 显示"网络在线，后台巡检中"）——建议 Activity/ViewModel 初始化时按 enabled 状态恢复服务或纠正状态；2026-10-27 真机验收发现
- [ ] Android UI 细节优化（用户反馈部分界面不够和谐，已确认暂缓）
- [ ] Android 13+ 通知权限路径验证（待可用设备）

## 阻塞项

- 无

## 已完成（近期）

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
