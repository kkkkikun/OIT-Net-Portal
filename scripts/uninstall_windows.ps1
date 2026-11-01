# OIT 校园网自动登录 — Windows 卸载
# 用法：powershell -ExecutionPolicy Bypass -File scripts\uninstall_windows.ps1
# 默认保留配置/凭据/日志；加 -Purge 一并删除 %APPDATA%\oit-portal
# 若装在专用 venv 里，请带上 -Python 指向该解释器（否则 PATH 上的 python 不是它）
param(
    [switch]$Purge,
    [string]$Python = "python"
)

$ErrorActionPreference = "Continue"

Write-Host "==> 停止托盘、daemon 与计划任务" -ForegroundColor Cyan
Stop-Process -Name "OIT-Portal", "oit-portal-tray" -Force -ErrorAction SilentlyContinue
Remove-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
    -Name "OIT-Portal" -ErrorAction SilentlyContinue
# 用传入的解释器停 daemon：直接调 oit-portal 依赖 PATH 上有该命令，
# 而装在 venv 里时 PATH 上并没有（2026-11-01 实测），命令找不到会被 2>$null 吞掉。
& $Python -m oit_portal.cli stop 2>&1 | Out-Null
Unregister-ScheduledTask -TaskName "OIT-Portal-Daemon" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "OIT-Portal-OnConnect" -Confirm:$false -ErrorAction SilentlyContinue

Write-Host "==> 卸载 Python 包" -ForegroundColor Cyan
& $Python -m pip uninstall -y oit-portal 2>&1 | Out-Null

# pip 卸载有个静默失败模式：入口 exe 正在被占用时，pip 会跳过它们，
# 照样打印「Successfully uninstalled」，并在 site-packages 留下 ~ 前缀的临时目录。
# 结果是「包没了但 oit-portal.exe / oit-portal-tray.exe 还在」——
# 用户 PATH 上仍能跑到一个指向已删包的旧启动器。这里显式清一遍。
$pyPaths = & $Python -c "import json, sysconfig; print(json.dumps({'scripts': sysconfig.get_path('scripts'), 'purelib': sysconfig.get_path('purelib')}))" 2>$null
if ($pyPaths) {
    $info = $pyPaths | ConvertFrom-Json
    Get-ChildItem -Path $info.scripts -Filter "oit-portal*.exe" -Force -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $info.purelib -Filter "~it_portal*" -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

if ($Purge) {
    Write-Host "==> 删除配置/凭据/日志（-Purge）" -ForegroundColor Cyan
    Remove-Item (Join-Path $env:APPDATA "oit-portal") -Recurse -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "已保留 %APPDATA%\oit-portal（配置/凭据/日志）；如需彻底删除请加 -Purge 重跑"
}

# 核实确实卸载干净，不要无条件报「卸载完成」：
# 之前脚本用 PATH 上的 python / oit-portal，装在 venv 里时两者都不指向实际安装位置，
# 什么都没卸载却照旧打印「卸载完成。」（2026-11-01 实测）
$stillInstalled = (& $Python -m pip show oit-portal 2>&1 | Out-String) -match "(?m)^Name:\s"
$leftoverExe = @()
$leftoverTmp = @()
if ($pyPaths) {
    $info = $pyPaths | ConvertFrom-Json
    $leftoverExe = @(Get-ChildItem -Path $info.scripts -Filter "oit-portal*.exe" -Force -ErrorAction SilentlyContinue)
    $leftoverTmp = @(Get-ChildItem -Path $info.purelib -Filter "~it_portal*" -Force -ErrorAction SilentlyContinue)
}
if ($stillInstalled) {
    Write-Host "警告：在 $Python 中仍能查到 oit-portal 包 —— 它可能装在另一个解释器里，请用对应解释器重跑本脚本。" -ForegroundColor Yellow
} elseif ($leftoverExe.Count -gt 0 -or $leftoverTmp.Count -gt 0) {
    $leftoverNames = @()
    $leftoverNames += $leftoverExe.Name
    if ($leftoverTmp.Count -gt 0) { $leftoverNames += "site-packages 临时目录" }
    Write-Host ("警告：仍有残留（{0}）——多半是文件被占用，请关闭相关程序后重跑。" -f ($leftoverNames -join ", ")) -ForegroundColor Yellow
} else {
    Write-Host "已卸载 Python 包（$Python）。" -ForegroundColor Green
}
$runKey = Get-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" `
    -Name "OIT-Portal" -ErrorAction SilentlyContinue
if ($runKey) {
    Write-Host "警告：开机自启项仍存在。" -ForegroundColor Yellow
} else {
    Write-Host "已移除开机自启项。" -ForegroundColor Green
}
Write-Host "提示：本脚本不会删除 venv 目录，若装在专用虚拟环境里请自行清理。" -ForegroundColor DarkGray
Write-Host "卸载完成。" -ForegroundColor Green
