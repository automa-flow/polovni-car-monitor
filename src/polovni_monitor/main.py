"""CLI and the main monitoring loop."""
from __future__ import annotations

import argparse
import csv
import hashlib
import logging
import time
from datetime import datetime
from pathlib import Path

from polovni_monitor import db, deal, fetcher, llm, parser, telegram
from polovni_monitor.config import (
    EXPORT_PATH,
    KEYWORDS_FILE,
    Config,
    load_config,
    load_explore_urls,
    load_search_urls,
)
from polovni_monitor.scoring import ScoreResult, analyze_text, load_keywords
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
    model_urls = load_search_urls()
    explore_urls = load_explore_urls()
    if not model_urls and not explore_urls:
        logger.error(
            "No search URLs. Fill in config/search_urls.txt and/or "
            "config/explore_urls.txt "
            "(see the matching *.example.txt files)."
        )
        return 0

    keywords = load_keywords(KEYWORDS_FILE if KEYWORDS_FILE.exists() else None)
    conn = db.connect(cfg.db_path)
    db.init_db(conn)
    fetch = fetcher.build_fetcher(cfg)
    llm_client = llm.build_client(cfg)

    try:
        notified = 0
        if model_urls:
            notified += _scan(cfg, conn, fetch, keywords, llm_client, model_urls)
        if explore_urls:
            notified += _scan_explore(cfg, conn, fetch, llm_client, explore_urls)
        return notified
    finally:
        fetch.close()
        conn.close()


def _scan(cfg: Config, conn, fetch, keywords, llm_client, urls: list[str]) -> int:
    seeding = cfg.seed_on_first_run and db.count_ads(conn) == 0

    found = _collect_ads(cfg, fetch, urls)
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

    # Brand-new listing IDs are fully analyzed. Known IDs are normally skipped
    # (just refresh last_seen) to keep each pass to a handful of requests and
    # the load on the site low — except those due for a price re-check, which
    # are re-fetched to detect price drops.
    ts = int(time.time())
    new_listings: dict[str, str] = {}
    recheck_due: list[tuple[str, str, object]] = []
    for ad_id, ad_url in found.items():
        existing = db.get_ad(conn, ad_id)
        if existing is None:
            new_listings[ad_id] = ad_url
        elif _due_for_recheck(existing, cfg, ts):
            recheck_due.append((ad_id, ad_url, existing))
        else:
            db.touch_ad(conn, ad_id, ts)
    conn.commit()
    logger.info(
        "%d known listing(s) skipped; %d due for price re-check; %d new to analyze.",
        len(found) - len(new_listings) - len(recheck_due),
        len(recheck_due), len(new_listings),
    )

    notified = _recheck_known_prices(cfg, conn, fetch, recheck_due, ts)

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

        logger.info(
            "  parsed: %s | price=%s year=%s mileage=%s fuel=%s trans=%s",
            (ad.title or "—")[:70],
            f"{ad.price} EUR" if ad.price is not None else "?",
            ad.year if ad.year is not None else "?",
            f"{ad.mileage} km" if ad.mileage is not None else "?",
            ad.fuel or "?",
            ad.transmission or "?",
        )

        result = analyze_text(f"{ad.description}\n{ad.title or ''}", keywords)
        chash = _content_hash(ad.description)
        price_ok = ad.price is None or ad.price <= cfg.price_to_eur
        logger.info(
            "  score=%d (min=%d) | strong=%s weak=%s negative=%s",
            result.score, cfg.min_score_to_notify,
            result.positive_hits, result.weak_hits, result.negative_hits,
        )
        if result.negative_hits:
            logger.info("  ! negative signals present, score was reduced")

        # --- Good-deal heuristic (price / mileage / year / origin) ---
        norm_text = normalize_text(f"{ad.description}\n{ad.title or ''}")
        deal_result = deal.evaluate_deal(ad, cfg, norm_text)
        if deal_result.reasons:
            logger.info("  deal score=%d (min=%d): %s",
                        deal_result.score, cfg.deal_min_score, deal_result.reasons)

        # --- LLM analysis ---
        verdict = None
        if llm_client is not None:
            logger.info("  running LLM analysis (model=%s)...", cfg.openai_model)
            verdict = llm.analyze_listing(
                llm_client, cfg, ad, result, deal_result.reasons
            )
            if verdict.available:
                logger.info(
                    "  LLM: chain/belt=%s | worth_sending=%s | value=%d/10 | risk=%s",
                    verdict.chain_belt_status, verdict.worth_sending,
                    verdict.value_score, verdict.risk_level,
                )
                logger.info("  LLM reasoning: %s", verdict.reasoning)
                logger.info("  LLM price: %s", verdict.price_assessment)
                if verdict.suspicious:
                    logger.info("  LLM suspicious: %s", verdict.suspicious)
                if verdict.highlights:
                    logger.info("  LLM highlights: %s", verdict.highlights)

        # Heuristic worthiness that does not need the LLM.
        keyword_ok = result.score >= cfg.min_score_to_notify
        deal_ok = deal_result.score >= cfg.deal_min_score
        base_worth = price_ok and (keyword_ok or deal_ok)

        # If the LLM was supposed to run but couldn't (API error / quota):
        #  - if a heuristic already marks it worth, send anyway (AI noted as down);
        #  - otherwise defer (don't record) so it's retried once the LLM is back.
        if llm_client is not None and (verdict is None or not verdict.available):
            if not base_worth:
                logger.warning(
                    "  => defer: LLM unavailable and no keyword/deal signal — "
                    "not recording %s (will retry next pass)", ad_id,
                )
                time.sleep(cfg.request_delay_sec)
                continue
            logger.warning("  LLM unavailable; proceeding on heuristics only")

        # --- Every new listing is sent; the genuinely interesting ones are
        # flagged. Price is not a hard filter — over-budget cars are still sent,
        # just never flagged as "interesting" (don't-miss). Interesting requires
        # the price to be within budget AND a positive signal.
        use_llm = verdict is not None and verdict.available
        interesting = False

        if not price_ok:
            reason = f"over budget ({ad.price} EUR > {cfg.price_to_eur}) — informational"
        elif use_llm and verdict is not None:
            summary = f"value {verdict.value_score}/10, {verdict.risk_level} risk"
            if verdict.worth_sending:
                interesting = True
                reason = f"LLM: worth sending ({summary})"
            else:
                reason = f"LLM: not compelling ({summary})"
        elif keyword_ok:
            interesting = True
            reason = f"strong keyword signal (score {result.score})"
        elif deal_ok:
            interesting = True
            reason = "good deal: " + ", ".join(deal_result.reasons)
        else:
            reason = "informational"

        db.save_ad(
            conn, ad_id, ad_url, ad.title, ts, chash, result.score,
            notified=1, price=ad.price,
        )

        logger.info("  => SEND to Telegram: %s%s", reason,
                    " (INTERESTING)" if interesting else "")
        text = telegram.format_message(
            ad, result, "new", verdict, deal_result, interesting=interesting
        )
        if telegram.send_message(cfg, text, telegram.listing_button(ad_url)):
            notified += 1
            logger.info("  => notification delivered")
        else:
            logger.warning("  => Telegram send failed")

        time.sleep(cfg.request_delay_sec)

    db.set_meta(conn, "last_pass_ts", str(ts))
    conn.commit()
    logger.info(
        "Pass complete. New listings examined: %d, notifications sent: %d.",
        examined, notified,
    )
    return notified


def _explore_excerpt(description: str, radius: int = 220) -> str:
    """A short, normalized snippet of the listing text for the Telegram message."""
    snippet = normalize_text(description).strip()
    if len(snippet) > radius:
        snippet = snippet[:radius].rstrip() + "…"
    return snippet


def _scan_explore(cfg: Config, conn, fetch, llm_client, urls: list[str]) -> int:
    """Price-range survey pass (not tied to a make/model).

    Mirrors the seed-then-notify behaviour of the model scan, but with its own
    independent first-run flag (``explore_seeded`` in meta) so adding explore
    URLs to an already-populated database doesn't flood Telegram. On the first
    pass every listing is recorded silently; afterwards each newly appeared
    listing gets a generic LLM appraisal and is posted.
    """
    logger.info("=== Explore (price-range) pass ===")
    found = _collect_ads(cfg, fetch, urls)
    logger.info("Explore: listings found in results: %d", len(found))
    if not found:
        return 0

    # The explore pass always seeds on its first run (independent of the global
    # SEED_ON_FIRST_RUN flag): record everything silently, then only post
    # newly-appeared listings on later passes. This avoids flooding Telegram
    # when broad price-range URLs first match hundreds of cars.
    ts = int(time.time())
    seeded = db.get_meta(conn, "explore_seeded")
    if not seeded:
        for ad_id, ad_url in found.items():
            db.seed_ad(conn, ad_id, ad_url, None, ts)
        db.set_meta(conn, "explore_seeded", "1")
        conn.commit()
        logger.info(
            "Explore first run (SEED): remembered %d listings, no notifications sent.",
            len(found),
        )
        return 0

    new_listings: dict[str, str] = {}
    for ad_id, ad_url in found.items():
        if db.get_ad(conn, ad_id) is None:
            new_listings[ad_id] = ad_url
        else:
            db.touch_ad(conn, ad_id, ts)
    conn.commit()
    logger.info(
        "Explore: %d known listing(s) skipped; %d new to appraise.",
        len(found) - len(new_listings), len(new_listings),
    )

    notified = 0
    total = len(new_listings)
    for idx, (ad_id, ad_url) in enumerate(new_listings.items(), start=1):
        logger.info("[explore %d/%d] Appraising NEW listing %s", idx, total, ad_id)
        try:
            html = fetch.get(ad_url)
        except Exception as exc:
            logger.error("  -> failed to load listing %s: %s: %s",
                         ad_id, type(exc).__name__, exc)
            time.sleep(cfg.request_delay_sec)
            continue

        ad = parser.parse_ad(html, ad_url, ad_id)
        logger.info(
            "  parsed: %s | price=%s year=%s mileage=%s fuel=%s trans=%s",
            (ad.title or "—")[:70],
            f"{ad.price} EUR" if ad.price is not None else "?",
            ad.year if ad.year is not None else "?",
            f"{ad.mileage} km" if ad.mileage is not None else "?",
            ad.fuel or "?", ad.transmission or "?",
        )

        result = ScoreResult(score=0, excerpt=_explore_excerpt(ad.description))
        chash = _content_hash(ad.description)

        verdict = None
        if llm_client is not None:
            logger.info("  running explore LLM appraisal (model=%s)...", cfg.openai_model)
            verdict = llm.analyze_listing(
                llm_client, cfg, ad, result,
                system_prompt=llm.EXPLORE_SYSTEM_PROMPT,
            )
            if verdict.available:
                logger.info(
                    "  LLM: worth_sending=%s | value=%d/10 | risk=%s | %s",
                    verdict.worth_sending, verdict.value_score,
                    verdict.risk_level, verdict.price_assessment,
                )
                logger.info("  LLM reasoning: %s", verdict.reasoning)
            else:
                logger.warning("  LLM unavailable; sending without appraisal")

        # Record before sending so a crash mid-send doesn't re-post next pass.
        db.save_ad(
            conn, ad_id, ad_url, ad.title, ts, chash, 0,
            notified=1, price=ad.price,
        )

        text = telegram.format_message(ad, result, "new", verdict, explore=True)
        if telegram.send_message(cfg, text, telegram.listing_button(ad_url)):
            notified += 1
            logger.info("  => notification delivered")
        else:
            logger.warning("  => Telegram send failed")

        conn.commit()
        time.sleep(cfg.request_delay_sec)

    db.set_meta(conn, "explore_last_pass_ts", str(ts))
    conn.commit()
    logger.info(
        "Explore pass complete. New listings appraised: %d, notifications sent: %d.",
        total, notified,
    )
    return notified


def _due_for_recheck(existing, cfg: Config, now_ts: int) -> bool:
    """Whether a known listing should be re-fetched to check for a price drop."""
    if cfg.recheck_known_hours <= 0:
        return False
    last_checked = existing["price_checked_ts"] or existing["first_seen_ts"]
    return (now_ts - last_checked) >= cfg.recheck_known_hours * 3600


def _recheck_known_prices(cfg: Config, conn, fetch, recheck_due, ts: int) -> int:
    """Re-fetch listings due for a price check; notify on a meaningful drop.

    Returns the number of price-drop notifications sent.
    """
    notified = 0
    total = len(recheck_due)
    for idx, (ad_id, ad_url, existing) in enumerate(recheck_due, start=1):
        logger.info("[recheck %d/%d] known listing %s", idx, total, ad_id)
        try:
            html = fetch.get(ad_url)
        except Exception as exc:
            logger.error("  -> re-check fetch failed for %s: %s: %s",
                         ad_id, type(exc).__name__, exc)
            db.touch_ad(conn, ad_id, ts)
            time.sleep(cfg.request_delay_sec)
            continue

        ad = parser.parse_ad(html, ad_url, ad_id)
        old_price = existing["last_price"]
        new_price = ad.price
        logger.info("  price: old=%s new=%s", old_price, new_price)

        if new_price is not None and old_price is not None and new_price < old_price:
            drop_eur = old_price - new_price
            drop_pct = drop_eur / old_price * 100
            if drop_eur >= cfg.price_drop_min_eur or drop_pct >= cfg.price_drop_min_pct:
                logger.info("  => price drop %s -> %s (−%.0f%%), notifying",
                            old_price, new_price, drop_pct)
                text = telegram.format_price_drop(ad, old_price, new_price)
                if telegram.send_message(cfg, text, telegram.listing_button(ad_url)):
                    notified += 1

        # Keep the last known price if the page didn't yield one this time.
        db.update_price(conn, ad_id, new_price if new_price is not None else old_price, ts)
        conn.commit()
        time.sleep(cfg.request_delay_sec)
    return notified


def _interval_minutes(cfg: Config) -> int:
    """Polling interval for the current local time (slower at night)."""
    hour = datetime.now().hour
    start, end = cfg.night_start_hour, cfg.night_end_hour
    if start <= end:
        is_night = start <= hour < end
    else:  # window wraps past midnight, e.g. 23 -> 7
        is_night = hour >= start or hour < end
    return cfg.night_interval_min if is_night else cfg.check_interval_min


def _maybe_send_heartbeat(cfg: Config) -> None:
    """Once a day (on/after HEARTBEAT_HOUR local) send a short status summary."""
    if cfg.heartbeat_hour < 0:
        return
    now = datetime.now()
    if now.hour < cfg.heartbeat_hour:
        return
    today = now.strftime("%Y-%m-%d")
    conn = db.connect(cfg.db_path)
    db.init_db(conn)
    try:
        if db.get_meta(conn, "heartbeat_date") == today:
            return  # already sent today
        total = db.count_ads(conn)
        notified_24h = db.count_notified_since(conn, int(time.time()) - 24 * 3600)
        last_pass = db.get_meta(conn, "last_pass_ts")
        when = (
            datetime.fromtimestamp(int(last_pass)).strftime("%Y-%m-%d %H:%M")
            if last_pass
            else "—"
        )
        text = (
            "💟 <b>Monitor heartbeat</b>\n\n"
            f"Listings tracked: {total}\n"
            f"Notified (last 24h): {notified_24h}\n"
            f"Last pass: {when}"
        )
        if telegram.send_message(cfg, text):
            db.set_meta(conn, "heartbeat_date", today)
            conn.commit()
            logger.info("Heartbeat sent.")
    finally:
        conn.close()


def run_forever(cfg: Config) -> None:
    logger.info(
        "Monitoring started (day=%d min; night=%d min between %02d:00-%02d:00 local). "
        "Press Ctrl+C to stop.",
        cfg.check_interval_min, cfg.night_interval_min,
        cfg.night_start_hour, cfg.night_end_hour,
    )
    try:
        while True:
            try:
                scan_once(cfg)
                _maybe_send_heartbeat(cfg)
            except Exception as exc:  # a single failure must not kill the loop
                logger.exception("Error during monitoring pass: %s", exc)
            mins = max(1, _interval_minutes(cfg))
            logger.info("Next check in %d min.", mins)
            time.sleep(mins * 60)
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


def cmd_export(cfg: Config, path: Path) -> int:
    """Write all notified listings to a CSV file."""
    conn = db.connect(cfg.db_path)
    db.init_db(conn)
    try:
        rows = db.iter_notified(conn)
    finally:
        conn.close()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["ad_id", "title", "price_eur", "score", "first_seen", "url"])
        for row in rows:
            first_seen = datetime.fromtimestamp(row["first_seen_ts"]).strftime(
                "%Y-%m-%d %H:%M"
            )
            writer.writerow([
                row["ad_id"], row["title"] or "", row["last_price"] or "",
                row["last_score"], first_seen, row["url"],
            ])
    logger.info("Exported %d listing(s) to %s", len(rows), path)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="polovni-monitor",
        description="Personal, low-frequency monitor for PolovniAutomobili listings (unofficial).",
    )
    sub = p.add_subparsers(dest="command")
    sub.add_parser("run", help="Continuous monitoring.")
    sub.add_parser("scan-once", help="A single pass, then exit.")
    sub.add_parser("test-telegram", help="Send a test message to Telegram.")
    exp = sub.add_parser("export", help="Export notified listings to CSV.")
    exp.add_argument("--path", type=Path, default=EXPORT_PATH,
                     help=f"Output CSV path (default: {EXPORT_PATH}).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config()
    setup_logging(level=cfg.log_level, log_file=cfg.log_file)

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
        if command == "export":
            return cmd_export(cfg, args.path)
    except KeyboardInterrupt:
        # Interrupt during a single scan; resources are released in scan_once.
        logger.info("Interrupted by user (Ctrl+C). Exiting.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
