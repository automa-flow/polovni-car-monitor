"""Fetch and parse PolovniAutomobili pages.

Only basic listing data: link, title, price, year, mileage, fuel,
transmission, location, and the description text. No seller contacts / phone
numbers.

Structured fields (year/mileage/fuel/transmission) are read from the listing's
labeled spec block first ("Godište: 2020.", "Kilometraža: 146.930 km", …), and
location from JSON-LD / the seller-city block, falling back to whole-page regex
only when a labeled value is missing — so a stray number from a sidebar or
footer is not mistaken for the listing's own data.
"""
from __future__ import annotations

import json
import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import Ad
from .utils import normalize_text

logger = logging.getLogger("polovni_monitor.parser")

USER_AGENT = (
    "Mozilla/5.0 (compatible; personal-car-monitor/0.1; low-frequency personal use)"
)

# /auto-oglasi/{id}/...slug...
AD_LINK_RE = re.compile(r"/auto-oglasi/(\d+)/[^\"'\s?#<>]+")
# 13.500 € | 13500 € | 13 500 €
PRICE_RE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})+|\d{3,6})\s*€")
# 162.000 km | 162000 km | 162 000 km
MILEAGE_RE = re.compile(r"(\d{1,3}(?:[.\s]\d{3})+|\d{3,7})\s*km", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19[89]\d|20[0-2]\d)\b")

# Spec-block lookups run on normalized (lowercase, diacritic-free) text where
# "Godište\n:\n2020." collapses to "godiste : 2020.".
SPEC_YEAR_RE = re.compile(r"godiste\s*:?\s*((?:19|20)\d{2})")
SPEC_MILEAGE_RE = re.compile(
    r"kilometraza\s*:?\s*(\d{1,3}(?:[.\s]\d{3})+|\d{3,7})\s*km"
)
SPEC_FUEL_RE = re.compile(r"gorivo\s*:?\s*([a-z()/ +-]{2,30})")
SPEC_TRANS_RE = re.compile(r"menjac\s*:?\s*([a-z/ ]{2,40})")

FUEL_KEYWORDS = {
    "dizel": "Dizel",
    "benzin": "Benzin",
    "hibrid": "Hibrid",
    "elektro": "Elektro",
    "tng": "TNG",
    "metan": "Metan (CNG)",
}


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept-Language": "sr,en;q=0.8",
        }
    )
    return session


def extract_ad_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Extract unique (ad_id, url) listings from a results page."""
    results: dict[str, str] = {}
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        m = AD_LINK_RE.search(a["href"])
        if m:
            ad_id = m.group(1)
            clean = a["href"].split("?")[0]
            results.setdefault(ad_id, urljoin(base_url, clean))
    # fallback pass over raw html (for links not in <a> tags)
    for m in AD_LINK_RE.finditer(html):
        ad_id = m.group(1)
        if ad_id not in results:
            results[ad_id] = urljoin(base_url, m.group(0).split("?")[0])
    return list(results.items())


def _to_int(raw: str) -> int:
    return int(re.sub(r"\D", "", raw))


def parse_price(text: str) -> int | None:
    """Find the price in EUR. Returns an int or None."""
    m = PRICE_RE.search(text)
    if not m:
        return None
    try:
        return _to_int(m.group(1))
    except ValueError:
        return None


def parse_mileage(text: str) -> int | None:
    m = MILEAGE_RE.search(text)
    if not m:
        return None
    try:
        return _to_int(m.group(1))
    except ValueError:
        return None


def parse_year(text: str) -> int | None:
    m = YEAR_RE.search(text)
    return int(m.group(1)) if m else None


def _detect_fuel(norm: str) -> str | None:
    for key, label in FUEL_KEYWORDS.items():
        if key in norm:
            return label
    return None


def _detect_transmission(norm: str) -> str | None:
    if "automat" in norm:
        return "Automatik"
    if "manuel" in norm or "manual" in norm:
        return "Manuelni"
    return None


def _spec_year(norm: str) -> int | None:
    m = SPEC_YEAR_RE.search(norm)
    return int(m.group(1)) if m else None


def _spec_mileage(norm: str) -> int | None:
    m = SPEC_MILEAGE_RE.search(norm)
    if not m:
        return None
    try:
        return _to_int(m.group(1))
    except ValueError:
        return None


def _spec_fuel(norm: str) -> str | None:
    m = SPEC_FUEL_RE.search(norm)
    return _detect_fuel(m.group(1)) if m else None


def _spec_transmission(norm: str) -> str | None:
    m = SPEC_TRANS_RE.search(norm)
    return _detect_transmission(m.group(1)) if m else None


def _iter_jsonld(soup: BeautifulSoup):
    """Yield each JSON-LD object on the page (flattening top-level lists).

    Must run before scripts are stripped from the soup.
    """
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in data if isinstance(data, list) else [data]:
            if isinstance(obj, dict):
                yield obj


def _extract_location(soup: BeautifulSoup) -> str | None:
    """Seller city, e.g. 'Novi Sad'. Prefer JSON-LD ``address.addressLocality``
    (reliable for dealers), then the seller-city block (class is a dynamic hash,
    so match on the stable 'SellerCity' component-name fragment)."""
    for obj in _iter_jsonld(soup):
        addr = obj.get("address")
        if isinstance(addr, dict):
            loc = addr.get("addressLocality")
            if loc and str(loc).strip():
                return str(loc).strip()
    for selector in ("[class*=SellerCity]", "[class*=SellerLocation]", "[class*=Location]"):
        node = soup.select_one(selector)
        if node:
            txt = node.get_text(" ", strip=True)
            if txt and len(txt) < 60:
                return txt
    return None


def _extract_description(soup: BeautifulSoup, visible: str) -> str:
    """Return the listing's "Opis" (description) block, else all visible text.

    PolovniAutomobili renders the description right after an <h2>Opis</h2>
    heading, inside styled-components containers whose class names are dynamic
    hashes. We therefore anchor on the heading text (stable) rather than class
    names, with a couple of class-hint fallbacks.
    """
    # 1) Anchor on the "Opis" heading and take the block right after it.
    for heading in soup.find_all(re.compile(r"^h[1-4]$")):
        if heading.get_text(strip=True).lower() == "opis":
            sib = heading.find_next_sibling()
            if sib:
                txt = sib.get_text(" ", strip=True)
                if len(txt) > 40:
                    return txt

    # 2) Class-name hints (component names tend to survive across deploys).
    for selector in (
        "[class*=InfoCardText]",
        "[class*=InfoCardList]",
        "#description",
        ".description",
        "[class*=description]",
        "[id*=opis]",
    ):
        node = soup.select_one(selector)
        if node:
            txt = node.get_text(" ", strip=True)
            if len(txt) > 40:
                return txt

    # 3) Fallback: the whole visible text (noisy, but never empty).
    return visible


def parse_ad(html: str, url: str, ad_id: str) -> Ad:
    """Parse a listing card."""
    soup = BeautifulSoup(html, "html.parser")

    title: str | None = None
    if soup.title and soup.title.get_text(strip=True):
        title = soup.title.get_text(strip=True)
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        title = h1.get_text(strip=True)

    # Location is read first — it relies on JSON-LD <script> tags that the
    # cleanup pass below removes.
    location = _extract_location(soup)

    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    visible = soup.get_text(" ", strip=True)

    description = _extract_description(soup, visible)
    norm_visible = normalize_text(visible)

    # Prefer the labeled spec block; fall back to whole-page regex.
    year = _spec_year(norm_visible)
    mileage = _spec_mileage(norm_visible)
    fuel = _spec_fuel(norm_visible)
    transmission = _spec_transmission(norm_visible)

    return Ad(
        ad_id=ad_id,
        url=url,
        title=title,
        price=parse_price(visible),
        year=year if year is not None else parse_year(visible),
        mileage=mileage if mileage is not None else parse_mileage(visible),
        fuel=fuel if fuel is not None else _detect_fuel(norm_visible),
        transmission=transmission
        if transmission is not None
        else _detect_transmission(norm_visible),
        location=location,
        description=description,
    )
