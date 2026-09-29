@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title iTANTRA - Offline Neural Transceiver

echo.
echo =========================================================
echo   iTANTRA  -  OFFLINE NEURAL TRANSCEIVER
echo   SIH 2026  -  Problem Statement 173
echo =========================================================
echo.

REM ------------------------------------------------------------
REM  Locate Python
REM ------------------------------------------------------------
set PYEXE=
where python >nul 2>nul && set PYEXE=python
if "%PYEXE%"=="" ( where py >nul 2>nul && set PYEXE=py )
if "%PYEXE%"=="" (
  echo [ERROR] Python 3.10+ was not found on this machine.
  echo         Install from https://www.python.org/downloads/
  echo         Make sure "Add python.exe to PATH" is ticked.
  echo.
  pause
  exit /b 1
)

REM ------------------------------------------------------------
REM  Create / reuse virtual environment
REM ------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtual environment ^(.venv^) ...
  %PYEXE% -m venv .venv
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    pause
    exit /b 1
  )
) else (
  echo [1/4] Virtual environment already present.
)
set VPY=.venv\Scripts\python.exe

REM ------------------------------------------------------------
REM  Install dependencies
REM ------------------------------------------------------------
echo [2/4] Installing / verifying dependencies ...
"%VPY%" -m pip install --upgrade pip --quiet --disable-pip-version-check
"%VPY%" -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
  echo [ERROR] pip install failed. Check your internet connection during first setup.
  pause
  exit /b 1
)

REM ------------------------------------------------------------
REM  Offline speech models
REM ------------------------------------------------------------
echo [3/4] Checking offline speech models ...
"%VPY%" setup_models.py
if errorlevel 1 (
  echo [WARN] Model setup reported an issue. Server will still start.
  echo        Hindi / English STT may fall back to DEMO MODE.
)

REM ------------------------------------------------------------
REM  Start server  +  auto-open admin dashboard
REM ------------------------------------------------------------
echo [4/4] Starting iTANTRA server ...
echo.

start "" /min cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000/admin"

"%VPY%" app.py

echo.
echo Server stopped.
pause

