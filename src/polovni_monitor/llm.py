"""Optional OpenAI-powered listing analysis.

Given a parsed listing, ask an LLM to judge whether it's worth sending, flag
anything suspicious, and state clearly whether the timing chain/belt
replacement is mentioned.

The whole module is optional: if the ``openai`` package or an API key is
missing, or a request fails, the caller falls back to keyword scoring.

Privacy: the listing text is sent to the configured API provider. Contact
details are already masked by the parser; the full prompt and the raw
response are only logged at DEBUG level.
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
    "You are an expert used-car appraiser helping find a good Citroen — either a "
    "C5 Aircross (SUV) or a C4 / C4 Cactus (compact). First identify which model and "
    "engine the listing is, because the timing-component risk differs:\n"
    "- 1.5 BlueHDi (diesel): uses a timing CHAIN (Serbian 'lanac'), prone to stretch "
    "if neglected.\n"
    "- 1.2 PureTech (petrol, common on C4 / C4 Cactus): uses a WET timing BELT running "
    "in oil (Serbian 'kaiš u ulju' / 'uljni kaiš'), known to disintegrate — replacement "
    "or recent service is a major positive.\n"
    "Whichever applies, evidence that the chain/belt was replaced or recently serviced "
    "matters a lot.\n\n"
    "You are selective but fair. Mark 'worth_sending' true when the car is a solid "
    "buy: reasonable price for its model, year and mileage, decent condition, no "
    "serious red flags. You don't need perfection — use your judgement.\n\n"
    "Key evaluation criteria:\n"
    "- **Price vs. market** (budget up to 13500 EUR): judge against the RIGHT model. "
    "A C5 Aircross (SUV) sits higher: 2021+ under 100k km → fair ~11-13k; 2019-2020 "
    "with 150k+ km → fair ~8-10k. A C4 / C4 Cactus (compact) is cheaper — a comparable "
    "year/mileage typically costs ~2-4k less than the C5 Aircross, so a C4 near 13k is "
    "usually overpriced unless very low mileage / high trim. Noticeably above the "
    "model's band = overpriced.\n"
    "- **Mileage**: Under 100k = good. 100-150k = acceptable if serviced. Over 170k "
    "without documented chain/belt service = high risk.\n"
    "- **Service history**: Documented service or chain/belt replacement = strong "
    "positive. Vague claims with no records = neutral. Known neglect = negative.\n"
    "- **Condition signals**: First owner, no accidents, domestic car = positives. "
    "Accident damage, 'rezervisan', odometer doubts = red flags.\n"
    "- **Equipment**: Shine/Feel/Max trim, EAT8 gearbox, panoramic roof, adaptive "
    "cruise, heated seats = add real value.\n\n"
    "Listings are in Serbian. Analyze the provided listing and reply ONLY with a "
    "JSON object, no prose. Keep all string values in English. Schema: {"
    '"chain_belt_status": "yes"|"no"|"unclear", '
    '"chain_belt_note": string (one sentence on chain/belt evidence, or "not mentioned"), '
    '"worth_sending": boolean (true ONLY if worth serious consideration - '
    'would YOU buy it? strict: chain done or perfect, excellent value, no red flags), '
    '"reasoning": string (2-3 sentences explaining the decision: price/mileage/year '
    "trade-off, equipment, service history, risk factors), "
    '"price_assessment": string (e.g. "fair for mileage", "good for year", "overpriced"'
    '), "value_score": number (1-10: how good is the value at THIS price; 1=poor, '
    '10=excellent), '
    '"risk_level": "low"|"medium"|"high" (likelihood of major issues given available '
    "info), "
    '"suspicious": [string] (red flags; empty list if none), '
    '"highlights": [string] (standout positives; empty list if none)'
    "}"
)


EXPLORE_SYSTEM_PROMPT = (
    "You are an expert used-car appraiser. The listing comes from a broad "
    "price-range search on PolovniAutomobili (Serbia) that is NOT tied to any "
    "particular make or model — the goal is to understand what a buyer can get "
    "for this money and whether THIS specific car is good value.\n\n"
    "Steps:\n"
    "1. Identify the make, model, generation and engine from the title/text.\n"
    "2. Judge the asking price against the typical market for that exact car "
    "(year, mileage, trim) — is it cheap, fair, or overpriced for what it is?\n"
    "3. Note the equipment/options that add or subtract value.\n"
    "4. Flag reliability risks for THIS engine/model where you know them "
    "(e.g. wet timing belt in oil on PSA 1.2 PureTech, DSG/dual-clutch wear, "
    "diesel DPF, etc.) and whether the ad shows relevant service was done.\n"
    "5. Call out anything suspicious (accident damage, odometer doubts, "
    "'rezervisan', import/curbstoning signs).\n\n"
    "Be fair, not perfectionist. Mark 'worth_sending' true when the car is a "
    "genuinely good buy for its price — something you'd flag to a friend.\n\n"
    "Listings are in Serbian. Reply ONLY with a JSON object, no prose. Keep all "
    "string values in English. Schema: {"
    '"chain_belt_status": "yes"|"no"|"unclear" (timing chain/belt service '
    "evidence, or unclear/not applicable), "
    '"chain_belt_note": string (one sentence on timing/reliability evidence, or '
    '"not mentioned"), '
    '"worth_sending": boolean (true only if a genuinely good buy for the money), '
    '"reasoning": string (2-3 sentences: identify the car, then price/mileage/'
    "year/equipment trade-off and risks), "
    '"price_assessment": string (e.g. "cheap for the model", "fair", "overpriced"), '
    '"value_score": number (1-10: value at THIS price; 1=poor, 10=excellent), '
    '"risk_level": "low"|"medium"|"high", '
    '"suspicious": [string] (red flags; empty list if none), '
    '"highlights": [string] (standout positives; empty list if none)'
    "}"
)


@dataclass
class LlmVerdict:
    chain_belt_status: str  # "yes" | "no" | "unclear"
    chain_belt_note: str
    worth_sending: bool
    reasoning: str  # Why send or not
    price_assessment: str  # Fair/overpriced/good value etc
    value_score: int  # 1-10
    risk_level: str  # "low" | "medium" | "high"
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

    risk = str(data.get("risk_level", "medium")).lower().strip()
    if risk not in {"low", "medium", "high"}:
        risk = "medium"

    # Parse value_score as an int, default to 5 (neutral)
    try:
        value_score = int(data.get("value_score", 5))
        value_score = max(1, min(10, value_score))  # Clamp to 1-10
    except (ValueError, TypeError):
        value_score = 5

    return LlmVerdict(
        chain_belt_status=status,
        chain_belt_note=str(data.get("chain_belt_note", "")).strip()
        or "not mentioned in the ad",
        worth_sending=bool(data.get("worth_sending", False)),
        reasoning=str(data.get("reasoning", "")).strip()
        or "No detailed reasoning provided",
        price_assessment=str(data.get("price_assessment", "")).strip()
        or "fair price",
        value_score=value_score,
        risk_level=risk,
        suspicious=_coerce_list(data.get("suspicious")),
        highlights=_coerce_list(data.get("highlights")),
    )


def _build_user_prompt(ad: Ad, score: ScoreResult, deal_reasons: list[str]) -> str:
    desc = ad.description[:MAX_DESC_CHARS]
    return (
        f"Title: {ad.title or '-'}\n"
        f"Price: {ad.price if ad.price is not None else '?'} EUR\n"
        f"Year: {ad.year if ad.year is not None else '?'}\n"
        f"Mileage: {ad.mileage if ad.mileage is not None else '?'} km\n"
        f"Fuel: {ad.fuel or '?'} | Transmission: {ad.transmission or '?'}\n"
        f"Location: {ad.location or '?'}\n"
        f"Keyword pre-scan (score {score.score}): "
        f"strong={score.positive_hits} weak={score.weak_hits} "
        f"negative={score.negative_hits}\n"
        f"Deal heuristic flags: {deal_reasons or 'none'}\n\n"
        f"Listing text (Serbian):\n{desc}"
    )


def analyze_listing(
    client, cfg: Config, ad: Ad, score: ScoreResult,
    deal_reasons: list[str] | None = None,
    system_prompt: str = SYSTEM_PROMPT,
) -> LlmVerdict:
    """Run the LLM analysis. Never raises; returns an 'unavailable' verdict on error.

    ``system_prompt`` selects the appraisal style — the default Citroen-focused
    prompt, or ``EXPLORE_SYSTEM_PROMPT`` for generic price-range surveys.
    """
    user_prompt = _build_user_prompt(ad, score, deal_reasons or [])
    logger.debug(
        "LLM request for %s (model=%s, %d chars of listing text):\n"
        "----- prompt sent to AI -----\n%s\n----- end prompt -----",
        ad.ad_id, cfg.openai_model, min(len(ad.description), MAX_DESC_CHARS),
        user_prompt,
    )
    try:
        resp = client.chat.completions.create(
            model=cfg.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        logger.debug("LLM raw response for %s:\n%s", ad.ad_id, content)
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
            reasoning="LLM analysis failed — falling back to heuristics",
            price_assessment="unknown",
            value_score=5,
            risk_level="medium",
            available=False,
        )
