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

见 [tasks.md](.claude/docs/tasks.md) 与 [SNAPSHOT.md](.claude/docs/SNAPSHOT.md)。
