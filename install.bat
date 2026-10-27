@echo off
setlocal
cd /d "%~dp0"
title Twitch chat 7TV - install
echo.
echo  === Twitch chat 7TV: install ===
echo.

rem --- find a working Python 3.9+ ---
set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1
if not errorlevel 1 set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(sys.version_info < (3, 9))" >nul 2>&1
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo  Python 3.9 or newer was not found.
  echo  Opening the download page. During setup tick "Add python.exe to PATH",
  echo  then run install.bat again.
  start "" "https://www.python.org/downloads/windows/"
  echo.
  pause
  exit /b 1
)
echo  Python found: %PY%

rem --- virtual environment ---
if not exist ".venv\Scripts\python.exe" (
  echo  Creating environment...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)

echo  Installing dependencies...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto :fail

rem --- desktop shortcut ---
echo  Creating shortcuts (desktop and program folder)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $w=New-Object -ComObject WScript.Shell; foreach($p in @(($d+'\Twitch chat 7TV.lnk'),('%~dp0Twitch chat 7TV.lnk'))){ $s=$w.CreateShortcut($p); $s.TargetPath='%~dp0.venv\Scripts\pythonw.exe'; $s.Arguments='server.py'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0icon.ico'; $s.Description='Twitch chat 7TV'; $s.Save() }" >nul 2>&1

echo.
echo  Done. Starting the app...
echo.
start "" "%~dp0start.bat"
timeout /t 3 >nul
exit /b 0

:fail
echo.
echo  Install failed. Check your internet connection and try again.
echo.
pause
exit /b 1
