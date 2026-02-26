@echo off
title Twitch Viewer Bot - Setup
color 0A
echo.
echo  ============================================
echo    Twitch Viewer Bot - One-Click Setup
echo  ============================================
echo.

REM ── 1. Check Python ────────────────────────────
echo [1/4] Checking for Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [!] Python is NOT installed or not in PATH.
    echo.
    echo  Downloading Python 3.11 installer...
    echo  IMPORTANT: When the installer opens, CHECK "Add Python to PATH"!
    echo.
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"
    echo  Opening Python installer...
    start /wait %TEMP%\python_installer.exe InstallAllUsers=0 PrependPath=1 Include_test=0
    echo.
    echo  [OK] Python installer finished.
    echo  Please CLOSE this window and REOPEN setup.bat so PATH updates take effect.
    pause
    exit /b
) else (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PY_VER=%%i
    echo  [OK] Found: %PY_VER%
)

REM ── 2. Check Google Chrome ─────────────────────
echo.
echo [2/4] Checking for Google Chrome...
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    echo  [OK] Chrome found.
) else if exist "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe" (
    echo  [OK] Chrome found (x86^).
) else (
    echo.
    echo  [!] Google Chrome is NOT installed.
    echo  Downloading Chrome installer...
    powershell -Command "Invoke-WebRequest -Uri 'https://dl.google.com/chrome/install/latest/chrome_installer.exe' -OutFile '%TEMP%\chrome_installer.exe'"
    echo  Opening Chrome installer...
    start /wait %TEMP%\chrome_installer.exe /silent /install
    echo  [OK] Chrome installed.
)

REM ── 3. Install pip dependencies ────────────────
echo.
echo [3/4] Installing Python packages...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo  [!] Some packages may have failed. Check messages above.
) else (
    echo  [OK] All packages installed.
)

REM ── 4. Done ────────────────────────────────────
echo.
echo  ============================================
echo    Setup complete! Launching the GUI...
echo  ============================================
echo.
timeout /t 2 >nul

python gui_launcher.py
pause
