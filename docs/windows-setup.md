# Windows 托盘 App 使用与部署

## 使用托盘 App（推荐）

支持 Windows 10 / Windows 11。托盘 App 在登录 Windows 后自动运行，在后台完成校园网认证和保活，不需要保留终端窗口，也不需要管理员权限。

### 源码安装

前置要求：Python 3.9+（[python.org](https://www.python.org/downloads/) 安装时勾选 *Add python.exe to PATH*），
并且**必须勾选 *tcl/tk and IDLE*** —— 托盘的账号设置窗口基于 tkinter，
而 tkinter 不是 pip 包，漏勾了只能重跑安装程序补上（Modify → 勾选 *tcl/tk and IDLE*）。

> 若已经装好 Python 却缺 tkinter，先跑 `python -c "import tkinter"` 确认。
> 不想用托盘界面的话，可以只用命令行：`oit-portal configure`（同样能设置账号密码）。

在项目目录打开普通 PowerShell：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_tray.ps1
```

脚本分四步执行：**① 检查运行环境**（tkinter 与 pystray/Pillow，缺了当场报错并给出修法）→
**② 安装 `.[tray]` 依赖** → **③ 准备 `%APPDATA%\oit-portal\config.toml` 并写入当前用户的开机自启项** →
**④ 启动 App 并确认进程真的存活**（启动即退出会明确报错，不会假装成功）。
首次启动会弹出账号设置窗口；输入校园网账号和密码，点击“保存并连接”。

如果旧版已注册 `OIT-Portal-Daemon` 计划任务，安装脚本会停止并移除它，避免两个守护同时运行。加 `-NoAutoStart` 可只安装、不注册开机自启。

装在专用虚拟环境里时，用 `-Python` 指定解释器（否则脚本会用 PATH 上的 `python`）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows_tray.ps1 -Python "D:\oit-portal-venv\Scripts\python.exe"
```

### 托盘操作

右键屏幕右下角的 OIT 图标（可能在“隐藏的图标”中）：

- **状态与详情**：绿色表示在线，蓝色表示检测中，灰色表示离线/暂停，橙色表示需要人工处理，红色表示失败。
- **立即重新连接**：唤醒现有守护循环，立即重新探测，不会并发执行第二个登录。
- **暂停/启动自动登录**：暂停会停止后台循环，下次启动 App 时仍默认恢复自动登录。
- **账号设置**：修改账号密码；保存后自动用新配置重启连接。
- **开机自动启动**：切换 HKCU `Run` 注册表项，只影响当前 Windows 用户。
- **打开日志文件夹**：定位连接失败、验证码或协议变化问题。
- **退出**：停止托盘和后台任务。

### VPN 开启时登录校园网

在“账号设置”中勾选 **VPN 开启时仍使用校园网直连**。校园网探测、SSO 和 ePortal 请求会绑定到物理 Wi‑Fi/有线网卡，不经过系统 VPN 路由；其他应用和 VPN 连接本身不受影响，也不需要管理员权限。

通常将“物理网卡 IPv4”留空即可自动识别。无法连接时运行 `ipconfig`，找到连接校园 Wi‑Fi 的适配器（不是 VPN/TAP/TUN/Clash），把它的 IPv4 填入后保存。也可直接编辑 `%APPDATA%\oit-portal\config.toml`：

```toml
[advanced]
bypass_vpn = true
direct_source_ip = ""  # 例如 "172.18.10.25"；空 = 自动识别
```

DHCP 更换地址或切换网卡后请重启托盘 App。VPN 若启用 kill switch、强制全隧道/禁止局域网，或学校网络另有访问限制，仍可能无法直连；此时需在 VPN 客户端允许校园网分流，工具不会关闭或修改 VPN。

### 独立 exe 构建

在 Windows 原生环境执行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

产物为 `dist\OIT-Portal.exe`，已包含 Python、托盘依赖和登录核心，可分发给未安装 Python 的机器。直接运行 exe 即可；首次使用仍需录入账号。

构建脚本只安装构建期第三方依赖（`pystray` / `pillow` / `pyinstaller`），
PyInstaller 通过 `--paths` 从源码树直接导入本项目 —— **不会重装本项目**，
因此在托盘 App 正从同一个虚拟环境运行时构建也不会被文件锁挡住。
如果 `OIT-Portal.exe` 本身正在运行，脚本会提示先退出再构建。

> PyInstaller、注册表自启和托盘交互必须在 Windows 原生环境验证，WSL/Linux 下的测试不能代替这些验收。

## 配置与日志

- 配置：`%APPDATA%\oit-portal\config.toml`
- 密码：`%APPDATA%\oit-portal\credentials.toml`，与主配置分开，仅当前用户目录可访问
- SSO 会话：`%APPDATA%\oit-portal\session.json`
- 日志：`%APPDATA%\oit-portal\logs\oit-portal.log`（轮转 1MB×3）
- 所有配置、凭据和日志默认在卸载时保留

需要验证码时，连接校园 WiFi 后用浏览器访问任意 HTTP 网站完成一次人工登录；也可参考 `oit-portal login-info`。协议首次适配仍按 [抓包指南](capture-guide.md) 操作。

## 卸载

```powershell
# 默认保留配置、凭据和日志
powershell -ExecutionPolicy Bypass -File scripts\uninstall_windows.ps1

# 连配置、凭据和日志一起删除
powershell -ExecutionPolicy Bypass -File scripts\uninstall_windows.ps1 -Purge

# 装在专用虚拟环境里时，用 -Python 指定解释器
powershell -ExecutionPolicy Bypass -File scripts\uninstall_windows.ps1 -Python "D:\oit-portal-venv\Scripts\python.exe"
```

卸载会移除托盘开机自启、停止托盘/旧 daemon 并移除旧计划任务。

脚本结束前会**核实**是否真的卸载干净：包是否还在、开机自启项是否还在、
入口 exe 和 pip 遗留的临时目录是否还在。哪一项没清掉就打印**警告**并说明怎么办，
不会无条件报「卸载完成」。`pip uninstall` 有个静默失败模式 —— 入口 exe 被占用时它会跳过
却照样打印「Successfully uninstalled」，所以脚本会额外清理一遍残留。

> 脚本不会删除虚拟环境目录本身；若装在专用 venv 里请自行清理。

## 备用：CLI + 计划任务

不想运行托盘界面时，可使用原有方式（管理员 PowerShell）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
```

该脚本注册 **OIT-Portal-Daemon** 计划任务（登录自启 + 崩溃 3 次内自动重启 + 无执行时限）并立即启动。可选 `-EventTrigger` 会额外注册网络连接事件触发的 `oit-portal once`。

常用命令：

```powershell
oit-portal status      # online / captive / offline
oit-portal once        # 手动登录一次
oit-portal daemon      # 前台运行守护循环
oit-portal stop        # 停止 daemon
```

计划任务管理：

```powershell
Get-ScheduledTask OIT-Portal-Daemon
Start-ScheduledTask OIT-Portal-Daemon
Stop-ScheduledTask OIT-Portal-Daemon
```

托盘和 CLI daemon 使用同一单实例锁，但不要同时部署两套自启方式。

## Windows 验收清单

1. 首次启动弹出设置，保存后图标进入检测中并最终在线。
2. 断开/重连校园 WiFi，托盘状态变化且自动恢复；手动重连只触发一个后台循环。
3. 暂停后不再自动认证，恢复和修改账号后能重新连接。
4. 重启 Windows 后仅当前用户自动启动；托盘自启开关与注册表状态一致。
5. 打开日志、退出、卸载及 `-Purge` 行为符合上述说明。
6. 独立 exe 在未安装 Python 的 Windows 机器上完成相同流程。

### 2026-11-01 实测进度（用户自己的中文 Windows / PowerShell 5.1.26100.9711）

| # | 状态 | 证据 |
|---|------|------|
| 1 | ⏳ 部分 | 设置窗口已验证弹出、中文渲染正常、账号从 `config.toml` 预填；**保存后的真实登录待用户在本机输入密码** |
| 2 | ⏳ 待验 | 需校园网账号密码 + 断开/重连 Wi-Fi |
| 3 | ⏳ 待验 | 同上 |
| 4 | ⏳ 部分 | HKCU `Run` 自启项已验证只写当前用户、指向正确 exe；**重启 Windows 后的实际拉起未验证**（不能重启用户的机器） |
| 5 | ✅ 通过 | 卸载脚本实测：进程/自启项/包/入口 exe/`~` 临时目录全部清干净，配置默认保留；`-Purge` 分支用假 APPDATA 验证过删除生效 |
| 6 | ✅ 通过 | `dist\OIT-Portal.exe` 独立构建并成功弹出设置窗口（自包含，不需要系统 Python） |

另已验证：4 个 `.ps1` 在 PS 5.1 下解析全部 OK（UTF-8 with BOM 契约）、
`oit-portal status/once/login-info` CLI 行为正常、托盘安装 4 步流程全绿。
