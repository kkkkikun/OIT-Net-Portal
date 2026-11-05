# 更新日志

本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-11-01

首个正式版本。三端（Windows / Android Termux / Linux）+ 路线B 原生 App 齐备。

### Python 核心

- **协议自配置**：`oit-portal capture` 抓包向导自动发现登录协议，写入用户配置目录 `protocol.json`，
  运行时合并进 `CAPTURED` 常量块 —— 登录协议不写死在代码里，换校/协议变动不必改源码。
- **三态探测**：多探测点双确认的 `online` / `captive` / `offline` 判定。
- **VPN 分流**：VPN 开启时认证不中断 —— Windows/Linux 认证 socket 绑定物理网卡
  （`SourceAddressAdapter`），Android 端 `bindProcessToNetwork` 绑定底层 Wi-Fi；
  不关闭 VPN、不改变其他流量、不需要管理员权限。
- **保活与退避**：守护循环带指数退避、Wi-Fi SSID 触发、三次失败转人工介入。
- **`oit-portal configure`**：交互式设置账号密码（不回显、安全转义 TOML、回车保留原值）。
- **`oit-portal login-info`**：验证码 / 会话失效时的人工登录引导。
- **凭据安全**：密码只落 `credentials.toml`（0600）或 `OIT_PORTAL_PASSWORD`；
  日志只经 `log.fingerprint()` 脱敏；SSO cookie 落盘免密复用。

### Windows 托盘 App

- 托盘图标菜单：状态与详情、立即重连、暂停/启动自动登录、账号设置、开机自启开关、打开日志文件夹、退出。
- 账号设置窗口支持 **VPN 开启时仍使用校园网直连** 与手工指定物理网卡 IPv4。
- 一键安装脚本 `scripts\install_windows_tray.ps1`：运行环境预检 → 装依赖 → 写当前用户自启项 → 启动并**验证进程存活**；重装时会先停掉运行中的托盘（否则入口 exe 被锁，pip 报 WinError 5），校内网拉不到 pypi 时自动改用 `--no-build-isolation` 离线安装。
- 独立 exe 构建：`scripts\build_windows.ps1`（PyInstaller，自包含 Python，可分发给未装 Python 的机器）。
- 卸载脚本 `scripts\uninstall_windows.ps1`：停止托盘/daemon/旧计划任务、移除自启项、卸载包并**核实是否真清干净**，
  `-Purge` 一并删除配置/凭据/日志。

### Android Termux

- `scripts/install_termux.sh` 一键安装 + Termux:Boot 自启 + 电池优化豁免。
- 移动端桥接做**脱敏**探测/单次登录；首装无 `protocol.json` 时走 fail-closed 的 SSO 表单适配器。

### Linux（systemd）

- `scripts/build_linux.sh` 产出多架构**离线安装包**（wheelhouse tar.gz + SHA256 校验），
  `install.sh` 在无外网环境下也能装。
- systemd unit 支持 `Restart=on-failure` 与退避，避免守护退出码 1 造成重启风暴。

### Android 原生 App（路线B，`android/`）

Kotlin + Jetpack Compose + Chaquopy，复用同一份 Python 认证核心。

- **连接 / 设置 / 诊断** 三入口界面，Material 3 主题。
- **手动登录**（账密表单）、**多账号管理**（别名备注 + SSID 绑定预选）、
  **Keystore AES-256/GCM** 凭据存储（记住密码需用户明示、默认不勾选、不自动登录）。
- **后台自动重连**：前台 Service + 有界调度器，通知可见性检测与系统设置直达。
- **脱敏诊断页**：最近 50 条事件，只展示最新 10 条。
- **VPN 绑定**：`CampusNetworkBinder` 在探测/登录期间绑定物理 Wi-Fi。
- 四轮真机验收：vivo V1936A / Android 9、红米 K50 Ultra / HyperOS 2 / Android 15，
  覆盖安装、真实校园网登录、断网恢复、进程被杀后自愈、Android 13+ 通知权限允许与拒绝两条分支。
- 自带 Gradle Wrapper（8.9），`./gradlew :app:assembleDebug` 即可构建。

### 工程与发布

- **CI**（`.github/workflows/ci.yml`）：pytest（无网络）+ Android 单测/lint/构建 + Windows 独立 exe 构建。
- **发版工作流**（`.github/workflows/release.yml`）：推 `v*` 标签自动构建 APK 与 exe 并挂到 GitHub Release。
- **.ps1 一律 UTF-8 with BOM** —— PowerShell 5.1 只对带 BOM 的文件按 UTF-8 解码，
  否则中文 Windows 上会因引号被吞而语法错误。
- pytest **338 例**全部无网络；Android JUnit **61 例**。
- **版本号一致**：`oit-portal --version` 取自包元数据，与 `pyproject.toml` 同源，不会再对外报旧的 0.1.0。

### 已知边界

- 「自动重登」的端到端触发条件必须由 AC 主动作废本机会话 cookie 才出现，**无法从 App 外部制造**
  （外部注销只能注销匿名会话）——属验收方法边界，非缺陷。
- 门户注销端点已确认可用（`InterFace.do?method=logout`，不需要 `userIndex`），
  但 App 侧**未接入**该能力，现「结束本次会话」只关本地会话。

## [未发布]

### 新增

- **App 内嵌快速反馈通道**：设置页底部新增「意见反馈」卡片，点开是 **App 内原生 Compose 表单**
  （类型 / 内容 / 是否附带脱敏诊断摘要）—— 不跳浏览器、不用问卷链接、同学不需要注册任何账号。
  - 收集端自托管：`oit-portal feedback serve` 起极简 HTTP 服务，反馈按 JSONL 落盘到本机；
    默认只监听回环，`--host 0.0.0.0` 才对外（收集端无鉴权，只适合可信校园网内网）。
  - 集中处理：`oit-portal feedback list` 列出、`oit-portal feedback export` 导出 Markdown 清单
    （正文里的 Markdown 结构字符已转义，不会把清单排版冲掉）。
  - 可选同步飞书：配 `--feishu-webhook` 后每条反馈额外发一份到飞书
    （群机器人发文本、多维表格发扁平 JSON）；**落盘优先、转发其次**，飞书抖动不会丢反馈。
  - 安全边界：反馈载荷只有同学填的正文与脱敏摘要；含 URL、凭据线索或账号字样的诊断行**整行丢弃**；
    提交走 `network.create_session()`（trust_env=False）；APK 内不含任何第三方写入凭据。
- **反馈通道改为飞书直发**（2026-11-04）：作者不用再在自己电脑上常驻一个端口服务 ——
  提交目标从「自托管收集端」改为**飞书 webhook**（云端常驻）。
  - 按地址形态自动分流请求体：含 `/open-apis/bot/` 的走群机器人（`msg_type` + `content.text`），
    其它飞书地址走**多维表格扁平 JSON**（键名即列名）。
  - 载荷新增 `category_label`（中文分类）与 `submitted_at`，多维表格可直接建「分类」单选列与「时间」列。
  - **支持飞书凭证校验**：群机器人签名校验（`timestamp` + `sign`，HMAC-SHA256 后 Base64）、
    多维表格 Bearer（`Authorization` 头）。
  - **业务码判定**：飞书即使 HTTP 200 也可能返回 `code != 0`（关键词不匹配、IP 不在白名单），
    只看状态码会把失败当成功 → 提交层现在检查业务码，失败如实上报。
  - 自托管收集端**保留**，作为「先审后收」或「完全离线」时的可选项。
  - **通道地址与凭证构建期注入**：`android/local.properties`（已 gitignore）里的
    `oit.feedback.endpoint` / `oit.feedback.secret` 由 Gradle 注入 APK；    本仓库是公开仓库，真实 webhook 地址与密钥不进版本控制。

### 变更

- **反馈通道迁移到 OpenFeedback**（2026-11-05，change `2026-11-05-switch-feedback-to-openfeedback`）：
  提交目标从**飞书 webhook** 改为自托管的 **OpenFeedback** 统一反馈服务
  （独立、轻量、可自托管，公开仓库 `kkkkikun/OpenFeedback`；同一套服务端 + 同一个后台，按 `appId` 区分应用）。
  飞书直发有四个绕不开的问题：数据只进表格没有统一后台、没有截图、断网即丢、webhook 地址本身就是写入凭据。
  - **改动面刻意压到最小**：保留本 App 自己的 Compose 表单与 `FeedbackBridge` 边界，
    只把桥接实现从「Chaquopy → Python → requests → 飞书」换成「SDK core → HttpURLConnection → OpenFeedback」，
    表单 UI 与交互不变。回滚是单点替换（换回 `ChaquopyFeedbackBridge` 即可恢复飞书直发）。
  - **断网不丢、不重复**：离线时反馈存本机队列，联网后由 WorkManager 自动补发；
    每条反馈带客户端生成的 `submissionId`，服务端按它去重，补发**不会**产生重复记录。
  - **APK 内不再有任何服务端凭据**：只剩公开的 `appId` 与服务地址；
    `oit.feedback.secret`（旧飞书 webhook token）不再被任何代码读取。
  - **服务端再校验一遍**：限流（每 `appId` + IP 每小时 10 条）、字段合法性、
    附件魔数与数量/大小限制都不信任客户端；反馈内容与截图只有登录后的管理员能看到。
  - 新增依赖 `com.kkkkikun.openfeedback:openfeedback-core:0.1.0`，
    用框架自带的 `HttpURLConnection`，**不给宿主引入 OkHttp / Retrofit**，依赖树不变；
    SDK 仓库地址经 Gradle 属性 `oit.openfeedback.mavenUrl` 注入，可指向本地 `file://` 目录做离线构建。
  - 反馈类型从三类扩到四类（问题 / 功能建议 / 体验问题 / 其他），
    服务端兼容旧分类 `issue` / `suggestion` / `ux` / `problem`，**回退安全**。
  - Python 侧 `oit_portal/feedback.py` / `mobile_feedback.py` **保留但 Android 不再调用**
    （CLI 自托管收集端 `oit-portal feedback serve|list|export` 仍可用）。
  - Android 单测 73 → **79**（新增 `FeedbackCategoryMappingTest` 4 例；真机验收后补 `openFeedbackForm` 回归 2 例）。
  - Python 契约测试同步更新：`tests/test_android_feedback_contract.py` 原来断言
    「设置里要存通道凭证」「构建期要注入 `oit.feedback.secret`」，迁移后这两条**反过来**
    成了要禁止的行为 —— 契约测试现在断言**设置里不得出现任何 secret/token**、
    **构建期不得再注入 secret**、桥接实现里不得出现密钥字段。
    pytest 429 → **435**。
  - `docs/app-feedback.md` 已按新通道重写。

### 修复

- **提交过一次反馈后，弹窗再也打不开**（真机验收时发现）。
  反馈表单用 `LaunchedEffect(state.feedbackSubmitted)` 在提交成功后自动收起，
  而 `feedbackSubmitted` 提交后从不复位 —— 于是第二次打开表单时，
  这个 effect 拿着上一次的旧值立刻把表单关掉，表现为「点『写一条反馈』没反应」。
  修法：新增 `PortalViewModel.openFeedbackForm()`，在打开表单前把
  `feedbackSubmitted` 与 `feedbackError` 复位；补 2 条回归测试
  （`openFeedbackForm_clearsThePreviousSubmittedFlag` /
  `openFeedbackForm_allowsASecondSubmission`）。
  Android 单测 77 → **79**。

### 验收

- **真机闭环验收通过**（2026-11-05，红米 K50 Ultra / Android 15 / API 35，
  服务端为自托管的 OpenFeedback，公网 HTTPS）：
  - 在线提交 → App 显示「反馈已收到」→ 后台出现记录，
    设备信息 `Xiaomi 22081212C / android 15 / api 35 / zh-CN`，
    诊断摘要只含脱敏状态，无账号与完整 URL；
  - 断网（飞行模式）提交 → App 仍显示「反馈已收到」→ 后台**查不到**，
    反馈落盘在本机队列 `no_backup/openfeedback/queue/<uuid>/submission.json`；
  - 恢复网络 → WorkManager（带 `CONNECTIVITY` 约束）**自动补发** →
    后台出现记录，`submission_id` 与本机队列里的完全一致；
  - 强制重跑 worker 3 次 → 服务端条数不变，**无重复记录**。


见 [tasks.md](.claude/docs/tasks.md) 与 [SNAPSHOT.md](.claude/docs/SNAPSHOT.md)。
