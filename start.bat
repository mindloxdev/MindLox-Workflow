@echo off
REM Starts the API and the web app in their own windows, then opens the browser.
REM Double-click this file, or run  start.bat  from a terminal.
cd /d "%~dp0"

if not exist "backend\.venv\Scripts\python.exe" (
  echo Backend is not set up yet. Run this once:
  echo     cd backend
  echo     python -m venv .venv
  echo     .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
  echo     .venv\Scripts\python.exe seed.py --samples
  pause
  exit /b 1
)

if not exist "frontend\node_modules" (
  echo Frontend is not set up yet. Run this once:
  echo     cd frontend
  echo     npm install
  pause
  exit /b 1
)

echo Starting the API on port 8000...
start "Dispatch API" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

echo Starting the web app on port 5173...
start "Dispatch Web" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Two windows have opened. Close either one to stop that half.
echo Waiting for the servers to come up...
timeout /t 6 /nobreak >nul
start "" http://localhost:5173
echo.
echo   Web  http://localhost:5173
echo   API  http://localhost:8000/docs
echo.
