# Security policy

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's
private reporting instead: **Security → Report a vulnerability** on this
repository. You should get a first reply within a few days.

Only the latest version on `main` is supported.

## Keeping your own setup safe

- `.env` holds your Telegram bot token and OpenAI API key. It is gitignored:
  never commit it, paste it into issues, or share it in logs.
- If a token leaks, revoke it right away: `/revoke` in
  [@BotFather](https://t.me/BotFather) for Telegram, and the
  [API keys page](https://platform.openai.com/api-keys) for OpenAI.
- `data/` holds your local database, logs and the browser profile (cookies).
  It is gitignored too. Don't share it.
- When you report a parsing bug, don't attach a saved listing page. It holds
  sellers' personal data and content owned by the site. Describe the markup,
  or reduce it to a small made-up example like
  [`tests/fixtures/listing_synthetic.html`](tests/fixtures/listing_synthetic.html).
