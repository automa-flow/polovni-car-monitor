# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[semantic versioning](https://semver.org/).

## 0.2.0 — 2026-09-28

### Added
- `DISCLAIMER.md`: no-affiliation and trademark notice, the relevant clauses of
  the site's Terms of Use, data-protection notes, user responsibilities and a
  takedown contact.
- `SECURITY.md`, a GitHub Actions CI workflow (ruff + pytest on Python
  3.11–3.14, Linux and Windows) and this changelog.
- Phone numbers and e-mail addresses in listing descriptions are masked before
  the text is logged, sent to the LLM provider or forwarded to Telegram.
- Politeness limits enforced in code: at least 15 min between passes, at least
  2 s between page loads, at most 3 attempts per page, price re-checks at most
  once every 24 h.
- Tests: an end-to-end monitoring pass with a fake fetcher, contact redaction
  and config limits.

### Changed
- **Python 3.11+ is now required** (3.9 reached end of life). Delete an old
  `.venv` and run `run.bat` / `run.sh` again. The Windows script now creates
  the venv with the `py` launcher.
- Playwright is no longer pinned to 1.40. Any version ≥ 1.49 works.
- The browser is launched as-is: the spoofed User-Agent and the flag that hid
  the automation marker were removed. The plain-HTTP backend identifies itself
  as `polovni-car-monitor/<version>` with a link to this repository.
- The full LLM prompt and raw response are logged only at `DEBUG` level.
- Listing titles no longer glue the year onto the name
  ("…Arval 2020. godište" instead of "…Arval2020. godište").
- README rewritten to match current behaviour: every new listing is sent and
  interesting ones are flagged.

### Removed
- The saved copy of a real listing page used as a test fixture. It has been
  replaced by a fictional, hand-written page and purged from git history.

## 0.1.0 — 2026-06-19

First public version: saved-search monitoring with Playwright, keyword and
"good deal" scoring, optional OpenAI appraisal, price-range "explore" searches,
price-drop alerts, a daily heartbeat, CSV export and Telegram notifications.
