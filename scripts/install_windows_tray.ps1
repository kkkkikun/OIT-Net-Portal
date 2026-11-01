# OIT 校园网托盘 App — Windows 普通用户安装
# powershell -ExecutionPolicy Bypass -File scripts\install_windows_tray.ps1
param(
    [switch]$NoAutoStart,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
function Fail($msg) { Write-Host "错误：$msg" -ForegroundColor Red; exit 1 }

Write-Host "==> [1/4] 检查运行环境" -ForegroundColor Cyan
# 原生命令的 stderr 在 $ErrorActionPreference="Stop" 下会变成终止错误，
# 所以探活检查期间临时放宽错误策略，只看退出码。
$ErrorActionPreference = "Continue"
& $Python -c "import tkinter" 2>&1 | Out-Null
$hasTk = ($LASTEXITCODE -eq 0)
& $Python -c "import pystray, PIL" 2>&1 | Out-Null
$hasTrayDeps = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if (-not $hasTk) {
    Fail "当前 Python 缺少 tkinter，托盘界面无法启动。`n    tkinter 不是 pip 包：请重新运行 Python 安装程序 → Modify → 勾选 tcl/tk and IDLE → 重新安装后再执行本脚本。`n    不想用托盘界面的话，可改用命令行：$Python -m oit_portal.cli configure"
}
if (-not $hasTrayDeps) {
    Fail "缺少托盘依赖，请先执行：& '$Python' -m pip install '.[tray]'"
}

Write-Host "==> [2/4] 安装托盘 App 及依赖" -ForegroundColor Cyan
# 重装本项目会重新生成 Scripts\oit-portal-tray.exe，而托盘 App 正在运行时
# 该 exe 被 Windows 锁住 → pip 报 [WinError 5] 拒绝访问，安装在第 2 步就失败
# （与 build_windows.ps1 是同一个坑）。先停掉运行中的托盘，第 4 步会重新拉起。
if (Get-Process -Name "oit-portal-tray" -ErrorAction SilentlyContinue) {
    Write-Host "    停止正在运行的托盘 App（重装需要替换入口 exe）" -ForegroundColor Yellow
    Stop-Process -Name "oit-portal-tray" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
& $Python -m pip install --quiet ".[tray]"
if ($LASTEXITCODE -ne 0) {
    # 常见于校内网：pip 要拉 setuptools 到隔离构建环境，pypi.org 读超时。
    # venv 里通常已有 setuptools，直接关掉构建隔离即可离线安装。
    Write-Host "    常规安装失败（多为拉不到 pypi 的 setuptools），改用 --no-build-isolation 重试" -ForegroundColor Yellow
    & $Python -m pip install --quiet --no-build-isolation ".[tray]"
}
if ($LASTEXITCODE -ne 0) { Fail "pip install 失败" }

$exe = (Get-Command "oit-portal-tray.exe" -ErrorAction SilentlyContinue).Source
if (-not $exe) {
    $scriptsDir = & $Python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
    $exe = Join-Path $scriptsDir "oit-portal-tray.exe"
}
if (-not (Test-Path $exe)) { Fail "找不到 oit-portal-tray.exe，请用 -Python 指定解释器" }

Write-Host "==> [3/4] 配置用户目录与开机自启" -ForegroundColor Cyan
$cfgDir = Join-Path $env:APPDATA "oit-portal"
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
$cfg = Join-Path $cfgDir "config.toml"
if (-not (Test-Path $cfg)) {
    Copy-Item (Join-Path $PSScriptRoot "..\config.example.toml") $cfg
}

# 避免旧计划任务和托盘同时运行守护循环。
# 这一步是「尽力而为」：新机器上没有 daemon 在跑是正常情况，
# 而 oit_portal 的日志默认写 stderr，PowerShell 5.1 在 Stop 模式下
# 会把原生命令的 stderr 当成终止错误，把安装打断在启动托盘之前
# （2026-11-01 在中文 Windows 上实测）。这里临时放宽错误策略。
$ErrorActionPreference = "Continue"
& $Python -m oit_portal.cli stop 2>&1 | Out-Null
$ErrorActionPreference = "Stop"
$oldTask = Get-ScheduledTask -TaskName "OIT-Portal-Daemon" -ErrorAction SilentlyContinue
if ($oldTask) {
    Stop-ScheduledTask -TaskName "OIT-Portal-Daemon" -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName "OIT-Portal-Daemon" -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "    已移除旧版 OIT-Portal-Daemon 计划任务" -ForegroundColor DarkCyan
}
Unregister-ScheduledTask -TaskName "OIT-Portal-OnConnect" -Confirm:$false -ErrorAction SilentlyContinue

$runKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
if ($NoAutoStart) {
    Remove-ItemProperty -Path $runKey -Name "OIT-Portal" -ErrorAction SilentlyContinue
} else {
    Set-ItemProperty -Path $runKey -Name "OIT-Portal" -Value ('"{0}"' -f $exe)
}

Write-Host "==> [4/4] 启动托盘 App" -ForegroundColor Cyan
Start-Process -FilePath $exe
# 必须确认托盘真的活着再报完成：缺 tkinter 之类的依赖问题会让它启动即崩，
# 而之前脚本照旧打印「完成！」，用户只会等一个永远不弹出的窗口
# （2026-11-01 在用户自己的中文 Windows 上实测）。
Start-Sleep -Seconds 3
$running = Get-Process -Name "oit-portal-tray" -ErrorAction SilentlyContinue
if (-not $running) {
    Fail "托盘 App 启动后立即退出（通常是依赖缺失）。请手动运行 '$exe' 查看报错；`n    日志：$env:APPDATA\oit-portal\logs\oit-portal.log"
}
Write-Host ""
Write-Host "完成！请在首次弹出的窗口中输入账号密码。" -ForegroundColor Green
Write-Host "之后可从屏幕右下角托盘图标管理连接。卸载：scripts\uninstall_windows.ps1"
