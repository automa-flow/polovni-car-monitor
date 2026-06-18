"""Send messages via the Telegram Bot API + message formatting."""
from __future__ import annotations

import logging

import requests

from .config import Config
from .models import Ad
from .scoring import ScoreResult

logger = logging.getLogger("polovni_monitor.telegram")

API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_message(ad: Ad, result: ScoreResult, tag: str = "new") -> str:
    """Build the notification text for a listing."""
    if tag == "updated":
        header = "🔁 Updated listing"
    else:
        header = "🚗 Interesting listing found"

    price = f"{_fmt_int(ad.price)} €" if ad.price is not None else "not detected"
    mileage = f"{_fmt_int(ad.mileage)} km" if ad.mileage is not None else "—"

    lines = [
        header,
        "",
        ad.title or "Citroen (no title)",
        f"Price: {price}",
        f"Year: {ad.year if ad.year is not None else '—'}",
        f"Mileage: {mileage}",
        f"Fuel: {ad.fuel or '—'}",
        f"Transmission: {ad.transmission or '—'}",
        "",
        f"Score: {result.score}",
        "Signals:",
    ]

    for hit in result.positive_hits:
        lines.append(f"✅ {hit}")
    for hit in result.weak_hits:
        lines.append(f"✅ {hit}")
    for hit in result.negative_hits:
        lines.append(f"❌ {hit} (negative signal, score reduced)")
    lines.append("⚠️ verify with documents")

    lines += [
        "",
        "Description:",
        result.excerpt or "—",
        "",
        "Link:",
        ad.url,
    ]
    return "\n".join(lines)


def send_message(cfg: Config, text: str) -> bool:
    """Send a message. In DRY_RUN or without a token, just log it.

    Returns True if the message was actually sent (or simulated).
    """
    if cfg.dry_run:
        logger.info("[DRY_RUN] message not sent:\n%s", text)
        return True
    if not cfg.tg_bot_token or not cfg.tg_chat_id:
        logger.warning("TG_BOT_TOKEN / TG_CHAT_ID are not set — skipping send.")
        return False
    try:
        resp = requests.post(
            API_URL.format(token=cfg.tg_bot_token),
            json={
                "chat_id": cfg.tg_chat_id,
                "text": text,
                "disable_web_page_preview": False,
            },
            timeout=cfg.request_timeout_sec,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False
