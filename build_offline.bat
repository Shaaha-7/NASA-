@echo off
REM While ONLINE: cache Mars Trek tiles, space weather and the assistant documents, then zip the package.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python backend\scripts\fetch_docs.py
python backend\scripts\build_offline_package.py jezero
pause
