@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if not exist "%~dp0程序\python\python.exe" (
 echo 缺少内置运行环境。请先完整解压ZIP，再双击本文件。
 pause
 exit /b 2
)
"%~dp0程序\python\python.exe" -I -B -X utf8 "%~dp0程序\convert.py"
set "result=%errorlevel%"
echo.
echo 处理结束。请查看“视频输出”和“转换记录”。
pause
exit /b %result%
