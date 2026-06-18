"""Optional OpenAI-powered listing analysis.

Given a parsed listing, ask an LLM to judge whether it's worth sending, flag
anything suspicious, and — most importantly — state clearly whether the timing
chain/belt replacement is mentioned (the core question from the task).

The whole module is optional: if the ``openai`` package or an API key is
missing, or a request fails, the caller falls back to keyword scoring.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from .config import Config
from .models import Ad
from .scoring import ScoreResult

logger = logging.getLogger("polovni_monitor.llm")

MAX_DESC_CHARS = 6000  # cap tokens sent to the model

SYSTEM_PROMPT = (
    "You are a careful used-car assistant. The user hunts for Citroen C5 Aircross "
    "(1.5 BlueHDi, which uses a timing CHAIN, Serbian 'lanac') and Citroen C4 / "
    "C4 Cactus (PureTech, which uses a wet timing BELT, Serbian 'kaiš u ulju'). "
    "These engines are known for timing chain/belt failures, so evidence that the "
    "chain/belt was replaced or recently serviced is the single most important "
    "factor. Listings are in Serbian. Analyze the provided listing text and reply "
    "ONLY with a JSON object, no prose. Keep all string values in English. "
    "Schema: {"
    '"chain_belt_status": "yes"|"no"|"unclear" '
    "(yes = text clearly says the chain/belt was replaced/done; no = text says it "
    "was NOT replaced or warns about chain noise/problems; unclear = not mentioned), "
    '"chain_belt_note": string (one short sentence quoting/paraphrasing the evidence, '
    "or 'not mentioned in the ad'), "
    '"worth_sending": boolean (true if this is a promising candidate worth a closer '
    "look), "
    '"summary": string (1-2 sentence overall impression), '
    '"suspicious": [string] (red flags, e.g. vague wording, accident, "rezervisan", '
    "odometer doubts; empty list if none), "
    '"highlights": [string] (notable positives; empty list if none)'
    "}"
)


@dataclass
class LlmVerdict:
    chain_belt_status: str  # "yes" | "no" | "unclear"
    chain_belt_note: str
    worth_sending: bool
    summary: str
    suspicious: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)
    available: bool = True  # False => analysis could not be produced


def is_enabled(cfg: Config) -> bool:
    return bool(cfg.use_llm and cfg.openai_api_key)


def build_client(cfg: Config):
    """Return an OpenAI client, or None if unavailable."""
    if not is_enabled(cfg):
        logger.info(
            "LLM analysis disabled (USE_LLM=%s, api_key=%s).",
            cfg.use_llm, "set" if cfg.openai_api_key else "missing",
        )
        return None
    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("openai package not installed — LLM analysis disabled.")
        return None
    # Pass base_url explicitly. An empty OPENAI_BASE_URL in .env is exported as an
    # empty env var, which the SDK would otherwise read and turn into an invalid
    # protocol-less URL — so fall back to the official default when it's blank.
    base_url = cfg.openai_base_url or "https://api.openai.com/v1"
    client = OpenAI(
        api_key=cfg.openai_api_key,
        timeout=cfg.request_timeout_sec,
        base_url=base_url,
    )
    logger.info("LLM analysis enabled (model=%s, base_url=%s).",
                cfg.openai_model, base_url)
    return client


def _coerce_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def parse_verdict(text: str) -> LlmVerdict:
    """Parse the model's JSON answer into an LlmVerdict (tolerant of noise)."""
    data = json.loads(text)
    status = str(data.get("chain_belt_status", "unclear")).lower().strip()
    if status not in {"yes", "no", "unclear"}:
        status = "unclear"
    return LlmVerdict(
        chain_belt_status=status,
        chain_belt_note=str(data.get("chain_belt_note", "")).strip()
        or "not mentioned in the ad",
        worth_sending=bool(data.get("worth_sending", False)),
        summary=str(data.get("summary", "")).strip(),
        suspicious=_coerce_list(data.get("suspicious")),
        highlights=_coerce_list(data.get("highlights")),
    )


def _build_user_prompt(ad: Ad, score: ScoreResult) -> str:
    desc = ad.description[:MAX_DESC_CHARS]
    return (
        f"Title: {ad.title or '-'}\n"
        f"Price: {ad.price if ad.price is not None else '?'} EUR\n"
        f"Year: {ad.year if ad.year is not None else '?'}\n"
        f"Mileage: {ad.mileage if ad.mileage is not None else '?'} km\n"
        f"Fuel: {ad.fuel or '?'} | Transmission: {ad.transmission or '?'}\n"
        f"Keyword pre-scan (score {score.score}): "
        f"strong={score.positive_hits} weak={score.weak_hits} "
        f"negative={score.negative_hits}\n\n"
        f"Listing text (Serbian):\n{desc}"
    )


def analyze_listing(client, cfg: Config, ad: Ad, score: ScoreResult) -> LlmVerdict:
    """Run the LLM analysis. Never raises; returns an 'unavailable' verdict on error."""
    user_prompt = _build_user_prompt(ad, score)
    logger.info(
        "LLM request for %s (model=%s, %d chars of listing text):\n"
        "----- prompt sent to AI -----\n%s\n----- end prompt -----",
        ad.ad_id, cfg.openai_model, min(len(ad.description), MAX_DESC_CHARS),
        user_prompt,
    )
    try:
        resp = client.chat.completions.create(
            model=cfg.openai_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        content = resp.choices[0].message.content or "{}"
        logger.info("LLM raw response for %s:\n%s", ad.ad_id, content)
        verdict = parse_verdict(content)
        usage = getattr(resp, "usage", None)
        if usage is not None:
            logger.info(
                "LLM tokens for %s: prompt=%s completion=%s total=%s",
                ad.ad_id,
                getattr(usage, "prompt_tokens", "?"),
                getattr(usage, "completion_tokens", "?"),
                getattr(usage, "total_tokens", "?"),
            )
        return verdict
    except Exception as exc:  # network / API / parse — must not crash the bot
        logger.error("LLM analysis failed for %s: %s: %s",
                     ad.ad_id, type(exc).__name__, exc)
        return LlmVerdict(
            chain_belt_status="unclear",
            chain_belt_note="LLM analysis unavailable",
            worth_sending=False,
            summary="",
            available=False,
        )
