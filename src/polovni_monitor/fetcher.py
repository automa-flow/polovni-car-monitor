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
import time
from typing import Protocol

from .config import Config

logger = logging.getLogger("polovni_monitor.fetcher")


class Fetcher(Protocol):
    """Common interface for the page-fetching backends."""

    def get(self, url: str) -> str:
        """Return the fully-rendered HTML for ``url``."""
        ...

    def close(self) -> None:
        """Release any underlying resources (HTTP session / browser)."""
        ...

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Phrases that appear in the <title> of a Cloudflare interstitial (any language
# the site serves). Used to tell "still being verified" from "real page".
_CHALLENGE_TITLE_MARKERS = (
    "just a moment",
    "sačekajte trenutak",
    "sacekajte trenutak",
    "checking your browser",
    "attention required",
    "verifying you are human",
)


class FetchError(RuntimeError):
    """A page could not be fetched cleanly (e.g. Cloudflare never cleared)."""


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
        self._retries = max(1, cfg.fetch_retries)
        self._pw = sync_playwright().start()

        # Persistent profile: the cf_clearance cookie and cache survive between
        # pages and between runs, so most requests skip the Cloudflare challenge
        # entirely — exactly like a normal browser that keeps its cookies.
        profile_dir = cfg.db_path.parent / ".pw-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        self._profile_dir = str(profile_dir)
        self._context = self._launch_context(cfg.playwright_channel or None)

    def _launch_context(self, channel: str | None):
        """Launch a persistent context; fall back to bundled Chromium if the
        requested browser channel (chrome/msedge) is not installed."""
        try:
            return self._pw.chromium.launch_persistent_context(
                self._profile_dir,
                headless=self._cfg.playwright_headless,
                channel=channel,
                user_agent=BROWSER_UA,
                locale="sr-RS",
                viewport={"width": 1366, "height": 900},
                # Hide the headless "navigator.webdriver" automation flag.
                args=["--disable-blink-features=AutomationControlled"],
            )
        except Exception as exc:
            if channel:
                logger.warning(
                    "channel=%s unavailable (%s); falling back to bundled Chromium",
                    channel, exc,
                )
                return self._launch_context(None)
            raise

    def get(self, url: str) -> str:
        """Fetch a fully-rendered page. Raises FetchError if it can't be cleared."""
        last_err: Exception | None = None
        for attempt in range(1, self._retries + 1):
            page = self._context.new_page()
            try:
                try:
                    page.goto(
                        url, wait_until="domcontentloaded", timeout=self._timeout_ms
                    )
                except Exception as exc:  # navigation / timeout
                    last_err = exc
                    logger.warning(
                        "navigation error (attempt %d/%d): %s",
                        attempt, self._retries, exc,
                    )
                    continue

                self._await_clearance(page)
                if self._on_challenge(page):
                    last_err = FetchError("Cloudflare challenge not cleared")
                    logger.warning(
                        "Cloudflare challenge still up (attempt %d/%d) for %s",
                        attempt, self._retries, url,
                    )
                    continue

                # Real page reached — let it settle, then return its HTML.
                try:
                    page.wait_for_load_state("networkidle", timeout=self._timeout_ms)
                except Exception:  # networkidle can time out on chatty pages; ignore
                    pass
                page.wait_for_timeout(self._cfg.page_wait_ms)
                return page.content()
            finally:
                page.close()

        raise FetchError(
            f"could not fetch after {self._retries} attempt(s): {url} "
            f"(last error: {last_err})"
        )

    def _await_clearance(self, page) -> None:
        """Poll until the Cloudflare interstitial is gone (or we run out of time).

        The JS challenge needs several seconds to resolve; a fixed wait is too
        short for some pages. We watch the document <title>, which is the most
        reliable signal — the interstitial title differs from any real page.
        """
        deadline = time.monotonic() + (self._timeout_ms / 1000)
        while time.monotonic() < deadline:
            if not self._on_challenge(page):
                return
            page.wait_for_timeout(1000)
        # Timed out; the caller (get) decides whether to retry or fail.

    @staticmethod
    def _on_challenge(page) -> bool:
        try:
            title = (page.title() or "").lower()
        except Exception:  # page navigating; treat as still on challenge
            return True
        return any(m in title for m in _CHALLENGE_TITLE_MARKERS)

    def close(self) -> None:
        # The browser/context may already be gone (e.g. the visible window was
        # closed mid-run, or it crashed). Closing it again then raises
        # TargetClosedError — swallow it so a clean shutdown never crashes the
        # process with a non-zero exit code.
        try:
            self._context.close()  # persistent context owns the browser
        except Exception as exc:
            logger.warning("Browser context already closed: %s: %s",
                           type(exc).__name__, exc)
        finally:
            try:
                self._pw.stop()
            except Exception as exc:
                logger.warning("Playwright stop failed: %s: %s",
                               type(exc).__name__, exc)


def build_fetcher(cfg: Config) -> Fetcher:
    """Create the fetcher selected by ``cfg.fetch_backend``."""
    if cfg.fetch_backend == "requests":
        logger.info("Fetch backend: requests")
        return RequestsFetcher(cfg)
    logger.info(
        "Fetch backend: playwright (headless=%s, channel=%s, persistent profile)",
        cfg.playwright_headless, cfg.playwright_channel or "chromium",
    )
    return PlaywrightFetcher(cfg)
