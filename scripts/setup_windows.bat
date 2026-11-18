@echo off
setlocal
cd /d "%~dp0.."
where py >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.11 or 3.12 x64 with the py launcher first.
  exit /b 1
)
py -3.12 -m venv .venv
if errorlevel 1 py -3.11 -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m license_server.cli init --base-url http://127.0.0.1:8765
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pytest -q
if errorlevel 1 exit /b 1
echo Setup completed. Start scripts\start_local_license_server.bat, then create a license.
