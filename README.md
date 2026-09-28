# polovni-car-monitor

[![CI](https://github.com/automa-flow/polovni-car-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/automa-flow/polovni-car-monitor/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

A personal, low-frequency monitor for used-car listings on
[PolovniAutomobili](https://www.polovniautomobili.com), the Serbian car
marketplace. It watches the searches you saved, appraises each **new** listing
(keywords, a "good deal" heuristic and an optional LLM appraisal) and sends it
to your own Telegram chat. Listings that look like a strong buy are flagged.

> [!IMPORTANT]
> **Unofficial project.** It is not affiliated with or endorsed by Polovni
> automobili doo. The site's Terms of Use prohibit automated use, so running
> this tool against the site may breach them, even for personal use. Read
> [Legal & responsible use](#legal--responsible-use) and
> [DISCLAIMER.md](DISCLAIMER.md) before you run it. You use it at your own
> risk.

The default keyword list and LLM prompt are tuned for a **Citroen C5 Aircross**
(1.5 BlueHDi, timing chain) and **C4 / C4 Cactus** (1.2 PureTech, wet timing
belt) search. See [Adapting it to other cars](#adapting-it-to-other-cars).

---

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Install and run](#install-and-run)
- [Telegram setup](#telegram-setup)
- [Search URLs](#search-urls)
- [Settings](#settings-env)
- [Appraisal: keywords, deal score, LLM](#appraisal-keywords-deal-score-llm)
- [Price drops, heartbeat, export](#price-drops-heartbeat-export)
- [Design decisions](#design-decisions)
- [Development](#development)
- [Project layout](#project-layout)
- [Legal & responsible use](#legal--responsible-use)
- [License](#license)

---

## How it works

1. Reads your saved search URLs from `config/search_urls.txt` (model searches)
   and, optionally, `config/explore_urls.txt` (broad price-range searches).
2. Opens each results page in a normal browser (Playwright) and collects
   listing links.
3. **First run:** remembers every listing it sees and sends nothing, so you
   aren't flooded with the current stock.
4. **Later runs:** opens only **new** listings and parses title, price, year,
   mileage, fuel, transmission, location and the description text. Structured
   fields come from the listing's labelled spec block and JSON-LD. Whole-page
   regex is only a fallback. Phone numbers and e-mails in the description are
   masked.
5. Appraises each listing with a keyword score, a good-deal score and, if
   configured, an LLM.
6. **Sends every new listing** to Telegram. It adds a **🔥 DON'T MISS** flag
   when the price is within `PRICE_TO_EUR` and the LLM judges it worth
   buying. Without an LLM, the flag needs a keyword score of at least
   `MIN_SCORE_TO_NOTIFY` or a deal score of at least `DEAL_MIN_SCORE`.
7. Stores listing IDs, titles and prices in SQLite (`data/ads.db`), so nothing
   is sent twice.

Known listings are not re-opened, except for an optional daily price
re-check. If the LLM is configured but temporarily failing, a listing with no
other positive signal is left unrecorded and retried on the next pass instead
of being sent without an appraisal.

Pages are loaded by an ordinary browser. There is no stealth mode, no spoofed
User-Agent, no captcha solving and no attempt to get past the site's
protection: if a page doesn't load, it is skipped. Low frequency is enforced
in code (see [Settings](#settings-env)).

## Requirements

- Python **3.11+**
- Disk space for Playwright's Chromium, a few hundred MB (or use your
  installed Chrome/Edge)
- A Telegram bot token (free)
- Optional: an OpenAI API key (or any OpenAI-compatible endpoint) for the LLM
  appraisal

## Install and run

### Windows

```bat
run.bat
run.bat scan-once
run.bat test-telegram
```

With no argument it monitors continuously. `scan-once` does a single pass and
`test-telegram` sends a test message. `run.bat` creates `.venv` (with the `py` launcher when available), installs
dependencies and Playwright's Chromium, and copies the example configs on the
first run. Then fill in `.env` and `config/search_urls.txt`.

> Upgrading from 0.1.x? The minimum Python version is now 3.11. If `run.bat`
> says your `.venv` is too old, delete the `.venv` folder and run it again.

### Linux / macOS

```bash
chmod +x run.sh
./run.sh                 # continuous monitoring
./run.sh scan-once       # a single pass
./run.sh test-telegram   # send a test message
# PYTHON=python3.12 ./run.sh   # choose the interpreter used for .venv
```

### Manual (any OS)

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows:     .venv\Scripts\activate
pip install -e .                        # installs deps + the `polovni-monitor` command
python -m playwright install chromium   # one-time browser download

cp .env.example .env
cp config/search_urls.example.txt config/search_urls.txt

polovni-monitor test-telegram
polovni-monitor scan-once
polovni-monitor run
polovni-monitor export                  # notified listings -> data/export.csv
```

For unattended use, run `scan-once` from cron or Task Scheduler, or keep `run`
alive in a terminal. `run` polls every `CHECK_INTERVAL_MIN` minutes by day and
every `NIGHT_INTERVAL_MIN` minutes at night.

## Telegram setup

1. In Telegram, open [@BotFather](https://t.me/BotFather), send `/newbot` and
   follow the prompts. Put the token it returns into `.env` as `TG_BOT_TOKEN`.
2. Send any message (e.g. `/start`) to your new bot.
3. Open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and
   find `"chat":{"id": …}`. Put that number into `.env` as `TG_CHAT_ID`.
4. Check it: `polovni-monitor test-telegram`.

Use your **private chat** or a **private group** (group IDs start with `-`).
Do not point the bot at a public channel: the site's Terms of Use forbid
republishing listing content publicly.

## Search URLs

### Model searches (`config/search_urls.txt`)

1. Open [polovniautomobili.com](https://www.polovniautomobili.com) and set the
   filters: make, model, price, transmission, year and so on.
2. Run the search and copy the results page URL from the address bar.
3. Paste it into `config/search_urls.txt`, one URL per line. Blank lines and
   lines starting with `#` are ignored.

See [`config/search_urls.example.txt`](config/search_urls.example.txt).

### Price-range "explore" searches (`config/explore_urls.txt`)

Broad searches that aren't tied to a make or model, for example "anything
10 000–14 000 EUR, 2019+, automatic". They answer *"what can I get for this
money?"*. Every new listing gets a generic LLM appraisal (make, model,
generation, price vs. market, equipment, risks).

- Paste broad URLs (make and model left empty) into `config/explore_urls.txt`.
  See [`config/explore_urls.example.txt`](config/explore_urls.example.txt).
- The first explore pass records everything silently, whatever
  `SEED_ON_FIRST_RUN` says. After that, only newly appeared listings are sent.

Keep the number of URLs small. Each one is a page load on every pass.

## Settings (`.env`)

Copy `.env.example` to `.env`. Every variable is optional except the Telegram
pair.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TG_BOT_TOKEN` | — | Bot token from @BotFather |
| `TG_CHAT_ID` | — | Your private chat / private group ID |
| `CHECK_INTERVAL_MIN` | `45` | Minutes between passes by day (`run`). **Minimum 15** |
| `NIGHT_INTERVAL_MIN` | `180` | Minutes between passes at night. **Minimum 15** |
| `NIGHT_START_HOUR` / `NIGHT_END_HOUR` | `0` / `7` | Local-time night window (may wrap midnight) |
| `SEED_ON_FIRST_RUN` | `true` | First run only remembers current listings |
| `PRICE_TO_EUR` | `14000` | Budget. Pricier listings are still sent, never flagged |
| `MIN_SCORE_TO_NOTIFY` | `3` | Keyword score that flags a listing (no-LLM mode) |
| `DEAL_MIN_SCORE` | `3` | Deal score that flags a listing (no-LLM mode) |
| `DEAL_PRICE_EUR` | `12500` | "Great price" threshold for the deal score |
| `DEAL_MILEAGE_KM` | `130000` | "Low mileage" threshold |
| `DEAL_YEAR_FROM` | `2020` | "Recent year" threshold |
| `RECHECK_KNOWN_HOURS` | `24` | Price re-check period for known listings. `0` disables, **minimum 24** |
| `PRICE_DROP_MIN_PCT` / `PRICE_DROP_MIN_EUR` | `5` / `300` | Notify on a drop of at least this % **or** € |
| `HEARTBEAT_HOUR` | `9` | Local hour for the daily "still alive" summary. `-1` disables |
| `REQUEST_TIMEOUT_SEC` | `25` | Page / API timeout |
| `REQUEST_DELAY_SEC` | `2` | Pause between page loads. **Minimum 2** |
| `FETCH_BACKEND` | `playwright` | `playwright` (browser) or `requests` (plain HTTP, usually refused by the site) |
| `PLAYWRIGHT_HEADLESS` | `true` | `false` shows a normal browser window. The site may refuse headless Chromium |
| `PLAYWRIGHT_CHANNEL` | *(empty)* | `chrome` / `msedge` to use your installed browser instead of bundled Chromium |
| `PAGE_WAIT_MS` | `4000` | Extra wait after load so the page's JavaScript can render |
| `FETCH_RETRIES` | `2` | Attempts per page before skipping it (1–3) |
| `USE_LLM` | `true` | Use the LLM when an API key is set |
| `OPENAI_API_KEY` | *(empty)* | Empty = keyword/deal scoring only, nothing leaves your machine |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model for the appraisal |
| `OPENAI_BASE_URL` | *(empty)* | Any OpenAI-compatible endpoint |
| `LOG_LEVEL` | `INFO` | `DEBUG` also logs full LLM prompts and responses |
| `LOG_FILE` | `data/logs/monitor.log` | Rotating log file. `none` disables |
| `DRY_RUN` | `false` | Print messages to the console instead of sending them |

The **minimums are enforced in code**: lower values are raised to the floor.
They keep the tool low-frequency no matter how it is configured.

## Appraisal: keywords, deal score, LLM

### Keywords (`config/keywords.json`)

| Bucket | Points | Examples |
| --- | --- | --- |
| `strong` | +3 | `zamenjen lanac`, `kaiš u ulju`, `set razvoda` |
| `weak` | +1 | `veliki servis`, `servisna knjiga` |
| `negative` | −5 | `nije menjan lanac`, `čuje se lanac` |

Each phrase counts once. Matching uses word boundaries, so `razvod` doesn't
fire inside `razvodnik`. Text is normalised: lowercase, Serbian diacritics
folded (`č/ć→c`, `š→s`, `ž→z`, `đ→dj`), whitespace collapsed. So `kaiš u ulju`
and `kais u ulju` both match. Edit the JSON to change the lists, no code
changes needed. If the file is missing, the defaults in
`src/polovni_monitor/scoring.py` are used.

### Deal score

`src/polovni_monitor/deal.py` scores objective merit, independent of the
chain/belt question:

- price ≤ `DEAL_PRICE_EUR`: +2
- mileage ≤ `DEAL_MILEAGE_KM`: +1, or ≤ 75 % of it: +2
- year ≥ `DEAL_YEAR_FROM`: +1
- "first owner" or "bought in Serbia": +1 each

### LLM appraisal (optional)

With `USE_LLM=true` and `OPENAI_API_KEY` set, each new listing is sent to the
model, which returns:

- a **value score** (1–10), a **price assessment** and a **risk level**;
- a short **expert reasoning** (price/mileage/year trade-off, equipment,
  service history);
- **suspicious points** and **highlights**;
- a **timing chain/belt verdict**: replaced / not replaced / not mentioned;
- `worth_sending`, which decides the 🔥 flag.

The keyword pre-scan and deal flags are passed to the model as hints. API
errors are never fatal: the bot logs them and falls back to heuristics. The
listing text goes to the API provider with phone numbers and e-mails masked.

### Adapting it to other cars

- Edit `config/keywords.json` with the signals that matter for your model.
- Edit `SYSTEM_PROMPT` in `src/polovni_monitor/llm.py`. It describes the
  Citroen engines, price bands and trims. `EXPLORE_SYSTEM_PROMPT` is already
  generic.
- Or skip the model-specific part and use only
  [explore searches](#price-range-explore-searches-configexplore_urlstxt).

## Price drops, heartbeat, export

- **Price-drop alerts.** At most every `RECHECK_KNOWN_HOURS` (≥ 24 h) known
  listings are re-opened. A `📉 Price drop` message is sent when the price
  falls by at least `PRICE_DROP_MIN_PCT` % or `PRICE_DROP_MIN_EUR` €.
- **Daily heartbeat.** Once a day, at or after `HEARTBEAT_HOUR`, the bot sends
  a short summary: listings tracked, notifications in the last 24 h, last pass.
- **Export.** `polovni-monitor export [--path file.csv]` writes the listings
  you were notified about (ID, title, price, score, first seen, URL) to
  `data/export.csv`. It is for your own records. Don't publish it.

Notifications use Telegram HTML formatting with an inline **Open listing**
button.

## Design decisions

**Parse anchors that don't change.** The site is a Next.js app with
styled-components. Its class names are hashes like `kIbXrB` that change on
every deploy, so the parser never depends on them. It anchors on things that
stay put: the labelled spec rows (`Godište:`, `Kilometraža:`), the `Opis`
heading and the JSON-LD block. Whole-page regex is only a fallback, because
the same page shows teasers for other cars. A naive "first year on the page"
regex picks up *their* year and mileage. The synthetic test fixture includes
exactly such a decoy, so the tests catch that regression.

**Graceful degradation without the LLM.** Appraisal has three layers, from
cheapest to most expensive:

1. **Keyword score.** Always runs, costs nothing, and is passed to the LLM as
   a hint.
2. **Deal score.** Always runs and uses only objective fields: price, mileage,
   year, origin.
3. **LLM appraisal.** When it is available, it alone decides the 🔥 flag.

With no API key, the first two layers decide the flag. When a key is set but
the API call fails (outage or exhausted quota), the listing is not silently
lost or sent without analysis:

- if a heuristic already marks it as interesting, it is sent with "AI
  analysis: not available";
- otherwise it is **not recorded** and is retried on the next pass, once the
  LLM is back.

`analyze_listing()` never raises: every API or parse error becomes an
"unavailable" verdict. Explore searches have no model-specific heuristics, so
there a failed appraisal just sends the listing without one.

**Limits live in code, not in defaults.** A public tool should not be one
`.env` edit away from becoming a high-frequency scraper. The site's Terms of
Use also forbid creating unnecessary load. So the floors (15 min between
passes, 2 s between page loads, 3 attempts per page, 24 h between price
re-checks) are applied in `config.py` whatever the configuration says. They
cost nothing in practice: new car listings appear at a pace of hours, not
minutes. For the same reason:

- a pass opens only *new* listings, so steady state is a few search pages
  plus a handful of cards;
- the first run only records what already exists;
- a page stuck on a verification screen is skipped rather than worked around.

**Personal data never leaves the parser unmasked.** Phone numbers and e-mails
are masked in `parse_ad()`, before any sink: logs, the LLM provider, Telegram.
The database keeps only a hash of the description, not the text. Tests use a
hand-written page instead of a saved real one.

**Testable without the network.** Fetching sits behind a small `Fetcher`
protocol. `tests/test_scan.py` drives a full monitoring pass with an in-memory
fake: seed, detect a new listing, send, then stay quiet. So the orchestration
logic is covered without a browser, Telegram or an API key.

## Development

```bash
pip install -e ".[dev]"
pytest          # 50+ tests, no network access needed
ruff check .
```

CI runs ruff and pytest on Python 3.11–3.14 (Linux) and 3.14 (Windows).

Parser tests run against
[`tests/fixtures/listing_synthetic.html`](tests/fixtures/listing_synthetic.html).
It is a hand-written page that mirrors the real markup: labelled spec list,
"Opis" block, JSON-LD, hashed class names and decoy numbers. All of its data is
fictional. **Do not commit saved pages from the real site.** They contain
sellers' personal data and content owned by the site. If the markup changes,
update the synthetic fixture to reproduce the new structure.

## Project layout

```
polovni-car-monitor/
├── .github/workflows/ci.yml
├── config/
│   ├── search_urls.example.txt
│   ├── explore_urls.example.txt
│   └── keywords.json
├── data/                  # SQLite DB, logs, browser profile, exports (gitignored)
├── src/polovni_monitor/
│   ├── main.py            # CLI, monitoring loop, explore pass, price re-checks
│   ├── config.py          # .env loading, paths, enforced limits
│   ├── fetcher.py         # playwright / requests backends behind a Protocol
│   ├── parser.py          # results + listing parsing (spec block, JSON-LD, fallbacks)
│   ├── scoring.py         # keyword scoring (word-boundary matching)
│   ├── deal.py            # good-deal heuristic
│   ├── llm.py             # optional OpenAI appraisal
│   ├── telegram.py        # message formatting and sending
│   ├── db.py              # SQLite store with migrations and meta state
│   ├── models.py          # Ad dataclass
│   └── utils.py           # logging, text normalisation, contact redaction
├── tests/
│   ├── fixtures/listing_synthetic.html
│   └── test_*.py
├── .env.example
├── run.bat / run.sh
├── pyproject.toml
├── CHANGELOG.md
├── DISCLAIMER.md
├── SECURITY.md
└── LICENSE
```

## Legal & responsible use

Summary only. The full text, with the quoted clauses, is in
[DISCLAIMER.md](DISCLAIMER.md). This is not legal advice.

- **No affiliation.** "Polovni Automobili" is a trademark of its owner and is
  named here only to say which site the tool works with.
- **The site's Terms of Use** ([Uslovi korišćenja](https://www.polovniautomobili.com/uslovi-koriscenja),
  in force since 27 Aug 2026) prohibit, among other things, *any automated use*
  of the service, circumventing its security technologies, creating
  unnecessary load, and republishing listing content publicly without written
  consent. They allow downloading content only for visitors' personal needs.
  **Running this tool may therefore breach them.** Whether you run it is your
  decision and your responsibility.
- **How the tool keeps its footprint small:** no stealth or evasion, enforced
  low frequency, only new listings are opened, seller contact details are
  never extracted and are masked in descriptions, results go only to your own
  chat, all data stays on your machine.
- **Your part:** personal, non-commercial use only. No public channels, no
  datasets, no reselling, no contacting sellers in bulk. Don't raise the
  frequency or add evasion. Stop if the site asks you to.
- **Rights holders:** to request a change or removal,
  [open an issue](https://github.com/automa-flow/polovni-car-monitor/issues).

## License

[MIT](LICENSE) © 2026 Vadakuma. The license covers this source code only. It
grants no rights to the website, its content or its data.
