@echo off
setlocal
cd /d "%~dp0"
uv sync --locked --managed-python
if errorlevel 1 (
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "ping_tray.py" %*
