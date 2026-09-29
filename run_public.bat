@echo off
title iTANTRA - Public Demo (Cloudflare Tunnel)
cd /d "%~dp0"

echo.
echo ============================================================
echo   iTANTRA - PUBLIC DEMO MODE
echo   Judges will open a public HTTPS link - no setup needed.
echo ============================================================
echo.

REM --- Check venv exists ---
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Run run.bat at least once first to build the venv.
  pause
  exit /b 1
)

REM --- Download cloudflared.exe if missing ---
if not exist "cloudflared.exe" (
  echo [1/3] Downloading cloudflared.exe (one time, ~30 MB) ...
  powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'cloudflared.exe'"
  if errorlevel 1 (
    echo [ERROR] Download failed. Check internet, run this file again.
    pause
    exit /b 1
  )
) else (
  echo [1/3] cloudflared.exe already present.
)

REM --- Start the Flask server in a separate window ---
echo [2/3] Starting local iTANTRA server ...
start "iTANTRA Server" cmd /k ".venv\Scripts\python.exe app.py"
timeout /t 6 >nul

REM --- Start the public tunnel ---
echo [3/3] Opening public tunnel ...
echo.
echo ============================================================
echo   WHEN YOU SEE A URL LIKE:
echo.
echo       https://random-words-1234.trycloudflare.com
echo.
echo   COPY IT AND ADD  /solo  AT THE END - THAT IS THE
echo   LINK YOU SEND TO JUDGES.
echo.
echo   Example to send:
echo       https://random-words-1234.trycloudflare.com/solo
echo.
echo   KEEP THIS WINDOW OPEN while judges are viewing.
echo   Closing it kills the public link.
echo ============================================================
echo.

cloudflared.exe tunnel --url http://localhost:8000

pause