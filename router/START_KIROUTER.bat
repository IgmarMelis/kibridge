@echo off
REM =====================================================================
REM   KiRouter - one-click server start for Windows.
REM =====================================================================

setlocal

set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

echo.
echo  ====================================================================
echo    KiRouter - local web app autorouter for KiCad
echo    PSS Tools  -  github.com/IgmarMelis/kibridge
echo  ====================================================================
echo.

REM Find python (prefer 'py' launcher on Windows, fall back to 'python')
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PY=py -3
) else (
    where python >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Python is not installed or not on PATH.
        echo Install Python 3.9+ from https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set PY=python
)

REM First-run dep install
if not exist "%SCRIPT_DIR%.venv\" (
    echo  First run: creating virtual environment in .venv\
    %PY% -m venv .venv
    if errorlevel 1 (
        echo ERROR: failed to create venv.
        pause
        exit /b 1
    )
)

call "%SCRIPT_DIR%.venv\Scripts\activate.bat"

REM Install/upgrade Flask quietly
pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: failed to install dependencies.
    pause
    exit /b 1
)

echo.
echo  Starting server on http://127.0.0.1:8765 ...
echo  Your browser should open automatically. Close this window to stop.
echo.

python -m kirouter

endlocal
