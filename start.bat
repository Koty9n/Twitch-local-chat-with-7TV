@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo  Not installed yet. Run install.bat first.
  pause
  exit /b 1
)
rem Twitch chat 7TV. A .bat file cannot carry an icon: use the shortcut "Twitch chat 7TV" (made by install.bat) for the logo.
rem pythonw = no console window. The program window opens by itself; log is inside it.
start "" ".venv\Scripts\pythonw.exe" server.py %*
exit /b 0
