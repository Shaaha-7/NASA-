@echo off
REM Same as run.bat but the backend never touches the network: rehearse the Wi-Fi-off demo.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
set MARSPATH_OFFLINE=1
start "" http://localhost:8000/app/
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
pause
