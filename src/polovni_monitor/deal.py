"""Combined-attractiveness ("good deal") heuristic.

Independent of the timing chain/belt keyword scoring. A car can still be worth
sending even without chain evidence if the overall package is strong: great
price, low mileage, recent year, first owner / domestic origin, etc.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .models import Ad

# Origin / ownership phrases (normalized, diacritics-free) and their points.
_ORIGIN_HINTS = {
    "prvi vlasnik": (1, "first owner"),
    "kupljen u srbiji": (1, "bought in Serbia"),
    "domace vozilo": (1, "domestic car"),
    "domaci auto": (1, "domestic car"),
}


@dataclass
class DealResult:
    score: int = 0
    reasons: list[str] = field(default_factory=list)


def evaluate_deal(ad: Ad, cfg: Config, norm_text: str = "") -> DealResult:
    """Score a listing on objective attributes (price/mileage/year/origin)."""
    score = 0
    reasons: list[str] = []

    if ad.price is not None and ad.price <= cfg.deal_price_eur:
        score += 2
        reasons.append(f"great price ({ad.price} ≤ {cfg.deal_price_eur} EUR)")

    if ad.mileage is not None:
        very_low = int(cfg.deal_mileage_km * 0.75)
        if ad.mileage <= very_low:
            score += 2
            reasons.append(f"very low mileage ({ad.mileage} km)")
        elif ad.mileage <= cfg.deal_mileage_km:
            score += 1
            reasons.append(f"low mileage ({ad.mileage} km)")

    if ad.year is not None and ad.year >= cfg.deal_year_from:
        score += 1
        reasons.append(f"recent year ({ad.year})")

    seen_origin: set[str] = set()
    for phrase, (pts, label) in _ORIGIN_HINTS.items():
        if phrase in norm_text and label not in seen_origin:
            score += pts
            reasons.append(label)
            seen_origin.add(label)

    return DealResult(score=score, reasons=reasons)
