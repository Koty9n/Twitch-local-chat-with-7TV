@echo off
rem Closes the app completely (same as the Exit button in the program window).
powershell -NoProfile -Command "try { Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8787/api/quit | Out-Null; 'Closed.' } catch { 'The app is not running.' }"
timeout /t 2 >nul
