"""Page fetching backends.

Two interchangeable backends behind a tiny common interface:

* ``requests`` — plain HTTP with an identifiable User-Agent. The site's
  Cloudflare protection usually refuses it.
* ``playwright`` — drives an ordinary Chromium/Chrome/Edge that renders the
  page's JavaScript, like opening it yourself. This is the default.

The browser is launched as-is: no stealth patches, no spoofed User-Agent, no
hidden automation flags, no captcha solving. If the site's protection does not
let a page through, the page is skipped and logged — the tool does not try to
get around it.
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
    """A page could not be fetched cleanly (e.g. the site's check never passed)."""


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
    """Real-browser fetcher that renders the page's JavaScript."""

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

        # Persistent profile: cookies and cache survive between pages and runs,
        # like a normal browser that keeps its session. This also means fewer
        # requests overall.
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
                locale="sr-RS",
                viewport={"width": 1366, "height": 900},
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
                    last_err = FetchError("site verification page did not go away")
                    logger.warning(
                        "Verification page still shown (attempt %d/%d) for %s",
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
        """Wait until the Cloudflare interstitial is gone (or we run out of time).

        The interstitial is left to do its own thing; we only watch the document
        <title>, which differs from any real page, to know when to read it.
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
