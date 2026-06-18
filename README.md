# polovni-car-monitor

A small personal **low-frequency** monitor for listings on
[PolovniAutomobili](https://www.polovniautomobili.com). Every N minutes it
opens pre-saved search URLs (with your filters already applied), finds new
listings, opens each listing card, parses basic data and the description text,
scores it against a keyword list (timing chain/belt replacement, servicing),
and sends interesting listings to Telegram.

PolovniAutomobili sits behind Cloudflare, so by default the bot fetches pages
with a real headless Chromium (Playwright) that renders JS and clears
Cloudflare's standard "Just a moment" check — exactly like opening the page
yourself. No captchas are solved and no protections are bypassed; requests stay
low-frequency.

The browser uses a **persistent profile** (`data/.pw-profile/`), so the
Cloudflare clearance cookie and cache survive between runs and most requests
skip the challenge entirely. If Cloudflare still blocks you in headless mode,
set `PLAYWRIGHT_HEADLESS=false` (a visible browser passes much more reliably)
and/or `PLAYWRIGHT_CHANNEL=chrome` to use your installed Chrome.

Tuned for Citroen C5 Aircross (1.5 BlueHDi — timing chain `lanac`) and
Citroen C4 / C4 Cactus (PureTech — wet timing belt `kaiš u ulju`).

> ⚠️ This is a tool for **personal** use.
> - Do not use it for mass scraping.
> - Do not bypass captcha or site protections.
> - Do not parse seller phone numbers or personal data.
> - Keep the request rate low (`CHECK_INTERVAL_MIN`, `REQUEST_DELAY_SEC`).

---

## What the bot does

1. Reads search URLs from `config/search_urls.txt`.
2. Opens the results pages and collects listing links.
3. For new listings, opens the card and parses:
   `title`, `price`, `year`, `mileage`, `fuel`, `transmission`, `description`, `url`.
4. Analyzes the description text: strong/weak/negative signals → `score`.
5. If `score >= MIN_SCORE_TO_NOTIFY` and price `<= PRICE_TO_EUR`, sends to Telegram.
6. Stores processed listings in SQLite (`data/ads.db`) to avoid spam.

---

## Install and run

### Linux / macOS

```bash
cp .env.example .env
cp config/search_urls.example.txt config/search_urls.txt
# fill in TG_BOT_TOKEN, TG_CHAT_ID and your search URLs

chmod +x run.sh
./run.sh                 # continuous monitoring (run)
./run.sh scan-once       # a single pass
./run.sh test-telegram   # Telegram smoke test
```

`run.sh` creates `.venv`, installs dependencies (including the Playwright
Chromium browser via `python -m playwright install chromium`), and copies the
example configs.

### Windows

```bat
run.bat
run.bat scan-once
run.bat test-telegram
```

> Note: `run.bat` calls `python`. Make sure a real Python 3.9+ is on your PATH
> (the Microsoft Store stub will not work). If `.venv` already exists, the
> scripts use the interpreter inside it.

### Manual (any OS)

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows:     .venv\Scripts\activate
pip install -r requirements.txt
python -m playwright install chromium   # one-time browser download (~120 MB)

cp .env.example .env
cp config/search_urls.example.txt config/search_urls.txt

# run (src must be on PYTHONPATH)
PYTHONPATH=src python -m polovni_monitor scan-once
PYTHONPATH=src python -m polovni_monitor run
PYTHONPATH=src python -m polovni_monitor test-telegram
# or directly
python src/polovni_monitor/main.py scan-once
```

---

## Telegram: token and chat_id

### 1. Create a bot and get `TG_BOT_TOKEN`

1. In Telegram, open [@BotFather](https://t.me/BotFather).
2. Send `/newbot`, set a name and a username.
3. BotFather returns a token like `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxx`.
4. Put it in `.env` as `TG_BOT_TOKEN`.

### 2. Find your `TG_CHAT_ID`

1. Send any message to your bot (e.g. `/start`).
2. Open in a browser (substitute your token):
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
3. In the JSON, find `"chat":{"id": ... }` — that is your `TG_CHAT_ID`.
4. Put it in `.env`.

> To post into a group/channel, add the bot there; group ids usually start with `-`.

After configuring, verify with: `python -m polovni_monitor test-telegram`.

---

## How to copy a search URL from PolovniAutomobili

1. Open https://www.polovniautomobili.com.
2. Set the filters: make, model, price (`do 14000`), transmission (`automatik`),
   year, etc.
3. Click search — the filters end up in the address bar.
4. Copy the results page URL and paste it as a line in `config/search_urls.txt`.
5. Add as many URLs as you like, one per line. Lines starting with `#` and empty
   lines are ignored.

See `config/search_urls.example.txt` for an example.

---

## Settings (`.env`)

| Variable             | Purpose                                                           |
|----------------------|-------------------------------------------------------------------|
| `TG_BOT_TOKEN`       | Bot token from BotFather                                          |
| `TG_CHAT_ID`         | Where to send notifications                                       |
| `CHECK_INTERVAL_MIN` | Check interval in minutes (for `run`). Default `45`              |
| `PRICE_TO_EUR`       | Price threshold; above it, no notification. Default `14000`      |
| `SEED_ON_FIRST_RUN`  | `true`: the first run only remembers current listings           |
| `MIN_SCORE_TO_NOTIFY`| Minimum score to notify. Default `3`                            |
| `REQUEST_TIMEOUT_SEC`| Request timeout. Default `25`                                   |
| `REQUEST_DELAY_SEC`  | Delay between requests (politeness). Default `2`                |
| `DRY_RUN`            | `true`: print messages to console instead of sending to Telegram |
| `FETCH_BACKEND`      | `playwright` (default, clears Cloudflare) or `requests` (plain HTTP) |
| `PLAYWRIGHT_HEADLESS`| `true` (default). `false` (visible browser) passes Cloudflare far better |
| `PLAYWRIGHT_CHANNEL` | Empty = bundled Chromium; `chrome` / `msedge` use your installed browser |
| `PAGE_WAIT_MS`       | Extra wait after load for the JS challenge/SPA. Default `4000`   |
| `FETCH_RETRIES`      | Retries if the Cloudflare challenge doesn't clear. Default `2`   |
| `USE_LLM`            | `true` (default): use OpenAI to analyze listings (needs API key) |
| `OPENAI_API_KEY`     | OpenAI key; if empty, the bot falls back to keyword scoring     |
| `OPENAI_MODEL`       | Model for analysis. Default `gpt-4o-mini`                       |
| `OPENAI_BASE_URL`    | Optional custom OpenAI-compatible endpoint                      |

### Configuring the interval

Change `CHECK_INTERVAL_MIN` in `.env`. It only affects the `run` command (the
infinite loop). For one-off checks use `scan-once` (e.g. from a system
scheduler — `cron` / Task Scheduler).

### How `SEED_ON_FIRST_RUN` works

On the very first run (the `data/ads.db` database is empty) with
`SEED_ON_FIRST_RUN=true`, the bot **only remembers** the current listings and
sends nothing — so you are not flooded with all existing listings at once. From
the next pass on, it notifies only about **new** listings.

To also get notifications for already-existing listings, set
`SEED_ON_FIRST_RUN=false` before the first run.

> Note: each pass only fetches the listing card for **new** IDs; already-known
> listings are skipped (no re-fetch). This keeps requests low and avoids
> Cloudflare friction. The trade-off is that the bot does not re-notify when an
> existing listing's description later changes.

---

## Scoring and keywords

- Strong signal: `+3` (e.g. `zamenjen lanac`, `kaiš u ulju`).
- Weak signal: `+1` (e.g. `veliki servis`, `servisna knjiga`).
- Negative signal: `-5` (e.g. `nije menjan lanac`, `čuje se lanac`).
- Each signal type is counted once.
- Text is normalized: lowercase, Serbian diacritics removed
  (`č/ć→c`, `š→s`, `ž→z`, `đ→dj`), whitespace collapsed — so both
  `kaiš u ulju` and `kais u ulju` match.

### Adding new keywords

Edit `config/keywords.json` (three lists: `strong`, `weak`, `negative`) — no
code changes needed. If the file is missing, the built-in defaults from
`src/polovni_monitor/scoring.py` are used.

---

## LLM analysis (optional)

If `USE_LLM=true` and `OPENAI_API_KEY` is set, each **new** listing is sent to
an LLM, which:

- decides whether the listing is **worth sending** (this becomes the notify gate
  instead of the raw keyword score);
- writes a short overall **assessment**;
- flags **suspicious** points (vague wording, `rezervisan`, odometer doubts, …);
- gives the **mandatory verdict on the timing chain/belt**: replaced (`yes`),
  not replaced / warned (`no`), or not mentioned (`unclear`) — with a short note.

Keyword scoring still runs first (cheap) and is passed to the model as a hint.
The LLM is only called for new listings, so it stays low-frequency. Any LLM/API
error is non-fatal: the bot logs it and falls back to keyword scoring. With
`USE_LLM=false` or no API key, the message still answers the chain/belt question
from the keyword scan.

Default model is `gpt-4o-mini` (cheap); change with `OPENAI_MODEL`. To use an
OpenAI-compatible endpoint, set `OPENAI_BASE_URL`. To respond in a different
language, edit `SYSTEM_PROMPT` in `src/polovni_monitor/llm.py`.

---

## Tests

```bash
PYTHONPATH=src pytest        # or just: pytest (pythonpath is set in pyproject.toml)
```

---

## Project layout

```
polovni-car-monitor/
  README.md
  requirements.txt
  pyproject.toml
  .env.example
  .gitignore
  run.sh
  run.bat
  config/
    search_urls.example.txt
    keywords.json
  src/polovni_monitor/
    __init__.py
    __main__.py
    main.py        # CLI and loop
    config.py      # .env + paths
    db.py          # SQLite
    models.py      # Ad dataclass
    fetcher.py     # fetch backends (playwright / requests)
    llm.py         # optional OpenAI listing analysis
    parser.py      # HTML parsing
    scoring.py     # text analysis
    telegram.py    # message sending
    utils.py       # logging, normalization
  data/            # SQLite database (gitignored)
  tests/
    test_scoring.py
    test_price_parsing.py
    test_llm.py
```
