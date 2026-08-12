@echo off
chcp 65001 >nul
title 会议室提醒助手 - Windows 一键部署
echo ============================================================
echo    🏢 会议室提醒助手 - Windows 一键部署
echo ============================================================
echo.
echo 本脚本将：
echo   1. 安装依赖 (pyyaml, python-dateutil, pywin32)
echo   2. 创建3个定时任务:
echo      - 22:30  晚间预告 → 微信推送
echo      - 23:50  临开抢   → 微信推送
echo      - 00:00  每日检查 → 桌面提醒
echo.
echo 目录: %~dp0
echo.

REM ---- 1. 检查Python ----
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ 未找到Python！请先安装Python 3并勾选"Add to PATH"
    echo    下载: https://www.python.org/downloads/
    pause
    exit /b 1
)
echo ✅ Python: 
python --version

REM ---- 2. 安装依赖 ----
echo.
echo 正在安装依赖...
python -m pip install pyyaml python-dateutil pywin32 --quiet
if %errorlevel% neq 0 (
    echo ⚠️ 依赖安装可能失败，请手动运行:
    echo   python -m pip install pyyaml python-dateutil pywin32
)
echo ✅ 依赖安装完成

REM ---- 3. 创建定时任务 ----
echo.
echo 正在创建定时任务(需要管理员权限)...请确认UAC弹窗

schtasks /Create /F /TN "MeetingReminder_Evening" /TR "\"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe\" -NoProfile -Command \"cd '%cd%'; python main.py --reminder evening\"" /SC DAILY /ST 22:30 >nul 2>&1
if %errorlevel% equ 0 ( echo ✅ 已创建: 22:30 晚间预告 ) else ( echo ⚠️ 22:30任务创建失败，请用管理员身份运行本脚本 )

schtasks /Create /F /TN "MeetingReminder_Final" /TR "\"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe\" -NoProfile -Command \"cd '%cd%'; python main.py --reminder final\"" /SC DAILY /ST 23:50 >nul 2>&1
if %errorlevel% equ 0 ( echo ✅ 已创建: 23:50 临开抢 ) else ( echo ⚠️ 23:50任务创建失败 )

schtasks /Create /F /TN "MeetingReminder_Daily" /TR "\"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe\" -NoProfile -Command \"cd '%cd%'; python main.py --today\"" /SC DAILY /ST 00:00 >nul 2>&1
if %errorlevel% equ 0 ( echo ✅ 已创建: 00:00 每日检查 ) else ( echo ⚠️ 00:00任务创建失败 )

echo.
echo ============================================================
echo    完成！现在可以:
echo    1. 测试微信提醒:    python main.py --reminder final
echo    2. 查会议室状态:    python check_rooms.py --date 8/19 --start 11:00 --end 12:00
echo    3. 查看定时任务:    控制面板→任务计划程序→MeetingReminder_*
echo ============================================================
pause
