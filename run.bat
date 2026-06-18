@echo off
REM Run the bot on Windows.
setlocal
cd /d "%~dp0"

if not exist .venv (
  echo ==^> Creating virtual environment .venv
  python -m venv .venv
)

call .venv\Scripts\activate.bat

echo ==^> Upgrading pip ^(needed for prebuilt wheels^)
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

set PYTHONPATH=src
set COMMAND=%1
if "%COMMAND%"=="" set COMMAND=run

echo ==^> Running: polovni_monitor %COMMAND%
python -m polovni_monitor %COMMAND%

endlocal
