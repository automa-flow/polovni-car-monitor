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
   `title`, `price`, `year`, `mileage`, `fuel`, `transmission`, `location`,
   `description`, `url`. Structured fields are read from the listing's labeled
   spec block ("Godište", "Kilometraža", …) and JSON-LD, with whole-page regex
   only as a fallback — so a stray number from a sidebar isn't mistaken for the
   car's own data.
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
pip install -e .                        # installs deps + the `polovni-monitor` command
python -m playwright install chromium   # one-time browser download (~120 MB)

cp .env.example .env
cp config/search_urls.example.txt config/search_urls.txt

# run via the installed console command
polovni-monitor scan-once
polovni-monitor run
polovni-monitor test-telegram
polovni-monitor export                  # write notified listings to data/export.csv

# or without installing (src on PYTHONPATH)
PYTHONPATH=src python -m polovni_monitor scan-once
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
| `CHECK_INTERVAL_MIN` | Daytime check interval in minutes (for `run`). Default `45`      |
| `NIGHT_INTERVAL_MIN` | Night check interval in minutes. Default `180` (every 3h)       |
| `NIGHT_START_HOUR` / `NIGHT_END_HOUR` | Local-time night window. Default `0`–`7`       |
| `DEAL_MIN_SCORE`     | Deal score that alone justifies sending. Default `3`            |
| `DEAL_PRICE_EUR`     | "Great price" threshold for the deal heuristic. Default `12500` |
| `DEAL_MILEAGE_KM`    | "Low mileage" threshold. Default `130000`                      |
| `DEAL_YEAR_FROM`     | "Recent year" threshold. Default `2020`                        |
| `RECHECK_KNOWN_HOURS`| Re-check known listings for price drops at most this often. Default `24` (`0` disables) |
| `PRICE_DROP_MIN_PCT` | Notify on a price drop of at least this many percent. Default `5` |
| `PRICE_DROP_MIN_EUR` | …or at least this many euros. Default `300`                     |
| `HEARTBEAT_HOUR`     | Local hour for the once-a-day status summary. Default `9` (`-1` disables) |
| `LOG_LEVEL`          | Console log level (`DEBUG`/`INFO`/…). Default `INFO`            |
| `LOG_FILE`           | Rotating log file path. Empty = `data/logs/monitor.log`; `none` disables |
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

At night (local time, by default `00:00`–`07:00`) the bot polls less often —
every `NIGHT_INTERVAL_MIN` minutes (default 180) instead of
`CHECK_INTERVAL_MIN` — since new listings are rare overnight.

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

### Good-deal heuristic

Beyond the chain/belt keywords, a listing can also be sent on objective merit
even without any chain evidence. `src/polovni_monitor/deal.py` scores each car
on **price** (`≤ DEAL_PRICE_EUR` → +2), **mileage** (`≤ DEAL_MILEAGE_KM` → +1,
much lower → +2), **year** (`≥ DEAL_YEAR_FROM` → +1) and **origin** (first
owner / domestic → +1 each). If that score reaches `DEAL_MIN_SCORE`, the bot
notifies and the message shows a `💰 Deal score` block. A listing is sent when
the price is within `PRICE_TO_EUR` **and** any of: the LLM says it's worth it,
the keyword score is high enough, or the deal score is high enough.

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

## Price-drop alerts, heartbeat & export

- **Price-drop alerts.** Known listings are normally not re-fetched (to keep the
  request rate low), but at most every `RECHECK_KNOWN_HOURS` the bot re-opens
  them, compares the price to the last seen one, and sends a `📉 Price drop`
  message when the drop is at least `PRICE_DROP_MIN_PCT` percent or
  `PRICE_DROP_MIN_EUR` euros.
- **Daily heartbeat.** Once a day, on/after `HEARTBEAT_HOUR` (local), the bot
  sends a short summary (listings tracked, notified in the last 24h, last pass)
  so you know it's still running. Set `HEARTBEAT_HOUR=-1` to disable.
- **Export.** `polovni-monitor export` writes all notified listings to
  `data/export.csv` (override with `--path`).

Notifications use Telegram HTML formatting with an inline **"Open listing"**
button.

## Tests

```bash
pytest        # pythonpath is set in pyproject.toml
```

`tests/test_parser.py` runs against a saved real listing page
(`tests/fixtures/listing_c5.html`), so parsing is protected against regressions
if the site markup shifts.

---

## Project layout

```
polovni-car-monitor/
  README.md
  LICENSE
  requirements.txt
  pyproject.toml   # packaging + deps + the `polovni-monitor` entry point
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
    db.py          # SQLite (with migrations + meta state)
    models.py      # Ad dataclass
    deal.py        # good-deal heuristic (price/mileage/year/origin)
    fetcher.py     # fetch backends (playwright / requests) behind a Protocol
    llm.py         # optional OpenAI listing analysis
    parser.py      # HTML parsing (structured spec + JSON-LD, regex fallback)
    scoring.py     # text analysis (word-boundary keyword matching)
    telegram.py    # message formatting + sending (HTML + inline button)
    utils.py       # logging (console + rotating file), normalization
  data/            # SQLite database, logs, exports (gitignored)
  tests/
    fixtures/
      listing_c5.html
    test_scoring.py
    test_price_parsing.py
    test_parser.py
    test_llm.py
    test_deal.py
```
