@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Twitch chat 7TV - update
echo.
echo  === Twitch chat 7TV: update from zip ===
echo  Settings, skins, fonts and the emote cache (the data folder) are NOT touched.
echo.

rem --- choose the zip (dragging a zip onto this file also works) ---
set "UPD_ZIP=%~1"
if not defined UPD_ZIP call :pick
if not defined UPD_ZIP goto :nofile
if not exist "%UPD_ZIP%" goto :nofile
echo  Update file: %UPD_ZIP%
echo.

rem --- is the app running? ---
set "RUNNING=0"
for /f %%N in ('powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -and $_.CommandLine -like '*server.py*') -or $_.Name -eq 'TwitchChat7TV.exe' -or $_.Name -eq 'OBSChat.exe' } | ForEach-Object { $_.ProcessId }"') do set "RUNNING=1"
set "WAS_RUNNING=0"
if "%RUNNING%"=="1" (
  if /i not "%~2"=="/y" (
    choice /c YN /m "The app is running. Close it and continue"
    if errorlevel 2 goto :cancel
  )
  powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -like 'python*' -and $_.CommandLine -like '*server.py*') -or $_.Name -eq 'TwitchChat7TV.exe' -or $_.Name -eq 'OBSChat.exe' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1
  set "WAS_RUNNING=1"
  timeout /t 2 >nul
)

rem --- unpack to a temp folder ---
set "UPD_TMP=%TEMP%\obschat_upd_%RANDOM%%RANDOM%"
echo  Unpacking...
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Expand-Archive -LiteralPath $env:UPD_ZIP -DestinationPath $env:UPD_TMP -Force } catch { exit 1 }"
if errorlevel 1 goto :badzip

set "SRC="
for /f "usebackq delims=" %%D in (`powershell -NoProfile -Command "Get-ChildItem -LiteralPath $env:UPD_TMP -Recurse -Filter server.py | Select-Object -First 1 -ExpandProperty DirectoryName"`) do set "SRC=%%D"
if not defined SRC goto :badzip
if not exist "%SRC%\dock.html" goto :badzip
if not exist "%SRC%\overlay.html" goto :badzip

rem --- back up the current program files (not data) ---
for /f %%T in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%T"
set "BK=%~dp0_backup\%STAMP%"
echo  Backing up current files to _backup\%STAMP% ...
robocopy "%~dp0." "%BK%" *.py *.html *.js *.css *.bat *.txt *.md /NFL /NDL /NJH /NJS /NP >nul

rem --- shortcuts are refreshed by install.bat; icon.ico comes with the files
rem --- copy new files over, skipping data, the environment and backups ---
echo  Installing new files...
robocopy "%SRC%" "%~dp0." /E /XD data .venv _backup __pycache__ /XF update.bat /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 goto :copyfail

rem --- dependencies (quick when nothing changed) ---
if exist ".venv\Scripts\python.exe" (
  echo  Checking dependencies...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 echo  Warning: could not update dependencies. Check your internet connection.
)

echo.
echo  Update installed. The previous version is in _backup\%STAMP%
if "%WAS_RUNNING%"=="1" (
  echo  Starting the app again...
  start "" "%~dp0start.bat"
)
echo.
timeout /t 4 >nul

rem --- update.bat updates itself last (this line is already read, so it is safe) ---
if exist "%SRC%\update.bat" (
  copy /y "%SRC%\update.bat" "%~f0" >nul & rmdir /s /q "%UPD_TMP%" & exit /b 0
)
rmdir /s /q "%UPD_TMP%" >nul 2>&1
exit /b 0

:pick
for /f "usebackq delims=" %%F in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $d=New-Object System.Windows.Forms.OpenFileDialog; $d.Filter='ZIP files|*.zip'; $d.Title='Select the update zip'; if($d.ShowDialog() -eq 'OK'){$d.FileName}"`) do set "UPD_ZIP=%%F"
exit /b

:nofile
echo  No zip file selected. Nothing was changed.
echo.
pause
exit /b 1

:cancel
echo  Cancelled. Nothing was changed.
echo.
pause
exit /b 1

:badzip
echo.
echo  This zip does not look like an Twitch chat 7TV update
echo  (server.py, dock.html and overlay.html were not found). Nothing was changed.
if defined UPD_TMP rmdir /s /q "%UPD_TMP%" >nul 2>&1
echo.
pause
exit /b 1

:copyfail
echo.
echo  Copying failed. Your previous files are in _backup\%STAMP%
if defined UPD_TMP rmdir /s /q "%UPD_TMP%" >nul 2>&1
echo.
pause
exit /b 1
