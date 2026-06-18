"""Page fetching backends.

Two interchangeable backends behind a tiny common interface:

* ``requests`` — fast, but blocked by Cloudflare on PolovniAutomobili.
* ``playwright`` — a real headless Chromium that renders JS and clears the
  standard Cloudflare "Just a moment" challenge, exactly like opening the page
  yourself. This is the default so the bot actually works.

We do NOT solve captchas or bypass protections; we just render the page in a
real browser at a low frequency.
"""
from __future__ import annotations

import logging

from .config import Config

logger = logging.getLogger("polovni_monitor.fetcher")

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Markers of a Cloudflare interstitial that we may still be looking at.
_CHALLENGE_MARKERS = (
    "just a moment",
    "cf-browser-verification",
    "challenge-platform",
    "checking your browser",
)


class RequestsFetcher:
    """Plain HTTP fetcher (kept for completeness / sites without Cloudflare)."""

    def __init__(self, cfg: Config) -> None:
        from . import parser  # local import to avoid a cycle at import time

        self._session = parser.build_session()
        self._timeout = cfg.request_timeout_sec

    def get(self, url: str) -> str:
        resp = self._session.get(url, timeout=self._timeout)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        return resp.text

    def close(self) -> None:
        self._session.close()


class PlaywrightFetcher:
    """Headless-Chromium fetcher that renders JS and clears Cloudflare JS checks."""

    def __init__(self, cfg: Config) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "Playwright is not installed. Run:\n"
                "  pip install playwright\n"
                "  python -m playwright install chromium\n"
                "or set FETCH_BACKEND=requests in .env."
            ) from exc

        self._cfg = cfg
        self._timeout_ms = cfg.request_timeout_sec * 1000
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=cfg.playwright_headless)
        self._context = self._browser.new_context(
            user_agent=BROWSER_UA,
            locale="sr-RS",
            viewport={"width": 1366, "height": 900},
        )

    def get(self, url: str) -> str:
        page = self._context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
            # Give Cloudflare's JS challenge time to resolve and the SPA to render.
            try:
                page.wait_for_load_state("networkidle", timeout=self._timeout_ms)
            except Exception:  # networkidle can time out on chatty pages; ignore
                pass
            page.wait_for_timeout(self._cfg.page_wait_ms)

            html = page.content()
            low = html.lower()
            if any(marker in low for marker in _CHALLENGE_MARKERS):
                # Still on the interstitial: wait once more and re-read.
                page.wait_for_timeout(self._cfg.page_wait_ms)
                html = page.content()
            return html
        finally:
            page.close()

    def close(self) -> None:
        try:
            self._context.close()
            self._browser.close()
        finally:
            self._pw.stop()


def build_fetcher(cfg: Config):
    """Create the fetcher selected by ``cfg.fetch_backend``."""
    if cfg.fetch_backend == "requests":
        logger.info("Fetch backend: requests")
        return RequestsFetcher(cfg)
    logger.info("Fetch backend: playwright (headless=%s)", cfg.playwright_headless)
    return PlaywrightFetcher(cfg)
