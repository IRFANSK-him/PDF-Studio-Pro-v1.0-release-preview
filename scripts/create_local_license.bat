@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" exit /b 1
".venv\Scripts\python.exe" -m license_server.admin_cli create
exit /b %ERRORLEVEL%
