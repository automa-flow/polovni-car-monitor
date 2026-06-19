"""Send messages via the Telegram Bot API + message formatting."""
from __future__ import annotations

import html
import logging

import requests

from .config import Config
from .deal import DealResult
from .llm import LlmVerdict
from .models import Ad
from .scoring import ScoreResult

logger = logging.getLogger("polovni_monitor.telegram")

API_URL = "https://api.telegram.org/bot{token}/sendMessage"

_CHAIN_LABEL = {
    "yes": "✅ Timing chain/belt: replaced / serviced",
    "no": "❌ Timing chain/belt: NOT replaced / problem mentioned",
    "unclear": "❓ Timing chain/belt: not mentioned in the ad",
}


def _fmt_int(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _esc(value: object) -> str:
    """HTML-escape a dynamic value for Telegram's HTML parse mode."""
    return html.escape(str(value), quote=False)


def listing_button(url: str) -> dict:
    """An inline keyboard with a single 'Open listing' button."""
    return {"inline_keyboard": [[{"text": "🔗 Open listing", "url": url}]]}


def format_price_drop(ad: Ad, old_price: int, new_price: int) -> str:
    """Notification text for a price drop on a previously-seen listing."""
    pct = (old_price - new_price) / old_price * 100 if old_price else 0.0
    title = _esc(ad.title or "Citroen (no title)")
    return (
        "📉 <b>Price drop</b>\n\n"
        f"<b>{title}</b>\n"
        f"Price: {_fmt_int(old_price)} € → <b>{_fmt_int(new_price)} €</b> "
        f"(−{pct:.0f}%)\n"
        f"Location: {_esc(ad.location or '—')}\n\n"
        f'🔗 <a href="{_esc(ad.url)}">Open on PolovniAutomobili</a>'
    )


def format_message(
    ad: Ad,
    result: ScoreResult,
    tag: str = "new",
    verdict: LlmVerdict | None = None,
    deal: DealResult | None = None,
) -> str:
    """Build the notification text for a listing."""
    if tag == "updated":
        header = "🔁 Updated listing"
    else:
        header = "🚗 Interesting listing found"

    price = f"{_fmt_int(ad.price)} €" if ad.price is not None else "not detected"
    mileage = f"{_fmt_int(ad.mileage)} km" if ad.mileage is not None else "—"

    lines = [
        f"<b>{header}</b>",
        "",
        f"<b>{_esc(ad.title or 'Citroen (no title)')}</b>",
        f"Price: {price}",
        f"Year: {ad.year if ad.year is not None else '—'}",
        f"Mileage: {mileage}",
        f"Fuel: {_esc(ad.fuel or '—')}",
        f"Transmission: {_esc(ad.transmission or '—')}",
        f"Location: {_esc(ad.location or '—')}",
        "",
        f"Score: {result.score}",
        "Signals:",
    ]

    for hit in result.positive_hits:
        lines.append(f"✅ {_esc(hit)}")
    for hit in result.weak_hits:
        lines.append(f"✅ {_esc(hit)}")
    for hit in result.negative_hits:
        lines.append(f"❌ {_esc(hit)} (negative signal, score reduced)")
    lines.append("⚠️ verify with documents")

    # Mandatory chain/belt verdict + AI assessment (when available).
    lines.append("")
    if verdict is not None and verdict.available:
        lines.append(_CHAIN_LABEL.get(verdict.chain_belt_status, _CHAIN_LABEL["unclear"]))
        if verdict.chain_belt_note:
            lines.append(f"   → {_esc(verdict.chain_belt_note)}")
        if verdict.summary:
            lines.append(f"🧠 AI assessment: {_esc(verdict.summary)}")
        for item in verdict.suspicious:
            lines.append(f"⚠️ Suspicious: {_esc(item)}")
        for item in verdict.highlights:
            lines.append(f"✅ Highlight: {_esc(item)}")
    else:
        # No LLM: still answer the mandatory chain question from keyword scan.
        if result.negative_hits:
            lines.append("❌ Timing chain/belt: negative signal in keywords")
        elif result.positive_hits:
            lines.append("✅ Timing chain/belt: keyword match found (verify in text)")
        else:
            lines.append("❓ Timing chain/belt: not detected by keywords")

    # Good-deal signals (price/mileage/year/origin), independent of the chain.
    if deal is not None and deal.reasons:
        lines.append("")
        lines.append(f"💰 Deal score {deal.score}:")
        for item in deal.reasons:
            lines.append(f"   • {_esc(item)}")

    lines += [
        "",
        "Description:",
        _esc(result.excerpt or "—"),
        "",
        f'🔗 <a href="{_esc(ad.url)}">Open on PolovniAutomobili</a>',
    ]
    return "\n".join(lines)


def send_message(cfg: Config, text: str, reply_markup: dict | None = None) -> bool:
    """Send an HTML message. In DRY_RUN or without a token, just log it.

    Returns True if the message was actually sent (or simulated).
    """
    if cfg.dry_run:
        logger.info("[DRY_RUN] message not sent:\n%s", text)
        return True
    if not cfg.tg_bot_token or not cfg.tg_chat_id:
        logger.warning("TG_BOT_TOKEN / TG_CHAT_ID are not set — skipping send.")
        return False
    payload: dict = {
        "chat_id": cfg.tg_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    try:
        resp = requests.post(
            API_URL.format(token=cfg.tg_bot_token),
            json=payload,
            timeout=cfg.request_timeout_sec,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False
