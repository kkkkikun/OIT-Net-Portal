# Windows 部署指南

## 前置要求

- Windows 10 1809+ / Windows 11
- Python 3.9+（[python.org](https://www.python.org/downloads/) 安装时勾选 *Add python.exe to PATH*）

## 安装步骤（管理员 PowerShell）

```powershell
cd OIT-Net-Portal
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
```

脚本会：`pip install .` → 生成 `%APPDATA%\oit-portal\config.toml`（询问账号）→
写 `credentials.toml`（询问密码）→ 注册计划任务 **OIT-Portal-Daemon**（登录自启 + 崩溃 3 次内自动重启 + 无执行时限）→ 立即启动。

### 可选：联网事件加速

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1 -EventTrigger
```

额外注册「网络已连接」（NetworkProfile 事件 10000）触发 `oit-portal once`，刚连上 WiFi 时秒级响应。
与 daemon 之间靠单实例文件锁互斥，不会重复登录。

## 验证

```powershell
oit-portal status      # online / captive / offline
oit-portal once        # 手动登录一次
oit-portal stop        # 停止 daemon
```

- **重启电脑**：登录 Windows 后 daemon 自启，浏览器直接可用
- 日志：`%APPDATA%\oit-portal\logs\oit-portal.log`（轮转 1MB×3）

## 管理与卸载

```powershell
# 查看/手动控制计划任务
Get-ScheduledTask OIT-Portal-Daemon
Start-ScheduledTask OIT-Portal-Daemon
Stop-ScheduledTask  OIT-Portal-Daemon

# 卸载（默认保留配置；-Purge 连配置凭据日志一起删）
powershell -ExecutionPolicy Bypass -File scripts\uninstall_windows.ps1 -Purge
```

## 常见问题

| 现象 | 处理 |
|------|------|
| 任务显示运行但没登录 | 看日志；多数是协议细节未填（先完成 docs/capture-guide.md 抓包） |
| 需要验证码 | `oit-portal login-info`，浏览器人工登一次，daemon 自动收割 SSO 会话续跑 |
| 换了密码 | 编辑 `%APPDATA%\oit-portal\credentials.toml`，然后 `oit-portal stop` + `Start-ScheduledTask OIT-Portal-Daemon` |
| 不想用计划任务 | 回退方案：`shell:startup` 放一个 `oit-portal daemon` 的快捷方式（目标加 `pythonw` 隐藏窗口） |

> 注：`scripts/*.ps1` 与 pyinstaller 打包（一期可选）需在 **Windows 原生环境**执行验证，
> WSL 内无法运行 PowerShell 计划任务注册。
