@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "runtime\python.exe" (
  runtime\python.exe remove_certificate.py
  exit /b
)
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 remove_certificate.py
  exit /b
)
python remove_certificate.py
