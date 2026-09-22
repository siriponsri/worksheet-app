@echo off
chcp 65001 >nul
setlocal EnableExtensions
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

where pnpm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] pnpm is required for frontend development.
  echo Install Node.js, then enable Corepack and run this file again.
  pause
  exit /b 1
)

if not exist "%APP_DIR%node_modules" (
  echo [INFO] Installing frontend dependencies...
  pnpm install --frozen-lockfile
  if errorlevel 1 exit /b 1
)

echo Starting Vite at http://127.0.0.1:5173
pnpm dev --host 127.0.0.1
