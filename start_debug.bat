@echo off
cd /d "%~dp0"
title Twitch chat 7TV (debug console)
if not exist ".venv\Scripts\python.exe" (
  echo  Not installed yet. Run install.bat first.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" server.py --console %*
echo.
echo  The app stopped.
pause
