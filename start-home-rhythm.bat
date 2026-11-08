@echo off
REM Home Rhythm: double-click to start. First run creates .venv and installs packages.
cd /d %~dp0
if not exist .venv (
  echo Creating virtual environment...
  py -3 -m venv .venv || python -m venv .venv
)
.venv\Scripts\python -m pip install -q -r requirements.txt
.venv\Scripts\python -m homerhythm run --port 8765
pause
