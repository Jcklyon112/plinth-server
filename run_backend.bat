@echo off
cd /d "%~dp0"

echo Installing dependencies...
venv\Scripts\python.exe -m pip install -r requirements.txt --quiet

echo.
echo Plinth API starting on http://localhost:8000
echo Press Ctrl+C to stop.
echo.

venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

pause
