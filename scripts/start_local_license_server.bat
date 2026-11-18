@echo off
setlocal
cd /d "%~dp0.."
if not exist "secrets\license_private.pem" (
  echo Run scripts\setup_windows.bat first.
  exit /b 1
)
".venv\Scripts\python.exe" -m uvicorn license_server.api:app --host 127.0.0.1 --port 8765
exit /b %ERRORLEVEL%
