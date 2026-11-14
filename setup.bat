@echo off
REM One-time setup: virtual environment, packages, synthetic test region, tests.
cd /d "%~dp0"
python --version || (echo Python not found. Install Python 3.11+ from python.org and tick "Add to PATH". & pause & exit /b 1)

REM If an earlier attempt left a broken .venv (pip missing), rebuild it.
if exist .venv (
  .venv\Scripts\python.exe -m pip --version >nul 2>&1 || (
    echo Existing .venv is broken - recreating it...
    rmdir /s /q .venv
  )
)
if not exist .venv python -m venv .venv
set PY=.venv\Scripts\python.exe

REM Note: we do NOT upgrade pip itself - on Windows that can fail with "file in use" and break the venv.
%PY% -m pip install --disable-pip-version-check -r requirements.txt || (echo Package install failed - see README "Troubleshooting". & pause & exit /b 1)
echo.
echo === Building the synthetic TEST region (so the app works before NASA data is downloaded)
%PY% backend\scripts\make_synthetic.py || (pause & exit /b 1)
%PY% backend\scripts\prepare_data.py synthetic || (pause & exit /b 1)
echo.
echo === Running tests
%PY% -m pytest backend\tests -q
echo.
echo Setup finished. Start the app with run.bat
pause