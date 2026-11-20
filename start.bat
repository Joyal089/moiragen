@echo off
rem Double-click this file to wake Moiragen and open his viewer.
rem Close this window (or press Ctrl+C) to let him sleep.

cd /d "%~dp0"

rem Make sure the Ollama app (his brain) is running.
tasklist /FI "IMAGENAME eq ollama app.exe" | find /I "ollama app.exe" >nul
if errorlevel 1 (
    echo Starting Ollama...
    start "" "%LOCALAPPDATA%\Programs\Ollama\ollama app.exe"
    timeout /t 5 /nobreak >nul
)

rem Open the viewer a few seconds after the server starts (it reconnects by itself).
start "" cmd /c "timeout /t 4 /nobreak >nul & start http://127.0.0.1:8765"

".venv\Scripts\python.exe" server.py
pause
