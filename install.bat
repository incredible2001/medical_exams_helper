@echo off
chcp 65001 >nul
rem ==============================================
rem  医考帮备考助手 - 一键安装依赖（只需运行一次）
rem ==============================================
title 医考帮备考助手 - 安装依赖
cd /d "%~dp0"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py"

if defined PY goto :have_py

echo.
echo  [错误] 没找到 Python。
echo  请先安装 Python 3.11 或更高版本，安装时勾选 Add python.exe to PATH：
echo  https://www.python.org/downloads/
echo.
pause
exit /b 1

:have_py
echo ============================================
echo   正在安装依赖（需要联网，约 1 到 2 分钟）
echo ============================================
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :err

echo.
echo  安装完成！现在双击「启动备考助手.bat」即可使用。
echo  首次打开后点窗口里的「设置」填入你的 API Key。
echo.
pause
exit /b 0

:err
echo.
echo  [失败] 安装出错，请把上方红字截图发给维护者。
echo.
pause
exit /b 1
