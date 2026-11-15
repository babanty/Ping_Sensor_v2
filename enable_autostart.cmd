@echo off
setlocal
set "PING_TRAY_DIR=%~dp0"
powershell.exe -NoProfile -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "$startup = [Environment]::GetFolderPath('Startup');" ^
    "if ([string]::IsNullOrWhiteSpace($startup)) { throw 'Windows Startup folder was not found.' };" ^
    "$target = Join-Path $env:PING_TRAY_DIR 'start.cmd';" ^
    "if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw 'start.cmd was not found.' };" ^
    "$null = New-Item -ItemType Directory -Path $startup -Force;" ^
    "$shell = New-Object -ComObject WScript.Shell;" ^
    "$shortcut = $shell.CreateShortcut((Join-Path $startup 'Ping Tray.lnk'));" ^
    "$shortcut.TargetPath = $target;" ^
    "$shortcut.WorkingDirectory = $env:PING_TRAY_DIR;" ^
    "$shortcut.WindowStyle = 7;" ^
    "$shortcut.Save();"
if errorlevel 1 (
    echo Failed to enable Ping Tray autostart.
    pause
    exit /b 1
)
echo Ping Tray will start when you sign in to Windows.
pause
exit /b 0
