@echo off
REM =====================================================================
REM   KiBridge - one-click install for Windows.
REM   Wraps scripts\install_plugin_windows.ps1 so you can just double-click.
REM =====================================================================

setlocal

set SCRIPT_DIR=%~dp0
set PS_SCRIPT=%SCRIPT_DIR%scripts\install_plugin_windows.ps1

if not exist "%PS_SCRIPT%" (
    echo.
    echo ERROR: install script not found:
    echo   %PS_SCRIPT%
    echo.
    echo Make sure you extracted the full repo, not just this BAT file.
    pause
    exit /b 1
)

echo.
echo  ====================================================================
echo    KiBridge installer
echo    PSS Tools  -  github.com/IgmarMelis/kibridge
echo  ====================================================================
echo.
echo  This will install the KiBridge plugin into your KiCad user folder.
echo  Existing installs of KiBridge (or its predecessor pss_kicad_agent)
echo  will be removed first.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS_SCRIPT%"

set EXITCODE=%ERRORLEVEL%
echo.
if %EXITCODE% EQU 0 (
    echo  Done. In KiCad:  Tools - External Plugins - Refresh Plugins
) else (
    echo  Install finished with errors (exit code %EXITCODE%).
)
echo.
pause
endlocal
exit /b %EXITCODE%
