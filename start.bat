@echo off
setlocal
cd /d "%~dp0"
title Resume Tailor

rem ---- Find Python 3.10+ -------------------------------------------------
set "PY="
where py >nul 2>nul && py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY (
  where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo  Python 3.10 or newer is not installed.
  echo.
  echo  1. Download it from https://www.python.org/downloads/
  echo  2. Run the installer and TICK "Add python.exe to PATH" on the first screen.
  echo  3. Double-click start.bat again.
  echo.
  start "" https://www.python.org/downloads/
  pause
  exit /b 1
)

rem ---- First run: create a private environment and install packages --------
if not exist ".venv\Scripts\python.exe" (
  echo  First-time setup: creating environment... this takes 1-3 minutes.
  %PY% -m venv .venv || goto :fail
  del /q ".venv\.installed" >nul 2>nul
)
if not exist ".venv\.installed" (
  echo  Installing packages...
  ".venv\Scripts\python.exe" -m pip install --upgrade pip -q
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt -q || goto :fail
  echo ok> ".venv\.installed"
)

rem ---- Run ---------------------------------------------------------------
".venv\Scripts\python.exe" app.py
pause
exit /b 0

:fail
echo.
echo  Setup failed. Check the internet connection, then run start.bat again.
echo  If it keeps failing, delete the ".venv" folder and try once more.
pause
exit /b 1
