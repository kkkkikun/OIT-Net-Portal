# SNAPSHOT.md — 项目状态快照

> 最后更新: 2026-11-09 | **v1.0.1 已发布**（tag → `7481acd`，Release 挂 APK + exe；发版 CI 三 job 全绿 run 42624904324 / Release run 42626497224）| 验证: pytest 436 passed (无网络) + Android testDebugUnitTest **79 例全绿**（CI 上通过，含 `FeedbackCategoryMappingTest` 4 例分类映射与 `openFeedbackForm` 回归 2 例）+ **反馈通道已迁移到 OpenFeedback**（change 已归档 2026-11-09，openspec 全量校验 8/8 绿）+ **真机闭环验收通过**（红米 K50 Ultra / Android 15：在线提交→后台可见；断网暂存→恢复自动补发→`submission_id` 一致→强制重跑无重复）+ vivo V1936A 真机复现验收（2026-10-31）+ 红米 K50 Ultra / Android 15 通知权限路径验收（2026-11-01）+ Windows 端 PC 侧全链路实测（2026-11-01）

## 项目概览

**oit-portal** — 鄂尔多斯应用技术学院校园网静默自动登录 + 保活工具。Python 3.9+，单代码库多端共用（Windows 托盘/计划任务 / Android Termux / Linux systemd），另有**路线B Android 原生 App**（`android/`，Kotlin + Compose + Chaquopy 复用 Python 核心；三轮真机验收 + 后台自动重连真机验收均通过，2026-10-27）。

核心机制：登录协议不写死，由 `oit-portal capture` 抓包向导自动发现，写入用户配置目录 `protocol.json`，运行时合并进 `sso.py` / `eportal.py` 顶部的 `CAPTURED` 常量块（占位标签 `<CAPTURE:Cx.y>` 对应 `docs/protocol-notes.md` 编号）。

**VPN 分流（2026-10-25 落地）**：VPN 开启时认证不中断——Windows/Linux 认证 socket 经 `network.create_session()` 可绑定物理网卡（`SourceAddressAdapter`），Android 端 `CampusNetworkBinder` 在 probe/loginOnce 期间 `bindProcessToNetwork` 绑定底层 Wi-Fi；不关闭 VPN、不改变其他流量。

**Jetson Nano 已完成端到端部署并正常运行**（2026-10-27 用户确认）。

## 技术栈

| 项 | 值 |
|---|---|
| 语言 | Python 3.9+ |
| 依赖 | requests, pycryptodome (可选 AES), tomli (<3.11) |
| 测试 | pytest，436 用例全部无网络（FakeSession + fixture 状态机 + Android/Windows 托盘/Windows 脚本/Linux 打包/CI workflow/反馈通道 静态契约测试）；Android 另有 79 例 JUnit 单测 |
| 打包 | pyproject.toml + setuptools，console_scripts: oit-portal；Linux 离线包 `scripts/build_linux.sh`（wheelhouse tar.gz + SHA256）；Windows PyInstaller exe |
| 格式化 | 无强制工具，遵循现有代码风格 |

## Git 状态

- 分支: `main`（= `android-app`，两条分支同步；`legacy-shell-cli` 停在 `ffa69aa`）
- 远端: `kkkkikun/OIT-Net-Portal`（**公开仓库**）；标签 `v1.0.0` → `b07a9f8`（annotated）
- 最近提交:
  - `b07a9f8` fix(ci): Android job 装 Python 3.10（Chaquopy 要求构建机与 App 同版本）+ CI workflow 契约测试
  - `fc4058c` ci: 修首轮 CI 的三个真问题 + 发版 workflow 的两个隐患
  - `b304aab` fix(build): 构建脚本先停托盘再装项目依赖（更正此前"不重装"的错误解法）
  - `c63f72b` fix(log): setup_logging 幂等判断改用「自有 handler」标记
  - `a06b8a2` chore(release): 版本号对齐 v1.0.0 + 补 CHANGELOG
  - `442c9b9` ci: 加 GitHub Actions（CI + 发版）+ 补 Gradle wrapper + 修正过时文档

## 目录结构

```
oit_portal/
├── cli.py                  # CLI 入口: status/once/daemon/stop/login-info/capture/configure/feedback
├── capture.py              # 抓包向导（_HEURISTIC_ENDPOINTS 等 fallback 常量）
├── discover.py             # 入口链路发现（302 / meta refresh / JS 三跳）
├── probe.py                # 三态探测 online/captive/offline，多探测点双确认
├── daemon.py               # 常驻守护（探活 + 保活 + 退避 + WiFi SSID 触发）
├── keepalive.py            # 心跳
├── htmlutil.py             # HTML/内联 JS 解析（find_aes / form_action / analyze_form）
├── protocol_overrides.py   # protocol.json 合并进 CAPTURED（仅替换已有键）
├── network.py              # 统一认证 Session：trust_env=False + 可选物理网卡绑定（VPN 分流）
├── mobile_bridge.py        # 路线B 移动端桥接（脱敏探测/单次登录，无 capture/daemon）
├── feedback.py             # App 反馈通道：载荷构造/JSONL 存储/HTTP 收集端/飞书可选转发
├── mobile_feedback.py      # 路线B 反馈桥接（提交一条反馈，无凭据、无 capture/daemon）
├── mobile_sso.py           # 移动端首装 SSO 适配器（不读 protocol.json，fail-closed 加密）
├── tray.py                 # Windows 托盘 App（账号设置含 VPN 直连开关、状态菜单、后台线程）
├── config.py / log.py / paths.py
├── auth/
│   ├── flow.py             # AuthFlow.ensure_online 编排
│   ├── sso.py              # SSO 账密登录（CAPTURED 块在顶部）
│   ├── eportal.py          # ePortal login_sso.jsp 上线检查（CAPTURED 块同）
│   ├── models.py           # AuthError / PortalChallenge / OnlineResult
│   └── session_store.py    # SSO cookie 落盘免密复用 (session.json)
└── platform/
    ├── windows.py          # 计划任务细节
    └── termux.py           # Termux 启动/守护 + 电池豁免
android/                    # 路线B 原生 App（Kotlin + Compose + Chaquopy）
└── .../core/CampusNetworkBinder.kt  # 认证期间 bindProcessToNetwork 绑定物理 Wi-Fi
tests/                      # 测试文件（含 test_mobile_* / test_android_* / test_linux_* 契约测试）
scripts/                    # install_windows.ps1 / build_windows.ps1 / install_windows_tray.ps1
                            # install_termux.sh / build_linux.sh / install_linux.sh
                            # uninstall_linux.sh / oit-portal.service.template
docs/                       # protocol-notes.md / capture-guide.md / 三端部署文档
openspec/                   # OpenSpec 规范体系（specs/ + changes/）
```

## 关键文件速查

| 场景 | 文件 |
|---|---|
| 改协议字段 | `oit_portal/auth/sso.py` + `eportal.py` 顶部 CAPTURED 块 + `docs/protocol-notes.md` |
| 改抓包向导 | `oit_portal/capture.py` + `tests/test_capture_wizard.py` + `docs/capture-guide.md` |
| 改入口跳转 | `oit_portal/discover.py` + `tests/test_discover.py` |
| 改路径/守护 | `oit_portal/paths.py` + `platform/` + `docs/{windows,termux}-setup.md` |
| 改表单解析 | `oit_portal/htmlutil.py` + `tests/test_htmlutil.py` |
| 改 Session/VPN 分流 | `oit_portal/network.py` + `tests/test_network.py`（新 Session 禁止直接 `requests.Session()`） |
| 改 Android 绑定 | `android/.../CampusNetworkBinder.kt` + `tests/test_android_vpn_bypass_contract.py` |
| 改 Linux 打包 | `scripts/build_linux.sh` + `install_linux.sh` + `tests/test_linux_packaging.py` |

## 当前工作

- **阶段**: 三端 + 路线B Android 功能齐备；VPN 分流（三端）、`configure` 交互命令、Linux 离线安装包均已落地并提交；Jetson Nano 已端到端部署正常运行
- **已完成**: Android 后台自动重连已于 2026-10-27 完成 Android 9 真机验收（vivo V1936A）：默认关闭/开启+通知/通知停止/断网监控恢复/结束会话全部通过；openspec change `android-background-auto-reconnect` 17/17 任务完成
- **已完成（2026-10-31）**: P1 修复（进程被杀后重开 App 自动恢复后台服务并纠正陈旧状态）、P2 通知可见性检测与设置页警告卡、Material3 `surfaceContainer*` 配色错配修复、真实 VPN 验收（debug 变体自建黑洞 VPN）、`docs/android-setup.md` 用户部署文档
- **新设备就位（2026-10-31）**: Debug APK 已装到**红米 K50 Ultra（22081212C，HyperOS 2 / Android 15 / API 35）**（`com.oitnetportal` v0.1.0，运行时权限已全授予）。同机另完成非项目范围的系统字体改造（汉仪新蒂黑板报体底字全局生效 + 度量修正 + 三档切换模块，见 `/mnt/d/oit-fonts/`）
- **Android 13+ 通知权限路径已验收（2026-11-01）**: 红米 K50 Ultra / Android 15 真机跑通 `POST_NOTIFICATIONS` 弹窗**允许与拒绝两条分支**（允许→常驻通知真实展示 `vis=PRIVATE`；拒绝→服务不启动 + `enabled=false` + 提示「未授予通知权限，后台自动重连保持关闭」+ 诊断事件）；同时在 Android 15 上复验 P1（force-stop 后重开自动恢复服务）与 P2（通知被撤销→设置页红色警告卡 +「打开通知设置」直达 `AppNotificationSettingsActivity`）、真实校园网登录（`OIT-XUESHENG` → CONNECTED）、断网→恢复巡检、「结束本次会话」。验收记录：`android/validation/2026-11-01-redmi-android15/report.md`
- **协议 C4.6 端点已确认（2026-11-01）**: 门户注销的接口层端点 = `http://172.16.11.54/eportal/InterFace.do?method=logout`，**不需要 `userIndex`**（仅凭 IP+MAC 即让该客户端会话失效，实测 204→200）；App 侧仍未接入该能力
- **字体侧收尾（2026-11-01）**: 阅读页 `【】` 异常经 STOCK 对照实验判定为 **App 侧问题**（系统字体原厂时同样不对称）；字体侧已把括号轮廓嵌入 Hanyi 本体（`embed_bracket_glyphs.py`），括号与正文同字体同字号、贴内缘；剩余偏心源于原文 `【` 后的空格，已出交接文档 `docs/APP-HANDOFF-BRACKET.md`（字体仓库 `kkkkikun/oit-font-switch`）。设备当前 = `chalk` 模式
- **遗留问题**: **新发现一项待处理**（见 tasks.md）：外部注销打不掉 App 自己的 session cookie → 「自动重登」端到端触发尚无法从 App 外部制造（**非缺陷**，是验收方法的边界）；协议 C4.6 App 侧注销功能未接入（端点已确认）。协议 C4.5 已于 2026-11-01 销项（校园网允许一账号多设备，无互踢需求）
- **P3/P4 已修（2026-11-01）**: ①新增 `core/NetworkValidationGate.kt`——默认网络「验证通过」只放行一次翻转，`MainActivity.onCapabilitiesChanged` 不再每几秒触发一次探测；红米真机静置 150 秒的校准事件从 25~100 条降到 **0 条**，一次 Wi-Fi 断开→重连后诊断事件总数 4 条。②`BackgroundReconnectController` 的重登路径改用区分性文案（「检测到需要校园网认证，正在自动重登」/「自动重登成功，网络在线」），普通巡检仍是「网络在线，后台巡检中」。Android 单测 53→**61 例**
- **Windows 端 PC 侧全链路实测与修复（2026-11-01）**: 在用户自己的中文 Windows（PowerShell 5.1.26100.9711）上跑完「安装 → 托盘启动 → 独立 exe → 卸载」全链路，暴露并修掉 4 个真缺陷：①4 个 `.ps1` 是 UTF-8 无 BOM + 含中文 → PS 5.1 按 ANSI 解码吞掉引号 → **语法错误，文档推荐的托盘安装/卸载方式在中文 Windows 上完全不可用**；②`stop` 在无 daemon 时打 ERROR 到 stderr → PS 把 stderr 当终止错误 → 安装脚本在第 2 步被打断、**托盘根本没启动**；③缺 tkinter 时只提示 `pip install .[tray]`（tkinter 不是 pip 包，等于死路），且安装脚本托盘启动即崩仍照报「完成！」；④`build_windows.ps1` 重装本项目撞上被占用的入口 exe（WinError 5）、`uninstall_windows.ps1` 用 PATH 上的 `python`/`oit-portal`（venv 场景下都不存在）却照报「卸载完成」。修复后：4 个脚本 PS 解析全 OK、托盘安装 4 步带存活校验、`stop` 幂等返回 0、卸载会核实包/自启项/入口 exe/`~` 临时目录是否真清干净、独立 exe（自包含）正常弹窗。pytest 309→**324**
- **验收截图的账号信息已遮盖并重写历史（2026-11-01）**: 本仓库是**公开仓库**（`kkkkikun/OIT-Net-Portal`，`visibility=PUBLIC`）。三个验收目录的截图里原本可见**学号**，最早的 `2026-10-27-background-reconnect` 那批还可见**真实姓名 + 工号**（教师账号）。处置分两步：①用新提交遮盖全部截图（红米 8 张 / 17 处黑块，vivo 3 张 / 6 处黑块），标签与界面结构保留；②对**唯一真正公开过未遮盖原图的** `00_screen_state.png` 用 `git filter-repo --blob-callback` 重写历史并强推 `android-app`（`40a9d72 → e484110`，所有提交 SHA 都变了）。**核验：全新克隆里该文件在所有历史提交中都只有遮盖版，旧 blob 不在对象库中**。残留边界：GitHub 自身在 GC 前仍可按旧 SHA 临时取到不可达对象
- **v1.0.0 发布与 GitHub Actions 落地（2026-11-01）**: `android-app` 纯快进合并进 `main`（`ffa69aa..a06b8a2`），两条分支现已同步；版本号 `pyproject` → 1.0.0、Android `versionName` 1.0.0 / `versionCode` 2；新增 `CHANGELOG.md`、README 徽章（294→337）+ Gradle Wrapper 8.9 入库；`.github/workflows/ci.yml`（python / android / windows-exe 三 job）+ `release.yml`（打 v* 标签即构建 APK + exe 并挂到 Release）。**首轮 CI 全红，修了 5 个真问题**：①pytest ≥9.2 会把 `LogCaptureHandler` 挂到 `propagate=False` 的 logger 上 → `setup_logging` 的 `if logger.handlers` 幂等判据误判 → 日志文件从未创建（本地 pytest 9.0.3 无此行为，**本地绿、CI 红**）→ 改用自有 handler 标记；②`build_windows.ps1` 此前只装 pystray/pillow/pyinstaller → 托盘模块 import requests 失败 → 更正为「先停运行中的托盘再正常装 `.[tray]`」；③`android-actions/setup-android` 会去装早已下架的 `tools` 包 → 改用 runner 预装 SDK + `yes | sdkmanager --licenses`；④Chaquopy 要求构建机 Python 与 App 内嵌版本一致（3.10），CI 装的却是 runner 自带的 3.12 → Android job 补装 Python 3.10；⑤发版说明的 awk 用 `"^## \["` 正则匹配标题，实测一行都匹配不到 → 改用 `index()`。**第三轮 CI 三 job 全绿（run 41307746362）**。发版后又补了 3 处真问题：⑥`pyproject.toml` 已是 1.0.0 但 `oit_portal/__init__.py` 还写着 `__version__ = "0.1.0"` → `oit-portal --version` 对外报 0.1.0（正式版里的假版本号）→ 改为以包元数据为准 + `tests/test_version.py` 3 例守住；⑦`install_windows_tray.ps1` 有和构建脚本同一个坑（托盘在跑时重装撞 WinError 5）→ 补「先停托盘」；⑧校内网拉不到 pypi 的 setuptools 导致 `pip install` 失败 → 加 `--no-build-isolation` 离线兜底。tag `v1.0.0` 最终指向 `e04c193`（含全部修复），Release 页面已挂 APK + exe
- **App 内嵌快速反馈通道（2026-11-04）**: 给分发给同学的 App 加了**完全内嵌**的反馈入口——设置页底部「意见反馈」卡片 → App 内原生 Compose 表单（类型 / 内容 / 是否附带脱敏诊断摘要），**不跳浏览器、不用问卷链接**。收集端自托管：`oit-portal feedback serve`（默认仅监听回环，`--host 0.0.0.0` 才对外）把反馈按 JSONL 落盘到本机，`oit-portal feedback list` / `export` 集中看与导出 Markdown 清单；**可选**配 `--feishu-webhook` 同步一份到飞书（群机器人发文本 / 多维表格发扁平 JSON），**落盘优先、转发其次**，飞书抖动不会丢反馈。安全边界：反馈载荷只有同学主动填写的文字 + 脱敏摘要，账号/密码/Cookie/完整 URL 所在行**整行丢弃**；提交走 `network.create_session()`（trust_env=False）；收集端无鉴权，只适合可信内网。pytest 338→**403**，Android 单测 61→**73**，端到端联调（真收集端 + App 侧同款桥接 + list/export）通过
- **反馈通道改为飞书直发（2026-11-04）**: 用户明确不想一直开着电脑上的一个端口服务，因此把提交目标从「作者机器上的自托管收集端」改成**飞书 webhook**（云端常驻，作者不占机器）。App 里的地址按形态自动分流：含 `/open-apis/bot/` 的走群机器人（`msg_type` + `content.text`），其它飞书地址走**多维表格扁平 JSON**（键名即表格列名，载荷新增 `category_label` 中文分类与 `submitted_at` 便于建单选列与时间列）。**支持飞书凭证校验**：群机器人签名校验（`timestamp` + `sign`，HMAC-SHA256 后 Base64）与多维表格 Bearer（`Authorization` 头）——因为 webhook 地址会随 APK 分发可被提取，**飞书侧必须开校验**才是有效防线。另外补了一个真坑：飞书即使 HTTP 200 也可能返回 `code != 0`（关键词不匹配、IP 不在白名单），只看状态码会把失败当成功 → 提交层现在检查业务码。自托管收集端**保留**（先审后收 / 完全离线时用）。**反馈通道地址与凭证改为构建期注入**（`android/local.properties` 的 `oit.feedback.endpoint` / `oit.feedback.secret` → Gradle 生成 `BuildConfigFeedback`）：本仓库是公开仓库，真实 webhook 地址与密钥只留在构建者本机，不进版本控制（已验证：APK dex 里有注入值、`git grep` 在入库文件里查不到）。pytest 403→**429**
- **v1.0.1 发版与 OpenFeedback 域名切换（2026-11-09）**: 发版前发现并修复 CI 两个发版阻断（android job 覆写 `local.properties` 丢反馈地址、SDK Maven 地址退占位符）→ 改为仓库变量注入 + fail-fast + 契约测试（pytest 435→436）。OpenFeedback 服务已从裸 IP 切换到域名（IP 停 HTTPS 属有意行为），仓库变量与本机 `local.properties` 均已同步域名值；GitHub runner 从国际出口拉取域名版 `/maven/` 验证成功。**大陆侧可达性已真机验证通过**（手机不开代理：根路径返回服务 JSON、`/admin/` 后台可打开）；开发机 WSL 出口与代理出口的 TLS 重置属本机网络环境特例
- **反馈通道已接上真实飞书多维表格（2026-11-05）**: 用户提供了真实 webhook 地址与 token，已写入 `android/local.properties`（已 gitignore）并用 App 侧同款代码**实测提交成功**（飞书返回 `code:0`），APK 用真实配置重建完成（dex 内含地址与凭据，`git grep` 确认未入库）。**实测发现飞书侧「凭证校验」尚未开启** —— 不带 `Authorization` 头 POST 同样返回 `code:0`，即当前地址泄露即可写入；已在 `docs/app-feedback.md` 给出 curl 自查方法，**分发前必须去飞书把凭证校验打开**。
- **反馈通道迁移到 OpenFeedback（2026-11-05，change `2026-11-05-switch-feedback-to-openfeedback`）**: 飞书直发有四个绕不开的问题——数据只进表格没有统一后台、没有截图、断网即丢、webhook 地址本身就是写入凭据。改为接入 **OpenFeedback**（独立、轻量、可自托管的多应用统一反馈服务，公开仓库 `kkkkikun/OpenFeedback`）：同一个服务端 + 同一个后台，按 `appId` 区分应用。**改动面刻意压到最小**——保留本 App 自己的 Compose 表单与 `FeedbackBridge` 边界，只把桥接实现从「Chaquopy → Python → requests → 飞书」换成「SDK core → HttpURLConnection → OpenFeedback」，表单 UI 与交互不变。三个实质性收益：①**断网不丢**——反馈存本机队列，联网后由 WorkManager 自动补发，且带 `submissionId` 由服务端去重，**补发不会产生重复记录**；②**APK 里不再有任何服务端凭据**——只剩公开的 `appId` 与服务地址（旧方案的飞书 token 已不再被读取，可从 `local.properties` 删除）；③**服务端再校验一遍**——限流（每 appId+IP 每小时 10 条）、字段合法性、附件魔数与数量/大小限制都不信任客户端。新增依赖 `com.kkkkikun.openfeedback:openfeedback-core:0.1.0`（用框架自带 `HttpURLConnection`，**不给宿主引入 OkHttp/Retrofit**，依赖树不变）；SDK 仓库地址经 Gradle 属性 `oit.openfeedback.mavenUrl` 注入（默认 `https://feedback.example.com/maven/`），可指向本地 `file://` 目录做离线构建。反馈类型从三类扩到四类（问题/功能建议/体验问题/其他），服务端兼容旧分类 `issue`/`suggestion`/`ux`/`problem`，**回退安全**。Python 侧 `oit_portal/feedback.py` / `mobile_feedback.py` **保留但 Android 不再调用**（CLI 自托管收集端 `oit-portal feedback serve|list|export` 仍可用）。回滚是单点替换：把注入的桥接换回 `ChaquopyFeedbackBridge` 即可恢复飞书直发，不用回滚服务端也不用动表单 UI。Android 单测 73→**77**（新增 `FeedbackCategoryMappingTest` 4 例，并改 `PortalFeedbackViewModelTest` 断言新分类）
- **已归档 change**: android-ui-refresh（2026-10-27）、android-background-auto-reconnect（2026-10-27）、add-app-feedback-channel（2026-11-04）、switch-feedback-to-feishu-direct（2026-11-04）、switch-feedback-to-openfeedback（2026-11-09）

## 安全红线（改代码前自查）

1. 配置文件不入库（.gitignore 已屏蔽 config.toml / credentials.toml / session.json / *.log / *.har）
2. 日志脱敏：密码/cookie/token 只能经 `log.fingerprint()`（前 4 位 + 长度）
3. 所有认证 Session 必须走 `network.create_session()`（内含 `trust_env = False` + 可选物理网卡绑定）
4. 密码只存 `credentials.toml`（0600）或 `OIT_PORTAL_PASSWORD` 环境变量
