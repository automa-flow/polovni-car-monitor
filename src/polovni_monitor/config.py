"""Load configuration from .env and resolve project paths."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"

SEARCH_URLS_FILE = CONFIG_DIR / "search_urls.txt"
KEYWORDS_FILE = CONFIG_DIR / "keywords.json"
ENV_FILE = PROJECT_ROOT / ".env"
DB_PATH = DATA_DIR / "ads.db"


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


def load_config() -> Config:
    """Read .env and build a Config."""
    load_dotenv(ENV_FILE)
    return Config(
        tg_bot_token=os.getenv("TG_BOT_TOKEN", "").strip(),
        tg_chat_id=os.getenv("TG_CHAT_ID", "").strip(),
        check_interval_min=_get_int("CHECK_INTERVAL_MIN", 45),
        price_to_eur=_get_int("PRICE_TO_EUR", 14000),
        seed_on_first_run=_get_bool("SEED_ON_FIRST_RUN", True),
        min_score_to_notify=_get_int("MIN_SCORE_TO_NOTIFY", 3),
        request_timeout_sec=_get_int("REQUEST_TIMEOUT_SEC", 25),
        request_delay_sec=_get_float("REQUEST_DELAY_SEC", 2.0),
        dry_run=_get_bool("DRY_RUN", False),
        db_path=DB_PATH,
        fetch_backend=os.getenv("FETCH_BACKEND", "playwright").strip().lower(),
        playwright_headless=_get_bool("PLAYWRIGHT_HEADLESS", True),
        playwright_channel=os.getenv("PLAYWRIGHT_CHANNEL", "").strip(),
        page_wait_ms=_get_int("PAGE_WAIT_MS", 4000),
        fetch_retries=max(1, _get_int("FETCH_RETRIES", 2)),
        use_llm=_get_bool("USE_LLM", True),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip(),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "").strip(),
        night_interval_min=_get_int("NIGHT_INTERVAL_MIN", 180),
        night_start_hour=_get_int("NIGHT_START_HOUR", 0),
        night_end_hour=_get_int("NIGHT_END_HOUR", 7),
        deal_min_score=_get_int("DEAL_MIN_SCORE", 3),
        deal_price_eur=_get_int("DEAL_PRICE_EUR", 12500),
        deal_mileage_km=_get_int("DEAL_MILEAGE_KM", 130000),
        deal_year_from=_get_int("DEAL_YEAR_FROM", 2020),
    )


def load_search_urls() -> list[str]:
    """Read the list of search URLs from config/search_urls.txt."""
    if not SEARCH_URLS_FILE.exists():
        return []
    urls: list[str] = []
    for line in SEARCH_URLS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls
