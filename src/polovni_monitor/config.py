"""Load configuration from .env and resolve project paths."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"

SEARCH_URLS_FILE = CONFIG_DIR / "search_urls.txt"
EXPLORE_URLS_FILE = CONFIG_DIR / "explore_urls.txt"
KEYWORDS_FILE = CONFIG_DIR / "keywords.json"
ENV_FILE = PROJECT_ROOT / ".env"
DB_PATH = DATA_DIR / "ads.db"
DEFAULT_LOG_FILE = DATA_DIR / "logs" / "monitor.log"
EXPORT_PATH = DATA_DIR / "export.csv"

# Politeness floors. They are enforced in code (not just defaults) so that no
# .env value can turn the monitor into a high-frequency scraper.
MIN_CHECK_INTERVAL_MIN = 15
MIN_REQUEST_DELAY_SEC = 2.0
MAX_FETCH_RETRIES = 3
MIN_RECHECK_KNOWN_HOURS = 24  # when enabled; 0 disables re-checks


@dataclass
class Config:
    tg_bot_token: str
    tg_chat_id: str
    check_interval_min: int
    price_to_eur: int
    seed_on_first_run: bool
    min_score_to_notify: int
    request_timeout_sec: int
    request_delay_sec: float
    dry_run: bool
    db_path: Path
    fetch_backend: str  # "playwright" | "requests"
    playwright_headless: bool
    playwright_channel: str  # "" (bundled chromium) | "chrome" | "msedge"
    page_wait_ms: int
    fetch_retries: int
    use_llm: bool
    openai_api_key: str
    openai_model: str
    openai_base_url: str
    # Night schedule (local time): slower polling overnight.
    night_interval_min: int
    night_start_hour: int
    night_end_hour: int
    # "Good deal" heuristic thresholds (used alongside chain/belt scoring).
    deal_min_score: int
    deal_price_eur: int
    deal_mileage_km: int
    deal_year_from: int
    # Price-drop re-checks of already-known listings.
    recheck_known_hours: int
    price_drop_min_pct: float
    price_drop_min_eur: int
    # Daily heartbeat summary (local hour; -1 disables).
    heartbeat_hour: int
    # Logging.
    log_level: int
    log_file: Path | None


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(float(raw))
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_recheck_hours(name: str, default: int) -> int:
    """Price re-check interval: 0 (or negative) disables, otherwise floored."""
    hours = _get_int(name, default)
    return 0 if hours <= 0 else max(MIN_RECHECK_KNOWN_HOURS, hours)


def _get_log_level(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return getattr(logging, raw.strip().upper(), default)


def _get_log_file(name: str) -> Path | None:
    """Resolve the log file path. Empty/default -> standard path; 'none'/'off'
    disables file logging."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return DEFAULT_LOG_FILE
    value = raw.strip()
    if value.lower() in {"none", "off", "false", "0"}:
        return None
    return Path(value)


def load_config() -> Config:
    """Read .env and build a Config."""
    load_dotenv(ENV_FILE)
    return Config(
        tg_bot_token=os.getenv("TG_BOT_TOKEN", "").strip(),
        tg_chat_id=os.getenv("TG_CHAT_ID", "").strip(),
        check_interval_min=max(
            MIN_CHECK_INTERVAL_MIN, _get_int("CHECK_INTERVAL_MIN", 45)
        ),
        price_to_eur=_get_int("PRICE_TO_EUR", 14000),
        seed_on_first_run=_get_bool("SEED_ON_FIRST_RUN", True),
        min_score_to_notify=_get_int("MIN_SCORE_TO_NOTIFY", 3),
        request_timeout_sec=_get_int("REQUEST_TIMEOUT_SEC", 25),
        request_delay_sec=max(
            MIN_REQUEST_DELAY_SEC, _get_float("REQUEST_DELAY_SEC", 2.0)
        ),
        dry_run=_get_bool("DRY_RUN", False),
        db_path=DB_PATH,
        fetch_backend=os.getenv("FETCH_BACKEND", "playwright").strip().lower(),
        playwright_headless=_get_bool("PLAYWRIGHT_HEADLESS", True),
        playwright_channel=os.getenv("PLAYWRIGHT_CHANNEL", "").strip(),
        page_wait_ms=_get_int("PAGE_WAIT_MS", 4000),
        fetch_retries=min(MAX_FETCH_RETRIES, max(1, _get_int("FETCH_RETRIES", 2))),
        use_llm=_get_bool("USE_LLM", True),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip(),
        night_interval_min=max(
            MIN_CHECK_INTERVAL_MIN, _get_int("NIGHT_INTERVAL_MIN", 180)
        ),
        night_start_hour=_get_int("NIGHT_START_HOUR", 0),
        night_end_hour=_get_int("NIGHT_END_HOUR", 7),
        deal_min_score=_get_int("DEAL_MIN_SCORE", 3),
        deal_price_eur=_get_int("DEAL_PRICE_EUR", 12500),
        deal_mileage_km=_get_int("DEAL_MILEAGE_KM", 130000),
        deal_year_from=_get_int("DEAL_YEAR_FROM", 2020),
        recheck_known_hours=_get_recheck_hours("RECHECK_KNOWN_HOURS", 24),
        price_drop_min_pct=_get_float("PRICE_DROP_MIN_PCT", 5.0),
        price_drop_min_eur=_get_int("PRICE_DROP_MIN_EUR", 300),
        heartbeat_hour=_get_int("HEARTBEAT_HOUR", 9),
        log_level=_get_log_level("LOG_LEVEL", logging.INFO),
        log_file=_get_log_file("LOG_FILE"),
    )


def _read_url_file(path: Path) -> list[str]:
    """Read a URL-per-line file, skipping blanks and '#' comments."""
    if not path.exists():
        return []
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def load_search_urls() -> list[str]:
    """Read the list of model-specific search URLs from config/search_urls.txt."""
    return _read_url_file(SEARCH_URLS_FILE)


def load_explore_urls() -> list[str]:
    """Read the price-range "explore" search URLs from config/explore_urls.txt.

    These are not tied to a make/model — they survey whatever turns up in a
    given price band, with a generic LLM appraisal attached.
    """
    return _read_url_file(EXPLORE_URLS_FILE)
