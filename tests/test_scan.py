"""End-to-end monitoring pass with a fake fetcher: no network, no Telegram, no LLM."""
from pathlib import Path

from polovni_monitor import main
from polovni_monitor.config import load_config

FIXTURE = Path(__file__).parent / "fixtures" / "listing_synthetic.html"
BASE = "https://www.polovniautomobili.com/auto-oglasi"
SEARCH = f"{BASE}/pretraga?brand=citroen"


class FakeFetcher:
    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str) -> str:
        self.calls.append(url)
        return self.pages[url]

    def close(self) -> None:
        pass


def _results_page(*ad_ids: str) -> str:
    return "".join(f'<a href="{BASE}/{i}/citroen-c5-aircross">x</a>' for i in ad_ids)


def test_first_pass_seeds_then_only_new_listings_are_sent(tmp_path, monkeypatch):
    cfg = load_config()
    cfg.db_path = tmp_path / "ads.db"
    cfg.seed_on_first_run = True
    cfg.request_delay_sec = 0
    cfg.recheck_known_hours = 0

    listing_html = FIXTURE.read_text(encoding="utf-8")
    fake = FakeFetcher({SEARCH: _results_page("100")})
    sent: list[str] = []

    monkeypatch.setattr(main, "load_search_urls", lambda: [SEARCH])
    monkeypatch.setattr(main, "load_explore_urls", lambda: [])
    monkeypatch.setattr(main.fetcher, "build_fetcher", lambda cfg: fake)
    monkeypatch.setattr(main.llm, "build_client", lambda cfg: None)
    monkeypatch.setattr(
        main.telegram, "send_message",
        lambda cfg, text, reply_markup=None: sent.append(text) or True,
    )

    # Pass 1: existing listings are remembered silently, cards are not opened.
    assert main.scan_once(cfg) == 0
    assert sent == []
    assert fake.calls == [SEARCH]

    # Pass 2: one new listing appears; only its card is fetched and sent.
    fake.pages[SEARCH] = _results_page("100", "200")
    fake.pages[f"{BASE}/200/citroen-c5-aircross"] = listing_html
    fake.calls.clear()
    assert main.scan_once(cfg) == 1
    assert fake.calls == [SEARCH, f"{BASE}/200/citroen-c5-aircross"]

    (message,) = sent
    assert "Citroen C5 Aircross" in message
    assert "13 550 €" in message
    # Seller contact details never reach Telegram.
    assert "000-00-00" not in message
    assert "@example.com" not in message

    # Pass 3: nothing new, nothing sent.
    sent.clear()
    assert main.scan_once(cfg) == 0
    assert sent == []
