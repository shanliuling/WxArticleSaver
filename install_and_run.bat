@echo off
chcp 65001 >nul
cd /d "%~dp0"
title WxArticleSaver v1.0.0
echo ============================================================
echo WxArticleSaver v1.0.0
echo ============================================================
echo.
echo 首次运行会自动检查依赖；运行日志写入 run.log。
echo.
echo [检查 Python]

where py >nul 2>&1
if not errorlevel 1 (
  set "PY=py -3"
  goto FOUND
)

where python >nul 2>&1
if not errorlevel 1 (
  set "PY=python"
  goto FOUND
)

echo.
echo [错误] 没找到 Python。
echo 请安装 Python 3.11 或 3.12，并勾选 Add Python to PATH。
echo.
echo 也可以在 CMD 里输入 python --version 检查。
echo.
pause
exit /b 1

:FOUND
echo Python 命令: %PY%
echo.
echo [安装/检查依赖]
%PY% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo [提示] 官方源安装失败，正在切换国内镜像重试...
  %PY% -m pip install --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
)
if errorlevel 1 (
  echo.
  echo [错误] Python 依赖安装失败。
  echo 请截图这个窗口，或者把 run.log 发给我。
  echo.
  pause
  exit /b 2
)

echo.
echo [启动]
%PY% -u launcher.py
set "RC=%ERRORLEVEL%"
echo.
echo WxArticleSaver 已退出，退出码: %RC%
echo 如果不是你主动 Ctrl+C，请把 run.log 发给我。
echo.
pause
exit /b %RC%
