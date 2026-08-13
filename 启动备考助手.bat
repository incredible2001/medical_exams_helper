@echo off
chcp 65001 >nul
rem ==============================================
rem  医考帮备考助手 - 双击即可启动
rem  首次使用请先双击 install.bat 安装依赖
rem ==============================================
title 医考帮备考助手
cd /d "%~dp0"

set "PYEXE="
if exist ".venv\Scripts\pythonw.exe" set "PYEXE=.venv\Scripts\pythonw.exe"
if not defined PYEXE if exist "venv\Scripts\pythonw.exe" set "PYEXE=venv\Scripts\pythonw.exe"
if not defined PYEXE where pythonw >nul 2>nul && set "PYEXE=pythonw"
if not defined PYEXE where python >nul 2>nul && set "PYEXE=python"
if not defined PYEXE where py >nul 2>nul && set "PYEXE=py"

if defined PYEXE goto :start

echo.
echo  [错误] 没找到 Python。
echo  请先安装 Python 3.11 或更高版本，安装时勾选 Add python.exe to PATH：
echo  https://www.python.org/downloads/
echo  装好后：先双击 install.bat 安装依赖，再双击本文件启动。
echo.
pause
exit /b 1

:start
start "" "%PYEXE%" main.py
