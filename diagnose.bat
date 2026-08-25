@echo off
chcp 65001 >nul
cd /d "%~dp0"
title WxArticleSaver 诊断

echo ==== WxArticleSaver 诊断 ====
echo.
echo 当前目录:
cd
echo.

if exist "runtime\python.exe" (
  echo [便携版] 找到内置 Python:
  "runtime\python.exe" --version
  echo.
  echo 检查 mitmproxy:
  "runtime\python.exe" -c "import mitmproxy; print('mitmproxy: OK')"
  echo.
) else (
  echo [源码版] 未找到 runtime\python.exe，检查系统 Python:
  where py 2>nul
  where python 2>nul
  echo.
  py -3 --version 2>nul
  python --version 2>nul
  echo.
)

if exist "launcher.py" (echo launcher.py: OK) else (echo launcher.py: MISSING)
if exist "wx_article_saver.py" (echo wx_article_saver.py: OK) else (echo wx_article_saver.py: MISSING)
if exist ".wxas_ca" (echo .wxas_ca: EXISTS) else (echo .wxas_ca: not created yet)
if exist "proxy_backup.json" (echo proxy_backup.json: EXISTS - previous proxy state may need recovery) else (echo proxy_backup.json: none)
if exist "run.log" (echo run.log: EXISTS) else (echo run.log: none)

echo.
echo 完成。若需要排查问题，请截图此窗口并附上 run.log。
echo.
pause
