# Lead Harvester — multi-source scraping deep-research (2026-06-10)

## Legal lines (India) — design constraints
- **IT Act 2000 §43(a)/(b)**: unauthorized access/extraction = liability. **ToS violation = contract breach** — JustDial/IndiaMART/Sulekha/LinkedIn/Facebook AUTO-scraping LOOP me KABHI nahi (ban + legal risk). Inka path = manual CSV import (Apollo-style, already built) ya official APIs (IndiaMART Lead Manager API = paid seller account, future gated integration).
- **DPDP Act 2023**: bina consent personal data = risk → hum sirf BUSINESS data collect karte (firm name, business phone, address, website) — personal profiles nahi.
- **Safe-by-design sources**: Google Places API (keyed, compliant), OSM Overpass (open license), business ki APNI website (public contact info, robots-respecting single fetch), data.gov.in OGD API (open license, free key), Brave Search API (keyed, $5/mo credit ≈1k queries — 2026 me free tier khatam, ab metered).
- Anti-bot warfare (stealth/proxies/fingerprints) = HUMARE liye nahi — woh ToS-bypass territory hai. Hum sirf legal sources, polite rate (sleep + caps + UA), graceful fail.

## Stack decision
- Scrapy/Playwright-stealth = overkill + ops burden (proxy layer). Humara scale (sub-100 fetches/run) = **httpx + trafilatura (web_extract.find_contacts) + regex** — already installed, zero new deps. Crawl4AI optional path pehle se hai (deep_extract).
- LLM scraping me NAHI (deterministic extract; LLM sirf pitch personalize jo pehle se hai).

## Sources (registry, gated = bina key inert)
| Source | Status | Gate |
|---|---|---|
| prospector (Places API + OSM) | LIVE primary | GOOGLE_MAPS_API_KEY (set) |
| websearch (Brave → business sites → contacts) | NEW | BRAVE_API_KEY |
| opendata (data.gov.in Udyam/MSME lists → seed names) | NEW | DATA_GOV_IN_API_KEY + DATA_GOV_RESOURCE_ID |
| enrich (website → email_finder waterfall, phone regex) | NEW stage | none (existing leads pe) |
| import (Apollo/CSV manual paste) | LIVE | none |

## Loop
`LEAD_HARVESTER=1` → (a) daily `prospect` job ke baad extra sources + enrich sweep, (b) self_improve action `harvest_leads` (continuous loop me), (c) process_library executor. Dedupe phone/email vs prospects store; validate phonenumbers E.164 + MX; persist prospector._append (DB mirror free); auto rescore.

Sources: [ikigailaw.com](https://www.ikigailaw.com/article/263/legality-of-data-scraping-in-india) · [spiceroutelegal.com](https://spiceroutelegal.com/publications/legality-of-data-scraping-under-indian-law/) · [law.asia DPDPA](https://law.asia/india-data-scraping-regulation/) · [Brave API pricing](https://api-dashboard.search.brave.com/documentation/pricing) · [implicator.ai Brave free-tier change](https://www.implicator.ai/brave-drops-free-search-api-tier-puts-all-developers-on-metered-billing/) · [data.gov.in Udyam](https://www.data.gov.in/catalog/udyam-registration-msme-registration) · [firecrawl open-source crawlers](https://www.firecrawl.dev/blog/best-open-source-web-crawler) · [scrapingbee tools 2026](https://www.scrapingbee.com/blog/web-scraping-tools/)
