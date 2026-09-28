from pathlib import Path

from polovni_monitor.parser import extract_ad_links, parse_ad

# Synthetic page that mirrors the real listing markup; all data is fictional.
FIXTURE = Path(__file__).parent / "fixtures" / "listing_synthetic.html"
URL = "https://www.polovniautomobili.com/auto-oglasi/10000000/citroen-c5-aircross"


def _ad():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_ad(html, URL, "10000000")


def test_parses_structured_fields_from_spec_block():
    ad = _ad()
    assert ad.price == 13550
    assert ad.fuel == "Dizel"
    assert ad.transmission == "Automatik"


def test_spec_block_wins_over_decoy_numbers_earlier_on_the_page():
    # The header teaser mentions "2016. godište, 214.000 km" before the specs;
    # whole-page regex would pick those up.
    ad = _ad()
    assert ad.year == 2020
    assert ad.mileage == 146930


def test_populates_location_from_jsonld():
    assert _ad().location == "Novi Sad"


def test_keeps_title_and_description():
    ad = _ad()
    assert ad.title == "Citroen C5 Aircross 1.5 BlueHDi Shine 2020. godište"
    assert "zamenjen lanac" in ad.description
    # Scripts are stripped before text extraction.
    assert "__NOISE__" not in ad.description


def test_description_contact_details_are_masked():
    desc = _ad().description
    assert "000-00-00" not in desc
    assert "+381" not in desc
    assert "@example.com" not in desc
    assert desc.count("[phone]") == 2
    assert "[email]" in desc
    # Dates are not mistaken for phone numbers.
    assert "01.06.2025" in desc


def test_extract_ad_links_dedupes_and_absolutizes():
    html = """
    <a href="/auto-oglasi/111/citroen-c4?tracking=1">A</a>
    <a href="/auto-oglasi/111/citroen-c4">A again</a>
    <a href="https://www.polovniautomobili.com/auto-oglasi/222/citroen-c5">B</a>
    <a href="/auto-oglasi/pretraga?brand=citroen">search, not a listing</a>
    """
    links = dict(extract_ad_links(html, "https://www.polovniautomobili.com/auto-oglasi/pretraga"))
    assert links == {
        "111": "https://www.polovniautomobili.com/auto-oglasi/111/citroen-c4",
        "222": "https://www.polovniautomobili.com/auto-oglasi/222/citroen-c5",
    }
