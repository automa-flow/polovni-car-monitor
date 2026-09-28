#!/usr/bin/env bash
# Run the monitor on Linux/macOS. Requires Python 3.11+.
# Override the interpreter used to create .venv with e.g. PYTHON=python3.12.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if [ ! -d .venv ]; then
  echo "==> Creating virtual environment .venv"
  "$PYTHON" -m venv .venv
fi

if ! .venv/bin/python -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
  echo "!! .venv was created with Python older than 3.11." >&2
  echo "!! Remove .venv and rerun, e.g.: rm -rf .venv && PYTHON=python3.12 ./run.sh" >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Upgrading pip"
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

COMMAND="${1:-run}"
echo "==> Running: polovni-monitor ${COMMAND}"
python -m polovni_monitor "${COMMAND}"
