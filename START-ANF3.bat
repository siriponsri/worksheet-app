@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

rem ===========================================================================
rem  ANF3 Laboratory Records - the one file to double-click
rem ---------------------------------------------------------------------------
rem  The share drive is the release master. Each PC runs its own copy under
rem  %LOCALAPPDATA%, so the Python environment, port file, audit log and output
rem  files are never shared by several laboratory PCs at once.
rem ===========================================================================

title ANF3 Laboratory Records
set "APP_DIR=%~dp0"
rem The directory this launcher lives in is the release master / project share.
rem Pass it to the server so controlled documents and logs land on the share
rem regardless of whether this PC later runs from a local copy.
set "SHARE_ROOT=%~dp0"
set "LOCAL_DIR=%LOCALAPPDATA%\ANF3-Laboratory-Records\"
set "LOCK_HELD="
set "FOUND="

rem /here is an owner/developer escape hatch. It still uses the local copy;
rem running the server from a UNC path would put the venv back on the share.
rem Developer mode must explicitly name the durable shared storage root so the
rem local repo is never silently treated as controlled storage.
if /i "%~1"=="/here" (
  if not defined ANF3_PROJECT_SHARE (
    if "%~2"=="" (
      echo.
      echo [ERROR] /here developer mode requires ANF3_PROJECT_SHARE.
      echo        Set it before running, or pass the share root as the second argument:
      echo          set "ANF3_PROJECT_SHARE=\\server\ANF3\worksheet"
      echo          START-ANF3.bat /here
      echo        or:
      echo          START-ANF3.bat /here "\\server\ANF3\worksheet"
      pause
      exit /b 1
    )
    set "ANF3_PROJECT_SHARE=%~2"
  )
  set "APP_DIR=%LOCAL_DIR%"
  goto :run_here
)
if /i "%APP_DIR%"=="%LOCAL_DIR%" goto :run_here

echo.
echo ANF3 Laboratory Records
echo   Please wait while ANF3 prepares this PC. Keep this window open
echo   while using the application; it opens your browser automatically.
echo   Master copy : %APP_DIR%
echo   This PC     : %LOCAL_DIR%
echo.

rem A disconnected or incomplete share must not silently turn into a server
rem started from the UNC path. A known-good local copy may still be used.
if not exist "%APP_DIR%VERSION.txt" (
  echo [ERROR] The ANF3 share-drive release cannot be read.
  if exist "%LOCAL_DIR%server\pdf_server.py" (
    echo [INFO] Using the existing local copy. Reconnect the share and retry
    echo        later to receive release updates.
    set "APP_DIR=%LOCAL_DIR%"
    goto :run_here
  )
  echo        Check the network connection and the share-drive path.
  pause
  exit /b 1
)

call :read_version "%APP_DIR%VERSION.txt" MASTER_VERSION
call :read_version "%LOCAL_DIR%VERSION.txt" LOCAL_VERSION

rem Reuse a healthy local service before considering a refresh. Overwriting a
rem workspace underneath a running Flask/Word process can produce a mixed
rem release, so an update waits until that service has stopped.
call :find_server "%LOCAL_DIR%"
if defined FOUND (
  if not "!MASTER_VERSION!"=="!LOCAL_VERSION!" (
    echo [INFO] Release !MASTER_VERSION! is ready, but the current local
    echo        service is still using !LOCAL_VERSION!.
    echo        The running service is being reused safely. Close it and
    echo        double-click START-ANF3.bat again to apply the update.
  ) else (
    echo [INFO] ANF3 is already running on port !FOUND!.
  )
  call :check_server_converter
  if errorlevel 1 goto :converter_missing
  goto :open_server
)

if not exist "%LOCAL_DIR%server\pdf_server.py" goto :copy_down
if not "!MASTER_VERSION!"=="!LOCAL_VERSION!" goto :copy_down
goto :hand_over

rem ---------------------------------------------------------------------------
rem Copy the release to this PC. The launch lock also covers setup and server
rem startup, so two people double-clicking at the same time cannot mirror or
rem rebuild the same local workspace concurrently.
:copy_down
call :acquire_lock
if errorlevel 1 goto :concurrent_launch

call :recorded_port_busy "%LOCAL_DIR%"
if errorlevel 1 goto :busy_server

echo [1/2] Copying the release to this PC...
robocopy "%APP_DIR%." "%LOCAL_DIR%." /MIR /NFL /NDL /NJH /NJS /NP /R:1 /W:1 ^
  /XD ".venv" "node_modules" ".git" ".uv-cache" ".agent-bus" "output" "pdfs" "words" "release" "shots" "__pycache__" ".anf3-launch.lock" ^
  /XF ".anf3-port" "activity-log.jsonl" "log-forward.json" "OVERNIGHT_LUNA.md" "luna-overnight.log"
if errorlevel 8 (
  call :release_lock
  echo.
  echo [ERROR] The release could not be copied to:
  echo         %LOCAL_DIR%
  echo        Check that this PC can write to its local AppData folder and
  echo        that the share is online, then try again.
  pause
  exit /b 1
)
echo       Copy complete.
set "APP_DIR=%LOCAL_DIR%"
goto :run_here_locked

:hand_over
set "APP_DIR=%LOCAL_DIR%"
goto :run_here

rem ---------------------------------------------------------------------------
rem Local execution path. A healthy service is reused; otherwise acquire the
rem lock, validate the package, prepare Python, start Flask and wait for its
rem status endpoint before opening the browser.
:run_here
call :find_server "%APP_DIR%"
if defined FOUND goto :open_server

call :recorded_port_busy "%APP_DIR%"
if errorlevel 1 goto :busy_server

call :acquire_lock
if errorlevel 1 goto :concurrent_launch
goto :run_here_locked

:run_here_locked
call :preflight "%APP_DIR%"
if errorlevel 1 goto :locked_failure

call :check_converter
if errorlevel 1 goto :converter_missing

if not exist "%APP_DIR%.venv\Scripts\python.exe" (
  echo [2/2] Setting up the Python environment on this PC ^(one time^)...
  set "ANF3_CALLED_BY_LAUNCHER=1"
  call "%APP_DIR%INSTALL.bat"
  set "ANF3_CALLED_BY_LAUNCHER="
  if errorlevel 1 goto :setup_failed
) else (
  echo [2/2] Starting.
)

echo.
rem Normal and disconnected-share paths use the original release directory as
rem the durable root. /here developer mode must have set ANF3_PROJECT_SHARE
rem explicitly before reaching this point.
if not defined ANF3_PROJECT_SHARE set "ANF3_PROJECT_SHARE=%SHARE_ROOT%"
echo [INFO] Starting the local ANF3 service...
echo          Project share: %ANF3_PROJECT_SHARE%
set "ANF3_NO_BROWSER=1"
start "ANF3 Local Server" /min "%APP_DIR%START-SERVER.bat"
set "ANF3_NO_BROWSER="
call :wait_for_server
set "WAIT_CODE=%errorlevel%"
if "%WAIT_CODE%"=="0" (
  call :check_server_converter
  if errorlevel 1 set "WAIT_CODE=2"
)
call :release_lock

if "%WAIT_CODE%"=="2" (
  echo.
  echo [ERROR] The server started, but no Word or LibreOffice PDF converter
  echo        is available. Install Office support and run this again.
  pause
  exit /b 1
)
if not "%WAIT_CODE%"=="0" (
  echo.
  echo [ERROR] The local ANF3 service did not answer at /api/status.
  echo        Check the server window for the exact Python or port error.
  pause
  exit /b 1
)
goto :open_server

rem ---------------------------------------------------------------------------
:open_server
echo [INFO] Opening ANF3 at http://127.0.0.1:%FOUND%
start "" "http://127.0.0.1:%FOUND%"
exit /b 0

:locked_failure
call :release_lock
pause
exit /b 1

:setup_failed
call :release_lock
echo.
echo [ERROR] Python setup did not finish. Run INSTALL.bat again after checking
echo        that this folder is writable and the PC can reach the internet.
pause
exit /b 1

:converter_missing
call :release_lock
echo.
echo [ERROR] No supported DOCX-to-PDF converter was found on this PC.
echo        Install Microsoft Word and run INSTALL-MSOFFICE-SUPPORT.bat,
echo        or install LibreOffice, then run START-ANF3.bat again.
pause
exit /b 1

:busy_server
call :release_lock
echo.
echo [ERROR] A process is using the ANF3 port recorded for this PC, but it is
echo        not answering as ANF3. Close that process or restart the PC, then
echo        try again. No files were refreshed.
pause
exit /b 1

:concurrent_launch
echo [INFO] Another ANF3 launch is preparing this PC. Waiting briefly...
for /l %%N in (1,1,15) do (
  call :find_server "%LOCAL_DIR%"
  if defined FOUND goto :open_server
  timeout /t 2 /nobreak >nul
)
echo.
echo [ERROR] The other launch did not finish within 30 seconds.
echo        Try START-ANF3.bat again after it finishes.
pause
exit /b 1

rem ---------------------------------------------------------------------------
rem Release preflight. Controlled templates are supplied with the share package;
rem a public source checkout without them must fail clearly before Flask starts.
:preflight
set "CHECK_DIR=%~1"
set "PREFLIGHT_OK=1"
for %%F in ("dist\index.html" "server\pdf_server.py" "server\requirements.txt" "START-SERVER.bat" "INSTALL.bat" "config.json" "templates\pw-prw-template.docx" "templates\wfi-pus-template.docx" "templates\ca-template.docx" "templates\em-template.docx" "templates\cv-contact-template.docx") do (
  if not exist "%CHECK_DIR%%%~F" (
    echo [ERROR] Release file is missing: %CHECK_DIR%%%~F
    set "PREFLIGHT_OK=0"
  )
)
if "%PREFLIGHT_OK%"=="0" goto :preflight_failed

powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $cfg=Get-Content -Raw -LiteralPath '%CHECK_DIR%config.json' | ConvertFrom-Json; $forbidden='ANF3'+'_SYNC_'+'TOKEN'; foreach($key in 'waterReadUrl','airReadUrl','cvReadUrl'){ $value=[string]$cfg.$key; if($value -and $value -notmatch '^https://script[.]google[.]com/macros/s/[A-Za-z0-9_-]+/exec$'){ throw ('config.json '+$key+' must be a public Google Apps Script /exec URL or blank') }; if($value -match $forbidden -or $value -match 'token'){ throw ('config.json '+$key+' contains a forbidden token') } }; exit 0" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] config.json is invalid or contains a non-public endpoint.
  echo        Use blank values or public Google Apps Script URLs ending in /exec.
  goto :preflight_failed
)
exit /b 0

:preflight_failed
echo.
echo [ERROR] This ANF3 release is incomplete. Ask the owner to publish dist,
echo        config.json and all five controlled DOCX templates.
exit /b 1

rem ---------------------------------------------------------------------------
rem Detect a converter without launching the Flask service. The server performs
rem its own detection again, so a newly installed Office/LibreOffice is picked
rem up after the next launch.
:check_converter
powershell -NoProfile -NonInteractive -Command "$word=(Test-Path 'HKCR:\Word.Application') -or [bool](Get-Command 'winword.exe' -ErrorAction SilentlyContinue); $lo=[bool](Get-Command 'soffice.exe' -ErrorAction SilentlyContinue); if(-not $lo){ $lo=(Test-Path 'C:\Program Files\LibreOffice\program\soffice.exe') -or (Test-Path 'C:\Program Files (x86)\LibreOffice\program\soffice.exe') }; if($word -or $lo){ exit 0 }; exit 1" >nul 2>&1
exit /b %errorlevel%

rem ---------------------------------------------------------------------------
rem Find a healthy ANF3 service on the local copy's recorded port or the full
rem range used by pdf_server.py when 8000 is busy.
:find_server
set "FOUND="
set "STATE_DIR=%~1"
rem Use one PowerShell process for the whole range. The former nested loop
rem launched PowerShell + an HTTP timeout once per port, which looked frozen
rem for tens of seconds before the server was even started.
for /f "usebackq delims=" %%P in (`powershell -NoProfile -NonInteractive -Command "$ports=@(); $path='%STATE_DIR%.anf3-port'; if(Test-Path -LiteralPath $path){$saved=(Get-Content -LiteralPath $path -TotalCount 1).Trim(); if($saved -match '^\d+$'){$ports+=[int]$saved}}; $ports+=8000..8039; foreach($port in ($ports|Select-Object -Unique)){ $client=New-Object Net.Sockets.TcpClient; try{$task=$client.ConnectAsync('127.0.0.1',[int]$port); if(-not $task.Wait(50) -or -not $client.Connected){continue}; try{$reply=Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 ('http://127.0.0.1:'+$port+'/api/status'); $body=$reply.Content|ConvertFrom-Json; if($reply.StatusCode -eq 200 -and $body.status -eq 'running' -and $body.converterAvailable -eq $true -and $null -ne $body.folders){Write-Output $port; break}}catch{}}finally{$client.Dispose()}}"`) do set "FOUND=%%P"
exit /b 0

rem A recorded port that is occupied but not ANF3 is a stop condition for a
rem refresh. It avoids copying files while a stale/foreign process may hold a
rem file or keep the user pointed at the wrong service.
:recorded_port_busy
set "RECORDED="
if not exist "%~1.anf3-port" exit /b 0
set /p RECORDED=<"%~1.anf3-port"
if not defined RECORDED exit /b 0
call :tcp_port_busy !RECORDED!
if errorlevel 1 exit /b 0
exit /b 1

:tcp_port_busy
powershell -NoProfile -NonInteractive -Command "$client=New-Object Net.Sockets.TcpClient; try { $task=$client.ConnectAsync('127.0.0.1',[int]('%1')); if(-not $task.Wait(500)){ exit 1 }; if($client.Connected){ exit 0 }; exit 1 } catch { exit 1 } finally { $client.Dispose() }" >nul 2>&1
exit /b %errorlevel%

rem ---------------------------------------------------------------------------
:wait_for_server
set "FOUND="
for /l %%N in (1,1,30) do (
  call :find_server "%APP_DIR%"
  if defined FOUND goto :server_ready
  timeout /t 1 /nobreak >nul
)
exit /b 1

:server_ready
exit /b 0

:check_server_converter
powershell -NoProfile -NonInteractive -Command "try { $r=Invoke-RestMethod -TimeoutSec 2 'http://127.0.0.1:%FOUND%/api/status'; if($r.status -eq 'running' -and $r.converterAvailable -eq $true -and $null -ne $r.folders){ exit 0 }; exit 1 } catch { exit 1 }" >nul 2>&1
exit /b %errorlevel%

rem ---------------------------------------------------------------------------
:acquire_lock
if not exist "%LOCAL_DIR%" mkdir "%LOCAL_DIR%" >nul 2>&1
mkdir "%LOCAL_DIR%.anf3-launch.lock" >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -NonInteractive -Command "$owner=Join-Path '%LOCAL_DIR%.anf3-launch.lock' 'owner.txt'; if(-not (Test-Path -LiteralPath $owner)){exit 1}; $text=(Get-Content -LiteralPath $owner -TotalCount 1); $match=[regex]::Match($text,'^([0-9]+)\|'); if(-not $match.Success){exit 0}; $ownerPid=[int]$match.Groups[1].Value; $p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$ownerPid) -ErrorAction SilentlyContinue; if($p -and $p.Name -ieq 'cmd.exe' -and $p.CommandLine -match '(?i)START-ANF3[.]bat'){exit 1}; exit 0" >nul 2>&1
  if errorlevel 1 exit /b 1
  rmdir /s /q "%LOCAL_DIR%.anf3-launch.lock" >nul 2>&1
  mkdir "%LOCAL_DIR%.anf3-launch.lock" >nul 2>&1
  if errorlevel 1 exit /b 1
)
powershell -NoProfile -NonInteractive -Command "$self=Get-CimInstance Win32_Process -Filter ('ProcessId='+$PID) -ErrorAction SilentlyContinue; if($self){$self.ParentProcessId}else{0}" >"%LOCAL_DIR%.anf3-launch.lock\owner.txt" 2>nul
for /f "usebackq delims=" %%P in ("%LOCAL_DIR%.anf3-launch.lock\owner.txt") do >"%LOCAL_DIR%.anf3-launch.lock\owner.txt.tmp" echo %%P^|%COMPUTERNAME%\%USERNAME% %DATE% %TIME%
move /y "%LOCAL_DIR%.anf3-launch.lock\owner.txt.tmp" "%LOCAL_DIR%.anf3-launch.lock\owner.txt" >nul 2>&1
set "LOCK_HELD=1"
exit /b 0

:release_lock
if not defined LOCK_HELD exit /b 0
rmdir /s /q "%LOCAL_DIR%.anf3-launch.lock" >nul 2>&1
set "LOCK_HELD="
exit /b 0

rem ---------------------------------------------------------------------------
:read_version
set "%~2=none"
if exist "%~1" (
  for /f "usebackq delims=" %%V in ("%~1") do (
    set "%~2=%%V"
    goto :eof
  )
)
goto :eof

rem /api/status is this application's own route, so another process on the
rem port is not mistaken for ANF3.
:probe
powershell -NoProfile -NonInteractive -Command "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 'http://127.0.0.1:%1/api/status'; if($r.StatusCode -eq 200){ exit 0 }; exit 1 } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 set "FOUND=%1"
exit /b 0
