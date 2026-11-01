# SNAPSHOT.md — 项目状态快照

> 最后更新: 2026-11-01 | 验证: pytest 324 passed (无网络) + Android testDebugUnitTest 61 例 + clean assembleDebug/lintDebug + vivo V1936A 真机复现验收（2026-10-31）+ 红米 K50 Ultra / Android 15 通知权限路径验收（2026-11-01）+ Windows 端 PC 侧全链路实测（2026-11-01）

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
| 测试 | pytest，324 用例全部无网络（FakeSession + fixture 状态机 + Android/Windows 托盘/Windows 脚本/Linux 打包静态契约测试）；Android 另有 61 例 JUnit 单测 |
| 打包 | pyproject.toml + setuptools，console_scripts: oit-portal；Linux 离线包 `scripts/build_linux.sh`（wheelhouse tar.gz + SHA256）；Windows PyInstaller exe |
| 格式化 | 无强制工具，遵循现有代码风格 |

## Git 状态

- 分支: android-app（工作区干净，VPN 分流 / configure / Linux 离线包 / Windows 脚本修复已提交）
- 最近提交:
  - `46013cd` fix(windows): .ps1 改 UTF-8 with BOM + 托盘安装 4 步校验 + stop 幂等 + 卸载核实
  - `5b639c3` docs(windows): 记录 PS 5.1 的 5 个新坑 + 部署说明补齐
  - `72c903d` chore(validation): 遮盖验收截图里的学号 + 补录最近任务与阅读页证据
  - `148b59b` docs(tasks): 协议 C4.6 App 侧注销按用户确认标记为暂不做
  - `210a5e4` docs(tasks): 销掉陈旧待办，重分类为待决策/阻塞/已知边界
  - `dc3c3e6` docs: 同步 VPN 分流 / configure / Linux 离线包说明与 294 用例基线

## 目录结构

```
oit_portal/
├── cli.py                  # CLI 入口: status/once/daemon/stop/login-info/capture/configure
├── capture.py              # 抓包向导（_HEURISTIC_ENDPOINTS 等 fallback 常量）
├── discover.py             # 入口链路发现（302 / meta refresh / JS 三跳）
├── probe.py                # 三态探测 online/captive/offline，多探测点双确认
├── daemon.py               # 常驻守护（探活 + 保活 + 退避 + WiFi SSID 触发）
├── keepalive.py            # 心跳
├── htmlutil.py             # HTML/内联 JS 解析（find_aes / form_action / analyze_form）
├── protocol_overrides.py   # protocol.json 合并进 CAPTURED（仅替换已有键）
├── network.py              # 统一认证 Session：trust_env=False + 可选物理网卡绑定（VPN 分流）
├── mobile_bridge.py        # 路线B 移动端桥接（脱敏探测/单次登录，无 capture/daemon）
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
- **验收截图的学号已遮盖（2026-11-01）**: 本仓库是**公开仓库**（`kkkkikun/OIT-Net-Portal`，`visibility=PUBLIC`），截图里原本直接可见学号。按用户决定用新提交遮盖（8 张图 / 17 处黑块，整串 + 最近任务卡片里的片段），标签与界面结构保留；**git 历史里仍留有原始图片**，彻底清除需 `git filter-repo` 重写历史
- **已归档 change**: android-ui-refresh（2026-10-27）、android-background-auto-reconnect（2026-10-27）

## 安全红线（改代码前自查）

1. 配置文件不入库（.gitignore 已屏蔽 config.toml / credentials.toml / session.json / *.log / *.har）
2. 日志脱敏：密码/cookie/token 只能经 `log.fingerprint()`（前 4 位 + 长度）
3. 所有认证 Session 必须走 `network.create_session()`（内含 `trust_env = False` + 可选物理网卡绑定）
4. 密码只存 `credentials.toml`（0600）或 `OIT_PORTAL_PASSWORD` 环境变量
