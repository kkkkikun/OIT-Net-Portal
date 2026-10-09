# OIT 校园网自动登录 — Windows 卸载
# 用法：powershell -ExecutionPolicy Bypass -File scripts\uninstall_windows.ps1
# 默认保留配置/凭据/日志；加 -Purge 一并删除 %APPDATA%\oit-portal
param([switch]$Purge)

$ErrorActionPreference = "Continue"

Write-Host "==> 停止 daemon 与计划任务" -ForegroundColor Cyan
oit-portal stop 2>$null
Unregister-ScheduledTask -TaskName "OIT-Portal-Daemon" -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName "OIT-Portal-OnConnect" -Confirm:$false -ErrorAction SilentlyContinue

Write-Host "==> 卸载 Python 包" -ForegroundColor Cyan
python -m pip uninstall -y oit-portal 2>$null

if ($Purge) {
    Write-Host "==> 删除配置/凭据/日志（-Purge）" -ForegroundColor Cyan
    Remove-Item (Join-Path $env:APPDATA "oit-portal") -Recurse -Force -ErrorAction SilentlyContinue
} else {
    Write-Host "已保留 %APPDATA%\oit-portal（配置/凭据/日志）；如需彻底删除请加 -Purge 重跑"
}
Write-Host "卸载完成。" -ForegroundColor Green
