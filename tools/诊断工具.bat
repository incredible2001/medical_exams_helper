@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title 医考帮备考助手 - adb 诊断
rem ============================================================
rem  医考帮备考助手 - adb 环境诊断工具
rem
rem  使用方法（小白版）：
rem    1. 把本文件放到 解压目录（与 exe、config.toml 同目录）
rem    2. 先打开医考帮 App，停在一道题的页面，模拟器保持在最前
rem    3. 双击本文件，等它自动跑完（一般 30 秒内）
rem    4. 把生成的「诊断结果.txt」和「屏幕截图.png」发回给作者
rem
rem  建议跑两次对比：
rem    第一次 停在医考帮题目页；第二次 停在模拟器桌面。
rem    对比两次结果里的 7/8/9/10/12 项，能区分「uiautomator 全局坏了」
rem    还是「只在医考帮页面才崩」。
rem ============================================================
cd /d "%~dp0"
rem 放在 tools/ 里运行时，config.toml 在上级目录
if not exist "config.toml" cd ..

rem ---------- 1) 确定 adb 路径 ----------
set "ADB="
rem 优先读 config.toml 里 [adb] 的 path（自动，不用手填）
powershell -NoProfile -Command "$l=Get-Content config.toml|Where-Object{$_ -like 'path*'}|Select-Object -First 1; $p=$l -split [char]34; $p[1] | Out-File -Encoding ascii -FilePath $env:TEMP\adbpath.txt" >nul 2>nul
if exist "%TEMP%\adbpath.txt" set /p ADB=<"%TEMP%\adbpath.txt"
rem 读不到就试常见 MuMu 路径
if "%ADB%"=="" if exist "C:\Program Files\Netease\MuMu Player 12\shell\adb.exe" set "ADB=C:\Program Files\Netease\MuMu Player 12\shell\adb.exe"
if "%ADB%"=="" if exist "C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe" set "ADB=C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe"
if "%ADB%"=="" if exist "D:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe" set "ADB=D:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe"
rem 还不行就试 PATH 里的 adb
if "%ADB%"=="" for /f "delims=" %%i in ('where adb 2^>nul') do if not defined ADB set "ADB=%%i"

if "%ADB%"=="" (
    echo [错误] 自动没找到 adb。请手动编辑本文件，把 set "ADB=" 那行改成你的 adb.exe 路径，例如：
    echo     set "ADB=D:\Program Files\Netease\MuMu\nx_device\12.0\shell\adb.exe"
    echo.
    pause
    exit /b 1
)

set "OUT=诊断结果.txt"
del "%OUT%" >nul 2>&1

echo 使用 adb：%ADB%
echo 正在诊断，请稍候（若屏幕闪动属正常）...

rem ---------- 文件头 ----------
echo 医考帮备考助手 - adb 诊断结果 >> "%OUT%"
echo 时间：%date% %time% >> "%OUT%"
echo adb 路径：%ADB% >> "%OUT%"

rem ---------- 1. adb 版本 ----------
echo. >> "%OUT%"
echo ===== 1. adb 版本 ===== >> "%OUT%"
call "%ADB%" version >> "%OUT%" 2>&1

rem ---------- 2. 已连接设备 ----------
echo. >> "%OUT%"
echo ===== 2. 已连接设备 ===== >> "%OUT%"
call "%ADB%" devices -l >> "%OUT%" 2>&1

rem ---------- 3. 设备系统信息 ----------
echo. >> "%OUT%"
echo ===== 3. 设备系统信息 ===== >> "%OUT%"
call "%ADB%" shell getprop ro.build.version.release >> "%OUT%" 2>&1
call "%ADB%" shell getprop ro.build.version.sdk >> "%OUT%" 2>&1
call "%ADB%" shell getprop ro.product.model >> "%OUT%" 2>&1

rem ---------- 4. 屏幕唤醒状态 ----------
echo. >> "%OUT%"
echo ===== 4. 屏幕唤醒状态 ===== >> "%OUT%"
call "%ADB%" shell dumpsys power 2>&1 | findstr /i "Wakefulness" >> "%OUT%"

rem ---------- 5. 当前焦点窗口 ----------
echo. >> "%OUT%"
echo ===== 5. 当前焦点窗口 ===== >> "%OUT%"
call "%ADB%" shell dumpsys window windows 2>&1 | findstr /i "mCurrentFocus" >> "%OUT%"

rem ---------- 6. 当前前台应用 ----------
echo. >> "%OUT%"
echo ===== 6. 当前前台应用 ===== >> "%OUT%"
call "%ADB%" shell dumpsys activity activities 2>&1 | findstr /i "mResumedActivity" >> "%OUT%"

rem ---------- 7. uiautomator 帮助（进程本身能否启动） ----------
echo. >> "%OUT%"
echo ===== 7. uiautomator 帮助命令（进程本身能否启动） ===== >> "%OUT%"
call "%ADB%" shell uiautomator >> "%OUT%" 2>&1
echo [退出码=%errorlevel%] >> "%OUT%"

rem ---------- 8. dump 普通模式（复现） ----------
echo. >> "%OUT%"
echo ===== 8. uiautomator dump 普通模式（复现） ===== >> "%OUT%"
call "%ADB%" shell uiautomator dump /sdcard/yk_diag.xml >> "%OUT%" 2>&1
echo [退出码=%errorlevel%] >> "%OUT%"

rem ---------- 9. dump --compressed（复现） ----------
echo. >> "%OUT%"
echo ===== 9. uiautomator dump --compressed（复现） ===== >> "%OUT%"
call "%ADB%" shell uiautomator dump --compressed /sdcard/yk_diag.xml >> "%OUT%" 2>&1
echo [退出码=%errorlevel%] >> "%OUT%"

rem ---------- 10. dump 写 /dev/tty（替代路径测试） ----------
echo. >> "%OUT%"
echo ===== 10. uiautomator dump 写 /dev/tty（替代路径测试） ===== >> "%OUT%"
call "%ADB%" shell uiautomator dump /dev/tty >> "%OUT%" 2>&1
echo [退出码=%errorlevel%] >> "%OUT%"

rem ---------- 11. dump 文件是否生成 ----------
echo. >> "%OUT%"
echo ===== 11. dump 文件是否生成 ===== >> "%OUT%"
call "%ADB%" shell ls -l /sdcard/yk_diag.xml >> "%OUT%" 2>&1

rem ---------- 12. 崩溃日志 crash buffer（最关键） ----------
echo. >> "%OUT%"
echo ===== 12. 崩溃日志 crash buffer（最关键） ===== >> "%OUT%"
call "%ADB%" logcat -d -b crash >> "%OUT%" 2>&1

rem ---------- 13. 崩溃相关日志 ----------
echo. >> "%OUT%"
echo ===== 13. 崩溃相关日志（AndroidRuntime / DEBUG / libc） ===== >> "%OUT%"
call "%ADB%" logcat -d -s AndroidRuntime:E DEBUG:E libc:E uiautomator:V >> "%OUT%" 2>&1

rem ---------- 14. 内核段错误日志 ----------
echo. >> "%OUT%"
echo ===== 14. 内核段错误日志 ===== >> "%OUT%"
call "%ADB%" shell dmesg 2>&1 | findstr /i "segfault uiautomator" >> "%OUT%"

rem ---------- 15. 屏幕截图 ----------
echo. >> "%OUT%"
echo ===== 15. 屏幕截图 ===== >> "%OUT%"
call "%ADB%" exec-out screencap -p > "屏幕截图.png" 2>nul
if exist "屏幕截图.png" (
    for %%s in ("屏幕截图.png") do if %%~zs LSS 500 echo [截图只有 %%~zs 字节，可能失败] >> "%OUT%"
    echo 已保存「屏幕截图.png」 >> "%OUT%"
) else (
    echo [截图失败：未生成文件] >> "%OUT%"
)
echo ===== 诊断结束 ===== >> "%OUT%"

echo.
echo 完成！请把「诊断结果.txt」和「屏幕截图.png」发回给作者。
pause
