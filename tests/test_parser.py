from pathlib import Path

from polovni_monitor.parser import parse_ad

FIXTURE = Path(__file__).parent / "fixtures" / "listing_c5.html"


def _ad():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_ad(html, "https://www.polovniautomobili.com/auto-oglasi/28830964/x", "28830964")


def test_parses_structured_fields_from_real_page():
    ad = _ad()
    assert ad.price == 13550
    assert ad.year == 2020
    assert ad.mileage == 146930
    assert ad.fuel == "Dizel"
    assert ad.transmission == "Automatik"


def test_populates_location_from_jsonld():
    # Location must come from the spec/JSON-LD, not be left None as before.
    assert _ad().location == "Novi Sad"


def test_keeps_title_and_description():
    ad = _ad()
    assert ad.title and "C5 Aircross" in ad.title
    assert len(ad.description) > 40
