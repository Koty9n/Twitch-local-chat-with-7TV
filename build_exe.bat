@echo off
setlocal
cd /d "%~dp0"
title Twitch chat 7TV - build exe
if not exist ".venv\Scripts\python.exe" (
  echo  Run install.bat first.
  pause
  exit /b 1
)
echo  Installing PyInstaller...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q pyinstaller
if errorlevel 1 goto :fail
echo  Building TwitchChat7TV.exe (1-2 minutes)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --noconsole --hidden-import pystray._win32 --icon icon.ico --name TwitchChat7TV ^
  --add-data "overlay.html;." --add-data "theme.css;." --add-data "theme.js;." --add-data "icon.ico;." --add-data "icon.png;." --add-data "app.html;." --add-data "dock.html;." --add-data "quick.js;." --add-data "editor.html;." --add-data "bubble.js;." --add-data "bubble.css;." server.py
if errorlevel 1 goto :fail
echo.
echo  Done: dist\TwitchChat7TV.exe
echo  Copy it anywhere. The "data" folder (settings, skins, fonts, emotes)
echo  will be created next to the exe.
echo.
pause
exit /b 0

:fail
echo.
echo  Build failed.
pause
exit /b 1
