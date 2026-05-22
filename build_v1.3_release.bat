@echo off
chcp 65001 >nul
cd /d "F:\项目\灵枢"
powershell.exe -ExecutionPolicy Bypass -File "packaging\build_first_exe_fast.ps1" -Version "v1.3" -ReuseRuntimeFrom "v1.3预览版"
echo.
echo Exit code: %ERRORLEVEL%
