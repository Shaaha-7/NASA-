@echo off
REM Download the Jezero datasets (about 2 GB with the HiRISE DTM) and build the region.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python backend\scripts\fetch_data.py --all
python backend\scripts\prepare_data.py jezero
pause
