# OIT 校园网自动登录 — Windows 一键安装（任务计划程序方案）
# 用法（管理员 PowerShell，项目目录内）：
#   powershell -ExecutionPolicy Bypass -File scripts\install_windows.ps1
# 可选参数：
#   -EventTrigger   额外注册「网络已连接」事件触发（登录响应更快）
#   -Python "C:\Path\To\Python\python.exe"  指定 Python
param(
    [switch]$EventTrigger,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$TaskName = "OIT-Portal-Daemon"

function Fail($msg) { Write-Host "错误：$msg" -ForegroundColor Red; exit 1 }

# ── 1. 安装包 ───────────────────────────────────────────────
Write-Host "==> [1/4] 安装 oit-portal 及依赖" -ForegroundColor Cyan
& $Python -m pip install --quiet .
if ($LASTEXITCODE -ne 0) { Fail "pip install 失败" }

# 定位 console script
$exe = (Get-Command "oit-portal.exe" -ErrorAction SilentlyContinue).Source
if (-not $exe) {
    $scriptsDir = & $Python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
    $exe = Join-Path $scriptsDir "oit-portal.exe"
}
if (-not (Test-Path $exe)) { Fail "找不到 oit-portal.exe（请确认 Python Scripts 目录在 PATH，或用 -Python 指定解释器）" }

# ── 2. 配置文件 ─────────────────────────────────────────────
Write-Host "==> [2/4] 生成配置 %APPDATA%\oit-portal" -ForegroundColor Cyan
$cfgDir = Join-Path $env:APPDATA "oit-portal"
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
$cfg = Join-Path $cfgDir "config.toml"
if (-not (Test-Path $cfg)) {
    Copy-Item (Join-Path $PSScriptRoot "..\config.example.toml") $cfg
}

$username = Read-Host "请输入校园网账号（学号/工号）"
if ($username) {
    (Get-Content $cfg) -replace '^username = .*', "username = `"$username`"" | Set-Content $cfg
}
$credFile = Join-Path $cfgDir "credentials.toml"
$sec = Read-Host "请输入校园网密码（输入不回显）" -AsSecureString
$plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
# 单用户目录写凭据（用户 Profile 自带 per-user ACL）
"password = `"$plain`"" | Set-Content $credFile
$plain = $null

# ── 3. 注册任务计划 ─────────────────────────────────────────
Write-Host "==> [3/4] 注册计划任务 $TaskName（登录时自启 + 崩溃自动重启）" -ForegroundColor Cyan
$action = New-ScheduledTaskAction -Execute $exe -Argument "daemon"
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -StartWhenAvailable
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings | Out-Null

if ($EventTrigger) {
    # 网络已连接事件（NetworkProfile 10000）触发一次 once，加速联网响应；
    # 与 daemon 之间靠文件锁互斥，不会重复登录
    $cim = New-CimInstance -ClassName MSFT_TaskEventTrigger -Namespace "Root/Microsoft/Windows/TaskScheduler" `
        -Property @{ Subscription =
        "<QueryList><Query Id='0' Path='Microsoft-Windows-NetworkProfile/Operational'>" +
        "<Select Path='Microsoft-Windows-NetworkProfile/Operational'>*[System[EventID=10000]]</Select>" +
        "</Query></QueryList>" } -ClientOnly
    $onceAction = New-ScheduledTaskAction -Execute $exe -Argument "once"
    Register-ScheduledTask -TaskName "OIT-Portal-OnConnect" -Action $onceAction -Trigger $cim `
        -Settings $settings | Out-Null
    Write-Host "    已注册联网事件触发器（OIT-Portal-OnConnect）" -ForegroundColor DarkCyan
}

# ── 4. 立即启动 ─────────────────────────────────────────────
Write-Host "==> [4/4] 立即启动 daemon" -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TaskName
Write-Host ""
Write-Host "完成！daemon 已运行。常用操作：" -ForegroundColor Green
Write-Host "  状态:    oit-portal status"
Write-Host "  单次登录: oit-portal once"
Write-Host "  停止:    oit-portal stop"
Write-Host "  卸载:    powershell -File scripts\uninstall_windows.ps1"
Write-Host "  日志:    %APPDATA%\oit-portal\logs\oit-portal.log"
