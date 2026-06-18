#!/usr/bin/env bash
# Run the bot on Linux/macOS.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "==> Creating virtual environment .venv"
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Upgrading pip (needed for prebuilt wheels)"
python -m pip install -q --upgrade pip

echo "==> Installing dependencies"
pip install -q -r requirements.txt

echo "==> Installing Playwright Chromium (no-op if already present)"
python -m playwright install chromium

if [ ! -f config/search_urls.txt ]; then
  echo "==> Creating config/search_urls.txt from example"
  cp config/search_urls.example.txt config/search_urls.txt
fi

if [ ! -f .env ]; then
  echo "==> Creating .env from .env.example (fill in TG_BOT_TOKEN and TG_CHAT_ID!)"
  cp .env.example .env
fi

export PYTHONPATH=src
COMMAND="${1:-run}"
echo "==> Running: polovni_monitor ${COMMAND}"
python -m polovni_monitor "${COMMAND}"
