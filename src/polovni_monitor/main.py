"""CLI and the main monitoring loop."""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
import time

# Support running as `python src/polovni_monitor/main.py`.
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polovni_monitor import db, fetcher, llm, parser, telegram
from polovni_monitor.config import (
    KEYWORDS_FILE,
    Config,
    load_config,
    load_search_urls,
)
from polovni_monitor.scoring import analyze_text, load_keywords
from polovni_monitor.utils import normalize_text, setup_logging

logger = logging.getLogger("polovni_monitor")


def _content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def _collect_ads(cfg: Config, fetch, urls: list[str]) -> dict[str, str]:
    """Walk the results pages and collect unique (ad_id -> url)."""
    found: dict[str, str] = {}
    logger.info("Loading %d search URL(s)...", len(urls))
    for i, surl in enumerate(urls, start=1):
        logger.info("[search %d/%d] %s", i, len(urls), surl)
        try:
            html = fetch.get(surl)
        except Exception as exc:  # network must not crash the whole bot
            logger.error("  -> failed to load results page: %s: %s",
                         type(exc).__name__, exc)
            continue
        links = parser.extract_ad_links(html, surl)
        before = len(found)
        for ad_id, ad_url in links:
            found.setdefault(ad_id, ad_url)
        new_here = len(found) - before
        logger.info(
            "  -> %d link(s) on page, %d new (running total %d)",
            len(links), new_here, len(found),
        )
        time.sleep(cfg.request_delay_sec)
    return found


def scan_once(cfg: Config) -> int:
    """One monitoring pass. Returns the number of notifications sent."""
    urls = load_search_urls()
    if not urls:
        logger.error(
            "No search URLs. Fill in config/search_urls.txt "
            "(see config/search_urls.example.txt)."
        )
        return 0

    keywords = load_keywords(KEYWORDS_FILE if KEYWORDS_FILE.exists() else None)
    conn = db.connect(cfg.db_path)
    db.init_db(conn)
    fetch = fetcher.build_fetcher(cfg)
    llm_client = llm.build_client(cfg)

    try:
        return _scan(cfg, conn, fetch, keywords, llm_client)
    finally:
        fetch.close()
        conn.close()


def _scan(cfg: Config, conn, fetch, keywords, llm_client) -> int:
    seeding = cfg.seed_on_first_run and db.count_ads(conn) == 0

    found = _collect_ads(cfg, fetch, load_search_urls())
    logger.info("Listings found in results: %d", len(found))

    if seeding:
        ts = int(time.time())
        for ad_id, ad_url in found.items():
            db.seed_ad(conn, ad_id, ad_url, None, ts)
        conn.commit()
        logger.info(
            "First run (SEED): remembered %d listings, no notifications sent.",
            len(found),
        )
        return 0

    # Only brand-new listing IDs are fetched. Known IDs are skipped (just
    # refresh last_seen) — this keeps each pass to a handful of requests and
    # greatly reduces Cloudflare friction. Trade-off: we no longer re-notify
    # when an existing listing's description changes.
    ts = int(time.time())
    new_listings: dict[str, str] = {}
    for ad_id, ad_url in found.items():
        if db.get_ad(conn, ad_id) is None:
            new_listings[ad_id] = ad_url
        else:
            db.touch_ad(conn, ad_id, ts)
    conn.commit()
    logger.info(
        "%d known listing(s) skipped (no re-fetch); %d new to analyze.",
        len(found) - len(new_listings), len(new_listings),
    )

    notified = 0
    examined = 0
    total = len(new_listings)
    for idx, (ad_id, ad_url) in enumerate(new_listings.items(), start=1):
        logger.info("[%d/%d] Analyzing NEW listing %s", idx, total, ad_id)
        try:
            html = fetch.get(ad_url)
        except Exception as exc:
            logger.error("  -> failed to load listing %s: %s: %s",
                         ad_id, type(exc).__name__, exc)
            time.sleep(cfg.request_delay_sec)
            continue

        examined += 1
        ad = parser.parse_ad(html, ad_url, ad_id)
        result = analyze_text(f"{ad.description}\n{ad.title or ''}", keywords)
        chash = _content_hash(ad.description)
        price_ok = ad.price is None or ad.price <= cfg.price_to_eur

        logger.info(
            "  parsed: %s | price=%s year=%s mileage=%s fuel=%s trans=%s",
            (ad.title or "—")[:70],
            f"{ad.price} EUR" if ad.price is not None else "?",
            ad.year if ad.year is not None else "?",
            f"{ad.mileage} km" if ad.mileage is not None else "?",
            ad.fuel or "?",
            ad.transmission or "?",
        )
        logger.info(
            "  score=%d (min=%d) | strong=%s weak=%s negative=%s",
            result.score, cfg.min_score_to_notify,
            result.positive_hits, result.weak_hits, result.negative_hits,
        )
        if result.negative_hits:
            logger.info("  ! negative signals present, score was reduced")

        # --- LLM analysis ---
        verdict = None
        if llm_client is not None:
            logger.info("  running LLM analysis (model=%s)...", cfg.openai_model)
            verdict = llm.analyze_listing(llm_client, cfg, ad, result)
            if verdict.available:
                logger.info(
                    "  LLM: chain/belt=%s | worth_sending=%s | %s",
                    verdict.chain_belt_status, verdict.worth_sending,
                    verdict.summary or "(no summary)",
                )
                if verdict.suspicious:
                    logger.info("  LLM suspicious: %s", verdict.suspicious)
                if verdict.highlights:
                    logger.info("  LLM highlights: %s", verdict.highlights)

        # If the LLM was supposed to run but couldn't (API error / quota), do
        # NOT consume this listing — leave it unrecorded so it is retried on the
        # next pass once the LLM is reachable again. Avoids "burning" listings
        # during an outage.
        if llm_client is not None and (verdict is None or not verdict.available):
            logger.warning(
                "  => defer: LLM unavailable, not recording %s (will retry next pass)",
                ad_id,
            )
            time.sleep(cfg.request_delay_sec)
            continue

        # --- Gate: decide whether to send ---
        use_llm = verdict is not None and verdict.available
        if not price_ok:
            send, reason = False, (
                f"price {ad.price} EUR above PRICE_TO_EUR={cfg.price_to_eur}"
            )
        elif use_llm and not verdict.worth_sending:
            send, reason = False, f"LLM verdict: not worth sending ({verdict.summary})"
        elif not use_llm and result.score < cfg.min_score_to_notify:
            send, reason = False, (
                f"keyword score {result.score} below "
                f"MIN_SCORE_TO_NOTIFY={cfg.min_score_to_notify}"
            )
        else:
            send, reason = True, (
                "LLM says worth sending" if use_llm else "keyword score OK"
            )

        db.save_ad(
            conn, ad_id, ad_url, ad.title, ts, chash, result.score,
            notified=1 if send else 0,
        )

        if send:
            logger.info("  => SEND to Telegram: %s", reason)
            text = telegram.format_message(ad, result, "new", verdict)
            if telegram.send_message(cfg, text):
                notified += 1
                logger.info("  => notification delivered")
            else:
                logger.warning("  => Telegram send failed")
        else:
            logger.info("  => skip: %s", reason)

        time.sleep(cfg.request_delay_sec)

    conn.commit()
    logger.info(
        "Pass complete. New listings examined: %d, notifications sent: %d.",
        examined, notified,
    )
    return notified


def run_forever(cfg: Config) -> None:
    interval = max(1, cfg.check_interval_min) * 60
    logger.info(
        "Monitoring started, interval %d min. Press Ctrl+C to stop.",
        cfg.check_interval_min,
    )
    try:
        while True:
            try:
                scan_once(cfg)
            except Exception as exc:  # a single failure must not kill the loop
                logger.exception("Error during monitoring pass: %s", exc)
            logger.info("Next check in %d min.", cfg.check_interval_min)
            time.sleep(interval)
    except KeyboardInterrupt:
        # scan_once() closes the browser and DB via its own finally block.
        logger.info("Stop requested (Ctrl+C). Shutting down cleanly.")


def cmd_test_telegram(cfg: Config) -> int:
    ok = telegram.send_message(
        cfg, "✅ Test message from polovni-car-monitor."
    )
    if ok:
        logger.info("Test message processed successfully.")
        return 0
    logger.error("Failed to send the test message.")
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polovni_monitor",
        description="Personal monitor for PolovniAutomobili listings.",
    )
    sub = p.add_subparsers(dest="command")
    sub.add_parser("run", help="Continuous monitoring.")
    sub.add_parser("scan-once", help="A single pass, then exit.")
    sub.add_parser("test-telegram", help="Send a test message to Telegram.")
    return p


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    args = build_parser().parse_args(argv)
    cfg = load_config()

    command = args.command or "run"
    try:
        if command == "run":
            run_forever(cfg)
            return 0
        if command == "scan-once":
            scan_once(cfg)
            return 0
        if command == "test-telegram":
            return cmd_test_telegram(cfg)
    except KeyboardInterrupt:
        # Interrupt during a single scan; resources are released in scan_once.
        logger.info("Interrupted by user (Ctrl+C). Exiting.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
