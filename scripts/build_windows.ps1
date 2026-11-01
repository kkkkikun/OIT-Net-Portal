# 在 Windows 原生环境构建独立托盘 App：dist\OIT-Portal.exe
# powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $root
try {
    # 重装本项目会重新生成 Scripts\oit-portal-tray.exe，而托盘 App 正在运行时
    # 该 exe 被 Windows 锁住 → pip 报 [WinError 5] 拒绝访问，构建第一步就失败
    # （2026-11-01 在用户自己的 Windows 上实测）。根因是「托盘在跑」，不是「要重装」，
    # 所以先把它停掉，再正常安装项目依赖（requests / pycryptodome 等托盘会间接导入的包
    # 不能省 —— 少了 requests，生成图标的 `from oit_portal.tray import ...` 就会 ModuleNotFoundError）。
    if (Get-Process -Name "oit-portal-tray" -ErrorAction SilentlyContinue) {
        Write-Host "==> 停止正在运行的托盘 App（重装需要替换入口 exe）" -ForegroundColor Yellow
        Stop-Process -Name "oit-portal-tray" -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }
    & $Python -m pip install --quiet ".[tray]" pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "构建依赖安装失败" }

    # 构建产物若正在运行，同样会被锁住（PyInstaller 无法覆盖）→ 先提示退出。
    if (Get-Process -Name "OIT-Portal" -ErrorAction SilentlyContinue) {
        throw "独立 App 正在运行，请先退出它（托盘图标右键 → 退出）再重新构建"
    }

    New-Item -ItemType Directory -Force -Path "build" | Out-Null
    & $Python -c "from oit_portal.tray import TrayApplication; TrayApplication._make_image('#16a34a').save('build/windows.ico', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
    if ($LASTEXITCODE -ne 0) { throw "应用图标生成失败" }

    Set-Content -Path "build\tray_entry.py" -Encoding UTF8 `
        -Value "from oit_portal.tray import main`n`nmain()"
    & $Python -m PyInstaller --noconfirm --clean --onefile --windowed `
        --paths "$root" --name "OIT-Portal" --icon "build\windows.ico" "build\tray_entry.py"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 构建失败" }
    Write-Host "构建完成：dist\OIT-Portal.exe" -ForegroundColor Green
} finally {
    Pop-Location
}
