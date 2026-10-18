@echo off
cd /d "%~dp0"
py -3.12 -m venv .venv
if errorlevel 1 py -m venv .venv
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Setup failed on Python dependencies.
  pause
  exit /b 1
)

if not exist "frontend\dist\index.html" (
  if exist "frontend\package.json" (
    echo Building React frontend studio...
    cd frontend
    call npm ci
    if errorlevel 1 exit /b 1
    call npm run build
    if errorlevel 1 exit /b 1
    cd ..
  )
)
echo.
echo Setup complete. Double-click run_app.bat.
pause
