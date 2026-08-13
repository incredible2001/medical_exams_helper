@echo off
chcp 65001 >nul
rem ==============================================
rem  医考帮备考助手 - 打包成独立 exe（给同学用，无需装 Python）
rem  产物：dist\医考帮备考助手.exe
rem  分享时把以下文件放进同一个文件夹再压缩发给同学：
rem    医考帮备考助手.exe + config.toml + taxonomy.json + .env.example
rem ==============================================
title 医考帮备考助手 - 打包 exe
cd /d "%~dp0"

set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY where py >nul 2>nul && set "PY=py"

if defined PY goto :have_py

echo.
echo  [错误] 没找到 Python。
pause
exit /b 1

:have_py
echo 正在安装 PyInstaller...
%PY% -m pip install pyinstaller
if errorlevel 1 goto :err

echo 正在打包（约 1 到 3 分钟，请耐心等待）...
rem 用 ASCII 名打包，避免中文名在部分环境出问题，打包后再重命名
%PY% -m PyInstaller --noconfirm --onefile --windowed --name "yikao_helper" main.py
if errorlevel 1 goto :err
if exist "dist\yikao_helper.exe" (
  move /y "dist\yikao_helper.exe" "dist\医考帮备考助手.exe" >nul
  if errorlevel 1 goto :err
)

echo.
echo  打包完成！exe 在  dist\医考帮备考助手.exe
echo.
echo  分享给同学时，把以下文件放进同一个文件夹再压缩：
echo    医考帮备考助手.exe
echo    config.toml
echo    taxonomy.json
echo    .env.example （同学改成 .env 并填自己的 Key）
echo.
echo  同学用法：解压后双击 exe，点「设置」填 Key，开刷。
echo.
pause
exit /b 0

:err
echo.
echo  [失败] 打包失败，请把上方报错截图发给维护者。
pause
exit /b 1
