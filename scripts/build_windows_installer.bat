@echo off
setlocal
cd /d "%~dp0.."
if not exist "dist\PDF-Studio-Pro\PDF-Studio-Pro.exe" (
 echo Build portable EXE first: scripts\build_windows_portable.bat
 exit /b 1
)
where ISCC.exe >nul 2>nul
if not errorlevel 1 (
  ISCC.exe installer\PDFStudioPro.iss
  exit /b %ERRORLEVEL%
)
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" installer\PDFStudioPro.iss
  exit /b %ERRORLEVEL%
)
echo Install Inno Setup 6 and add ISCC.exe to PATH, then retry.
exit /b 1
