@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title 抓取当前屏幕界面
rem ============================================================
rem  抓取当前模拟器屏幕的界面 XML + 截图，供排障用
rem  使用方法：
rem    1. 放在解压目录（与 config.toml 同目录）
rem    2. 打开医考帮，停在「识别成评论」的那个题目页
rem    3. 双击运行
rem    4. 把「界面XML.txt」和「屏幕截图.png」发给作者
rem ============================================================
cd /d "%~dp0"
rem 放在 tools/ 里运行时，config.toml 在上级目录
if not exist "config.toml" cd ..

set "ADB="
powershell -NoProfile -Command "$l=Get-Content config.toml|Where-Object{$_ -like 'path*'}|Select-Object -First 1; $p=$l -split [char]34; $p[1] | Out-File -Encoding ascii -FilePath $env:TEMP\adbpath.txt" >nul 2>nul
if exist "%TEMP%\adbpath.txt" set /p ADB=<"%TEMP%\adbpath.txt"
if "%ADB%"=="" if exist "C:\Program Files\Netease\MuMu Player 12\shell\adb.exe" set "ADB=C:\Program Files\Netease\MuMu Player 12\shell\adb.exe"
if "%ADB%"=="" if exist "D:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe" set "ADB=D:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe"
if "%ADB%"=="" for /f "delims=" %%i in ('where adb 2^>nul') do if not defined ADB set "ADB=%%i"
if "%ADB%"=="" (
    echo [错误] 找不到 adb。请确认本文件与 config.toml 同目录、且已填 adb 路径。
    pause
    exit /b 1
)

echo 使用 adb：%ADB%
echo 请确认医考帮已停在出问题的题目页，正在抓取...
call "%ADB%" shell uiautomator dump /sdcard/yk_ui.xml >nul 2>&1
call "%ADB%" exec-out cat /sdcard/yk_ui.xml > "界面XML.txt" 2>nul
call "%ADB%" exec-out screencap -p > "屏幕截图.png" 2>nul
if exist "界面XML.txt" (
    for %%s in ("界面XML.txt") do echo 界面XML.txt 已生成，大小 %%~zs 字节
) else (
    echo [失败] 没生成 界面XML.txt，请把窗口报错发回。
)
echo 完成！请把「界面XML.txt」和「屏幕截图.png」发给作者。
pause
