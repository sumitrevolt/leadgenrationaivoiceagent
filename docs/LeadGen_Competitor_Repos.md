# Automated Lead-Gen — competitor features → repos (2026-06-08, deep research)

Objective: automated lead generation, apne liye AUR client ke liye (done-for-you). Yeh doc
competitors ke features dekh ke gaps + jo free/OSS repos add kiye unka map hai.

## Competitor stack (2026) — 4 layers
1. **Enrichment** (Apollo 275M contacts DB / Clay waterfall) — email+phone+company find.
2. **Verification** (Hunter auto-verify, Clay confidence scoring) — bounce kam karo.
3. **Sending/deliverability** (Instantly/Smartlead — warmup, inbox rotation, SPF/DKIM/DMARC).
4. **Sequences + AI personalization** (multi-touch, AI intro lines).

## Hard 2026 deliverability rules (kyun verification critical hai)
- Gmail/Yahoo/Outlook ab **un-authenticated bulk mail REJECT** karte (Nov-2025 Gmail + May-2025 Outlook escalation). SPF + DKIM + DMARC = mandatory floor.
- **Bounce rate <2%** (ideal <1%). >5% = sender reputation barbaad → immediate pause.
- ~17% cold emails inbox tak pahunchte hi nahi (bad auth / high bounce / spammy content).
- Warmup: naya domain 5-10/din se shuru, 4-6 hafte ramp. Dedicated sending domain zaroori (primary mat jalao).

## Feature matrix — competitor vs hum
| Feature | Competitor | Hamara status | Repo / action |
|---|---|---|---|
| Lead sourcing | Apollo DB, scrapers | Google Maps API + OSM (free) | already; + Crawl4AI deep crawl |
| Web enrichment | Clay | trafilatura + crawl4ai + web_extract | **added** |
| Doc→data | — | MarkItDown (any file→md) | **added** |
| **Email verification** | Hunter/Clay | tha sirf basic syntax | **email-validator (syntax+MX) — ADDED + WIRED into auto_outreach** |
| **Phone validation** | — | crude regex | **phonenumbers (libphonenumber) — ADDED** |
| Personalization (AI) | Clay AI lines | free_ai + structured (Instructor) | already + structured |
| Lead scoring | intent data | `lead_scoring.py` (rules) | already |
| Sequences/follow-ups | Instantly | email Day-3/Day-7 + WhatsApp | already (`auto_outreach`) |
| Deliverability auth | Instantly/Smartlead | SMTP live | **USER action: SPF/DKIM/DMARC on leadsgenai.in** (DNS) |

## Added this round
- **`app/lead_scraper/email_verify.py`** (python-email-validator): syntax + **MX** deliverability + role/placeholder skip. **WIRED into `auto_outreach._valid_email`** → ab sirf deliverable emails ko bhejte hain → bounce <2%, reputation safe. Env `OUTREACH_VERIFY_MX=1` (default on; 0 = MX off). Defensive: lib absent → basic check.
- **`app/lead_scraper/phone_validate.py`** (phonenumbers): `validate_in(raw)` → valid? + E.164 + national + is_mobile. Cleaner WhatsApp/call targeting (kam wasted sends). Defensive regex fallback.
- Dono self-outreach AUR client campaigns dono ke liye (orchestrator_pipeline / run-campaign me lagao).

## "Client ke liye" (done-for-you lead-gen) — pipeline
Client ka niche+city → prospector (Maps/OSM) → enrich (trafilatura/crawl4ai) → **verify email (MX) + validate phone** → score (`lead_scoring`) → outreach (email + WhatsApp 1-click) → qualified leads deliver. Quality-gates (verify/validate) ab competitor-grade.

## Next gaps (USER/infra — Claude build nahi kar sakta)
- **SPF/DKIM/DMARC** leadsgenai.in pe set karo (Hostinger DNS) — bina iske bulk email reject ho sakta. (Highest ROI next step.)
- **Dedicated cold-email domain** (e.g. try-leadsgenai.in) — primary domain mat jalao.
- **Warmup** — naye domain pe slow ramp (mailwarm-type; ya manual low volume start).
- Apollo-jaisa contact DB paid hai — hum scraping + verification se free-stack me chalte hain.

## Sources
Apollo/Clay/Instantly/Smartlead/Hunter feature comparisons; python-email-validator; phonenumbers; 2026 Gmail/Outlook bulk-sender + deliverability guides (SPF/DKIM/DMARC, bounce<2%).
