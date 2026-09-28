@echo off
REM Run the monitor on Windows. Requires Python 3.11+.
setlocal
cd /d "%~dp0"

if not exist .venv (
  echo ==^> Creating virtual environment .venv
  where py >nul 2>nul
  if errorlevel 1 (
    python -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
)

if not exist .venv\Scripts\python.exe (
  echo Could not create .venv. Install Python 3.11+ from https://www.python.org/downloads/
  exit /b 1
)

.venv\Scripts\python.exe -c "import sys; sys.exit(sys.version_info < (3, 11))"
if errorlevel 1 (
  echo .venv was created with Python older than 3.11.
  echo Delete the .venv folder and run this script again.
  exit /b 1
)

call .venv\Scripts\activate.bat

echo ==^> Upgrading pip
python -m pip install -q --upgrade pip

echo ==^> Installing dependencies
pip install -q -r requirements.txt

echo ==^> Installing Playwright Chromium ^(no-op if already present^)
python -m playwright install chromium

if not exist config\search_urls.txt (
  echo ==^> Creating config\search_urls.txt from example
  copy /Y config\search_urls.example.txt config\search_urls.txt >nul
)

if not exist .env (
  echo ==^> Creating .env from .env.example ^(fill in TG_BOT_TOKEN and TG_CHAT_ID!^)
  copy /Y .env.example .env >nul
)

set COMMAND=%1
if "%COMMAND%"=="" set COMMAND=run

echo ==^> Running: polovni-monitor %COMMAND%
python -m polovni_monitor %COMMAND%

endlocal
