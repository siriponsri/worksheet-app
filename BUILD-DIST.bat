@echo off
chcp 65001 >nul
setlocal EnableExtensions

title ANF3 Laboratory Records - Rebuild the web app
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

echo.
echo ============================================
echo   Rebuilding the ANF3 web app
echo ============================================
echo.
echo   You usually do NOT need this.
echo   To change a System DB URL, edit
echo     config.json
echo   with Notepad and refresh the browser.
echo   That needs no Node, no pnpm, no rebuild.
echo.
echo   This script is only for changing the code
echo   itself, and it needs Node.js and pnpm.
echo ============================================
echo.

where node >nul 2>&1
if errorlevel 1 goto :no_node
where pnpm >nul 2>&1
if errorlevel 1 goto :no_pnpm

echo [1/2] Installing dependencies...
call pnpm install --frozen-lockfile
if errorlevel 1 goto :install_failed

echo.
echo [2/2] Building...
call pnpm build
if errorlevel 1 goto :build_failed

echo.
echo [OK] Built to dist\ — START-ANF3.bat will now serve it.
echo.
echo      Check the System DB URLs actually reached the build:
echo        node validation\validate_wiring.mjs --built
echo.
pause
exit /b 0

:no_node
echo [ERROR] Node.js is not installed on this computer.
echo.
echo   INSTALL.bat sets up Python for the PDF server only. It does not
echo   install Node, and this computer does not need Node for daily use.
echo.
echo   YOU PROBABLY DO NOT NEED TO BUILD AT ALL.
echo   To point the app at a different System DB, open
echo     %APP_DIR%config.json
echo   in Notepad, paste the /exec URL, save, and refresh the browser.
echo.
echo   If you really do need to rebuild, install Node.js LTS from
echo   https://nodejs.org/ then run:  npm install -g pnpm
echo.
pause
exit /b 1

:no_pnpm
echo [ERROR] Node.js is installed but pnpm is not.
echo.
echo   Install it with:   npm install -g pnpm
echo   Then run this file again.
echo.
echo   Or skip the build entirely: edit config.json in Notepad.
echo.
pause
exit /b 1

:install_failed
echo.
echo [ERROR] Dependency installation failed.
echo         Check that this computer can reach the internet, then retry.
echo.
pause
exit /b 1

:build_failed
echo.
echo [ERROR] The build failed. The messages above say why.
echo         dist\ has been left as it was; the app still runs.
echo.
pause
exit /b 1
