@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup_windows.bat first.
  exit /b 1
)
if "%PDFSP_ALLOW_LOCAL_BUILD%"=="1" (
  ".venv\Scripts\python.exe" scripts\release_preflight.py --allow-local
) else (
  ".venv\Scripts\python.exe" scripts\release_preflight.py
)
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onedir --windowed --name "PDF-Studio-Pro" --icon "assets\pdfstudio.ico" --add-data "assets;assets" --add-data "config\license_client.json;config" app.py
if errorlevel 1 exit /b 1
echo Portable executable: dist\PDF-Studio-Pro\PDF-Studio-Pro.exe
exit /b 0
