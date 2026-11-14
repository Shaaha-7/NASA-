@echo off
REM Start MarsPath on http://localhost:8000  (optional keys go in local_keys.bat)
cd /d "%~dp0"
call .venv\Scripts\activate.bat
if exist local_keys.bat call local_keys.bat
REM Keys: put them in local_keys.bat (git-ignored). Example lines:
REM   set NASA_API_KEY=your_key_here
REM   set ANTHROPIC_API_KEY=your_key_here
start "" http://localhost:8000/app/
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
pause
