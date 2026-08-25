@echo off
chcp 65001 >nul
cd /d "%~dp0"
title WxArticleSaver 诊断
echo ==== WxArticleSaver 诊断 ====
echo.
echo 当前目录:
cd
echo.
echo 查找 py:
where py
echo.
echo 查找 python:
where python
echo.
echo Python 版本:
py -3 --version
python --version
echo.
echo pip 版本:
py -3 -m pip --version
python -m pip --version
echo.
echo mitmdump:
where mitmdump
echo.
echo 完成。请截图此窗口。
echo.
pause
