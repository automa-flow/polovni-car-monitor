# Disclaimer, terms of use and data protection

This page explains the legal context of **polovni-car-monitor**, what the
software deliberately does and does not do, and what you take on by running it.
It is written in good faith by the author. It is **not legal advice**. If you
need certainty for your situation, ask a lawyer.

- [1. No affiliation, trademarks](#1-no-affiliation-trademarks)
- [2. The site's Terms of Use](#2-the-sites-terms-of-use)
- [3. What the software does and does not do](#3-what-the-software-does-and-does-not-do)
- [4. Your responsibilities](#4-your-responsibilities)
- [5. Personal data](#5-personal-data)
- [6. Third-party services](#6-third-party-services)
- [7. No warranty, no purchase advice](#7-no-warranty-no-purchase-advice)
- [8. Contact and takedown requests](#8-contact-and-takedown-requests)

## 1. No affiliation, trademarks

This is an independent, unofficial hobby project. It is **not affiliated with,
endorsed by, sponsored by or connected to Polovni automobili doo (Subotica,
Serbia)** or any company of its group.

"Polovni Automobili" and "PolovniAutomobili" are trademarks of their owner. They
are used here only to say which website the software works with. The project
uses no logos, design or other branding of the site. All other product names
(Telegram, OpenAI, Citroen and so on) belong to their respective owners.

The source code is MIT-licensed (see [LICENSE](LICENSE)). The license covers
this code only. It grants nothing in respect of the website, its content or its
data.

## 2. The site's Terms of Use

The website has its own Terms of Use (*Uslovi korišćenja*):
<https://www.polovniautomobili.com/uslovi-koriscenja>. The version quoted below
is dated 19 August 2026 and has applied since 27 August 2026. It was last
checked for this page on 28 September 2026. The terms can change at any time,
so read the current version yourself.

The terms apply to **every person who accesses the site**, including visitors
who never register (section 1.2, definition of *Korisnik*). Provisions
relevant to this tool:

| Provision (Serbian original) | English translation |
| --- | --- |
| §14.3: *"Bilo koje automatsko korišćenje sistema, kao što je, ali ne ograničavajući se na korišćenje skripti za slanje fotografija, ili video zapisa"* | Prohibited: "any automated use of the system, such as, but not limited to, the use of scripts for sending photos or videos" |
| §14.3: *"Zaobilaženje, ili izmena, pokušaj da se zaobiđe, ili izmeni, ili podsticanje, ili pomaganje drugim osobama da zaobiđu, ili izmene neku od bezbednosnih tehnologija, ili softvera koji su deo Servisa"* | Prohibited: circumventing or modifying any of the Service's security technologies or software, attempting to, or encouraging or helping others to do so |
| §14.3: *"Mešanje sa, prekidanje, ili kreiranje nepotrebnog opterećenja Servisa…"* | Prohibited: interfering with, disrupting, or creating unnecessary load on the Service |
| §14.3: *"Zabranjeno je neovlašćeno preuzimanje, kopiranje i javno objavljivanje sadržaja oglasa sa Servisa na profile na društvenim mrežama, druge veb-sajtove ili bilo koje javne kanale bez izričite pisane saglasnosti Društva."* | Prohibited: unauthorised downloading, copying and public republication of listing content on social-media profiles, other websites or any public channels without the company's express written consent |
| §14.3: *"Zabranjeno je sistematsko praćenje i prikupljanje podataka o oglašivačima sa Servisa u svrhu kontaktiranja i nuđenja usluga konkurentskih platformi za oglašavanje ili bilo kojih drugih komercijalnih usluga."* | Prohibited: systematic monitoring and collection of data about advertisers in order to contact them and offer competing platforms or any other commercial services |
| §8.1 | The company claims all IP rights in the Service, including its **databases** and the **"Polovni Automobili" trademark** |
| Site footer: *"Zabranjeno je njegovo preuzimanje bez dozvole Društva, zarad komercijalne upotrebe ili u druge svrhe, osim za lične potrebe posetilaca sajta."* | Downloading the site's content without the company's permission is prohibited, for commercial or other purposes, **except for the personal needs of site visitors** |
| §15.1 | Serbian law governs the terms |

**Bottom line:** because the terms prohibit *any automated use* of the site,
**running this software against polovniautomobili.com may breach its Terms of
Use, even for purely personal, low-frequency use.** Possible consequences
include blocked access and claims by the site operator. The design choices in
section 3 reduce the impact of the tool. They do not make its use authorised.
Only the site operator can do that.

For completeness, the site's `robots.txt` (checked 28 September 2026) does not
disallow the search (`/auto-oglasi/pretraga`) or listing (`/auto-oglasi/<id>/…`)
paths. `robots.txt` is a crawler convention. It does not override the Terms of
Use.

## 3. What the software does and does not do

The project was built as a **personal replacement for refreshing a few saved
searches by hand**. These safeguards are part of the code, not only the
documentation:

**It does not:**

- use stealth or anti-detection techniques: no spoofed User-Agent in the
  browser, no hidden automation flags, no fingerprint patches, no proxy
  rotation;
- solve captchas or try to get past the site's protection. If a page stays on a
  verification screen, it is skipped and logged;
- extract seller names, phone numbers, e-mail addresses or addresses. Phone
  numbers and e-mails that sellers type into the free-text description are
  masked (`[phone]`, `[email]`) right after parsing. That happens before the
  text is logged, sent to an LLM provider or forwarded to Telegram;
- save photos or build a copy of the site's database. The browser loads a
  page the same way it would for you, and only the parsed fields listed below
  are kept;
- publish anything. Results go only to the Telegram chat that *you* configure.

**It does:**

- enforce low frequency in code: at least **15 minutes** between passes, at
  least **2 seconds** between page loads, at most **3** attempts per page. No
  `.env` value can go lower;
- open only the search pages you list and **only new listings**. Known
  listings are not re-opened, apart from an optional price re-check at most
  once a day;
- identify itself honestly in the plain-HTTP backend
  (`polovni-car-monitor/<version> (+repo URL)`);
- keep all state locally in `data/`: listing IDs, URLs, titles, prices and
  timestamps.

## 4. Your responsibilities

By running this software you accept that **you alone are responsible** for how
you use it and for complying with the site's Terms of Use and the law that
applies to you. In particular:

- use it for **your own personal, non-commercial car search** only;
- send notifications only to **your own private chat or a private group**.
  Never forward listing content to public channels, websites or social media;
- do not use it, or code derived from it, to build datasets, resell data,
  compare prices commercially, or contact or market to sellers;
- do not reduce the enforced limits or add evasion techniques;
- stop if the site blocks you or asks you to stop.

If you are not comfortable with the risk described in section 2, do not run
the tool against the site.

## 5. Personal data

Listings are published by private individuals and dealers. The free-text
description can contain personal data. Serbia's Law on Personal Data Protection
(*Zakon o zaštiti podataka o ličnosti*, modelled on the EU GDPR) may apply to
you as the person running the software.

- **Minimisation:** seller contact fields are never extracted, and contact
  details in the description are masked right after parsing (see section 3).
- **Storage:** the SQLite database stores no description text, only a hash of
  it. Log files in `data/logs/` rotate at about 1 MB × 5. At the default `INFO`
  level they contain listing metadata and the LLM's verdict. The full text sent
  to the LLM is logged only at `DEBUG`.
- **Deletion:** delete the `data/` folder to erase everything the tool has
  stored.
- **Repository:** the tests use a hand-written, fictional HTML page. No real
  listing pages or personal data are included in this repository.

## 6. Third-party services

- **OpenAI (optional).** With `USE_LLM=true` and an API key, the text of each
  new listing (contact details masked) is sent to OpenAI or to the compatible
  endpoint you configure. Their terms and privacy policy apply. Leave
  `OPENAI_API_KEY` empty to keep all analysis local.
- **Telegram.** Notifications pass through the Telegram Bot API under
  Telegram's terms.
- **Playwright / Chromium.** Downloaded from their official sources under their
  own licenses.

## 7. No warranty, no purchase advice

The software is provided **"as is", without warranty of any kind**. See the MIT
[LICENSE](LICENSE). Parsing can break whenever the site changes. Keyword
scores, the "deal" heuristic and LLM appraisals are rough automated opinions.
They can be wrong. They are **not** professional, mechanical or financial
advice. Always inspect a car and its documents in person, ideally with a
mechanic, before buying.

## 8. Contact and takedown requests

If you represent Polovni automobili doo, or any other rights holder, and want
something in this repository changed or removed, please
[open an issue](https://github.com/automa-flow/polovni-car-monitor/issues).
The request will be handled promptly and in good faith.
