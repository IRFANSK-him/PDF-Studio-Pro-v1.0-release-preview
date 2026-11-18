@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0publish_to_github.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if "%EXITCODE%"=="0" (
  echo PDF Studio Pro source publication completed.
) else (
  echo Publication could not be completed. See the details above.
)
pause
exit /b %EXITCODE%
