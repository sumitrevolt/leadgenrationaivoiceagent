---
name: competitor-ad-teardown
description: Teardown competitor ads/landing-copy from FREE public sources (Meta Ad Library, Google Ads Transparency, LinkedIn) into a hooks/angles/offers swipe file for Product-1 marketing. Use when user says "competitor ads dekho", "ad teardown", "swipe file", "kya messaging chal rahi", "competitor offers", "ad inspiration", or building ad-creative for a niche/client.
---
# Competitor Ad Teardown

Product-1 (AI Marketing) ke liye: competitor ki **live ads + landing copy** se hooks/angles/offers nikaalo → swipe file → `ad-creative` + `hinglish-copywriting` me feed.

## FREE public sources (no paid tool, ToS-safe = public/read-only)
| Source | URL pattern | Deta hai |
|--------|-------------|----------|
| **Meta Ad Library** | `facebook.com/ads/library` (country=IN, search brand/keyword) | Active FB+IG ads, copy, creatives, run-dates |
| **Google Ads Transparency** | `adstransparency.google.com` (region=India) | Search + YouTube + display ads per advertiser |
| **LinkedIn Ads** | company Page → "Ads" tab | B2B ad copy |
| Landing pages | competitor URL → `/site-audit` (apna lead-magnet) | offer, CTA, proof, pricing framing |

> **Apni ToS rule:** justdial/indiamart/linkedin auto-SCRAPE blocked (CLAUDE.md). Yahan = **manual/public-API read** of ad libraries (these are PUBLIC by design) — scraping pipeline mat banao, browse + extract.

## Teardown checklist (har ad pe)
1. **Hook** — pehli line / thumbnail text (scroll-stopper).
2. **Angle** — pain / aspiration / fear / social-proof / urgency.
3. **Offer** — kya de rahe (free audit? trial? discount? guarantee?).
4. **CTA** — exact words ("Book now" vs "Get free quote").
5. **Proof** — reviews, numbers, logos, before/after.
6. **Run-length** — Meta library me long-running ad = winner (paisa laga rahe = convert ho rahi).

## Output: swipe file
```markdown
## <niche> — competitor ad swipe (<date>)
| Competitor | Hook | Angle | Offer | CTA | Running since |
|---|---|---|---|---|---|
| ... | "..." | urgency | free audit | "Get audit" | 90+ days |

### Steal-worthy (adapt, copy NAHI)
- Hook pattern: ...
- Offer gap WE can beat: ...  (our /audit lead-magnet > their generic form)
```
Save → `docs/` ya client KB (`clients_store` niche namespace) taaki content engine use kare.

## Then
- Winning angles → `ad-creative` skill se bulk variations (Hinglish).
- Offer gaps → `offers` / `conversion-optimization`.
- Gap vs OUR products → `competitors` / `competitor-profiling` (deeper feature-gap).

## Don't
- Copy verbatim (trademark/plagiarism) — **adapt** angle, apni voice.
- Auto-scrape loop banao — manual/public read only.
- Fabricate "competitor X spending ₹Y" — sirf jo library me dikhe.
