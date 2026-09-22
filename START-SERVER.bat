@echo off
chcp 65001 >nul
setlocal EnableExtensions

title ANF3 Laboratory Records - Local Server
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"
set "VENV_DIR=%APP_DIR%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"

rem Checking only for python.exe is not enough: a .venv that was copied, moved
rem or half-restored still has python.exe but no usable pyvenv.cfg, and the
rem launcher then hands the user a bare "No pyvenv.cfg file" and quits. Probe
rem the environment for real, and repair it once before giving up.
call :probe_env
if not defined ENV_OK (
  echo [INFO] The local Python environment is missing or broken. Repairing it...
  echo.
  call "%APP_DIR%INSTALL.bat"
  if errorlevel 1 goto :setup_failed
  call :probe_env
  if not defined ENV_OK goto :setup_failed
  echo.
)

rem Controlled Word/PDF files and the activity log belong on the central share.
rem The server uses the OS temp directory only during DOCX-to-PDF conversion.
rem START-ANF3.bat sets ANF3_PROJECT_SHARE to the share root before starting
rem this script. Do not hard-code a drive letter here.
if not defined ANF3_PROJECT_SHARE (
  echo.
  echo [ERROR] ANF3_PROJECT_SHARE is not set.
  echo        Run START-ANF3.bat from the share release, or set
  echo        ANF3_PROJECT_SHARE to the worksheet storage root first.
  pause
  exit /b 1
)
rem SHARE_ROOT from START-ANF3.bat already has a trailing backslash, so do
rem not add another one when testing the directory.
if not exist "%ANF3_PROJECT_SHARE%" (
  echo.
  echo [WARNING] The project share is not reachable:
  echo          %ANF3_PROJECT_SHARE%
  echo          Document generation and activity logging will be disabled.
  echo          Reconnect the share and restart to restore full function.
  echo.
) else (
  echo          Project share: %ANF3_PROJECT_SHARE%
)

echo.
echo ============================================
echo   ANF3 LABORATORY RECORDS v7
echo ============================================
echo   Starting the local server...
echo   The first available local port is selected automatically
echo   and the address is printed below.
echo.
echo   Keep this window open while using the app.
echo   Press Ctrl+C to stop the server.
echo ============================================
echo.

set "ANF3_HOST=127.0.0.1"
"%VENV_PY%" "%APP_DIR%server\pdf_server.py"
set "EXIT_CODE=%errorlevel%"

echo.
if not "%EXIT_CODE%"=="0" (
  echo [ERROR] The server stopped with code %EXIT_CODE%.
  echo         The port is chosen automatically, so a busy port is not the cause.
  echo         Run INSTALL.bat and try again.
) else (
  echo [INFO] Server stopped.
)
pause
exit /b %EXIT_CODE%

:setup_failed
echo.
echo ============================================
echo  [ERROR] Setup could not be completed.
echo ============================================
echo  The local Python environment at
echo    %VENV_DIR%
echo  could not be built. Try this, in order:
echo.
echo    1. Delete the .venv folder in this directory, then run INSTALL.bat
echo    2. Check that this PC can reach the internet ^(uv and pip need it^)
echo    3. Make sure this folder is not read-only or inside OneDrive sync
echo.
pause
exit /b 1

rem ---------------------------------------------------------------------------
rem Sets ENV_OK only when Python starts AND the server's dependency is present.
:probe_env
set "ENV_OK="
if not exist "%VENV_PY%" goto :eof
if not exist "%VENV_DIR%\pyvenv.cfg" goto :eof
"%VENV_PY%" -c "import flask" >nul 2>&1
if errorlevel 1 goto :eof
set "ENV_OK=1"
goto :eof
