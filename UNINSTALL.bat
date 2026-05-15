@echo off
REM =====================================================================
REM   KiBridge - one-click uninstall for Windows.
REM =====================================================================

setlocal

set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%scripts\uninstall_plugin_windows.ps1

if not exist "%PS_SCRIPT%" (
    echo ERROR: uninstall script not found: %PS_SCRIPT%
    pause
    exit /b 1
)

echo.
echo  ====================================================================
echo    KiBridge uninstaller
echo  ====================================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

set EXITCODE=%ERRORLEVEL%
echo.
echo  Done. Restart KiCad if it was open.
echo.
pause
endlocal
exit /b %EXITCODE%
