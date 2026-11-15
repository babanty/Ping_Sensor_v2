@echo off
setlocal
powershell.exe -NoProfile -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "$startup = [Environment]::GetFolderPath('Startup');" ^
    "if ([string]::IsNullOrWhiteSpace($startup)) { throw 'Windows Startup folder was not found.' };" ^
    "$shortcut = Join-Path $startup 'Ping Tray.lnk';" ^
    "if (Test-Path -LiteralPath $shortcut) { Remove-Item -LiteralPath $shortcut -Force };"
if errorlevel 1 (
    echo Failed to disable Ping Tray autostart.
    pause
    exit /b 1
)
echo Ping Tray autostart is disabled.
pause
exit /b 0
