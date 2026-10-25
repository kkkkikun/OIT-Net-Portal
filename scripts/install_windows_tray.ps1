# OIT 校园网托盘 App — Windows 普通用户安装
# powershell -ExecutionPolicy Bypass -File scripts\install_windows_tray.ps1
param(
    [switch]$NoAutoStart,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
function Fail($msg) { Write-Host "错误：$msg" -ForegroundColor Red; exit 1 }

Write-Host "==> [1/3] 安装托盘 App 及依赖" -ForegroundColor Cyan
& $Python -m pip install --quiet ".[tray]"
if ($LASTEXITCODE -ne 0) { Fail "pip install 失败" }

$exe = (Get-Command "oit-portal-tray.exe" -ErrorAction SilentlyContinue).Source
if (-not $exe) {
    $scriptsDir = & $Python -c "import sysconfig; print(sysconfig.get_path('scripts'))"
    $exe = Join-Path $scriptsDir "oit-portal-tray.exe"
}
if (-not (Test-Path $exe)) { Fail "找不到 oit-portal-tray.exe，请用 -Python 指定解释器" }

Write-Host "==> [2/3] 配置用户目录与开机自启" -ForegroundColor Cyan
$cfgDir = Join-Path $env:APPDATA "oit-portal"
New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
$cfg = Join-Path $cfgDir "config.toml"
if (-not (Test-Path $cfg)) {
    Copy-Item (Join-Path $PSScriptRoot "..\config.example.toml") $cfg
}

# 避免旧计划任务和托盘同时运行守护循环。
& $Python -m oit_portal.cli stop 2>$null | Out-Null
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

Write-Host "==> [3/3] 启动托盘 App" -ForegroundColor Cyan
Start-Process -FilePath $exe
Write-Host ""
Write-Host "完成！请在首次弹出的窗口中输入账号密码。" -ForegroundColor Green
Write-Host "之后可从屏幕右下角托盘图标管理连接。卸载：scripts\uninstall_windows.ps1"
