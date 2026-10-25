# 在 Windows 原生环境构建独立托盘 App：dist\OIT-Portal.exe
# powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
param([string]$Python = "python")

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $root
try {
    & $Python -m pip install --quiet ".[tray]" pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "构建依赖安装失败" }

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
