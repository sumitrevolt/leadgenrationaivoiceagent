# Free Public APIs — curated for LeadGen AI

Source: [public-apis/public-apis](https://github.com/public-apis/public-apis) (huge free-API directory). Yahan sirf woh **free, India-relevant, free-stack-compatible** APIs jo is project ke liye actually useful hain (curated, blindly nahi). Integration discipline: import-safe + gated + inert-without-key + never-raise (`integration-engineering` skill).

## ⚠️ Integrated (scaffold) — but India-data gap (honest)
| API | Use | Status |
|---|---|---|
| **Nager.Date** (`date.nager.at`, NO key) | Holidays → calendar enrich | Scaffold LIVE in `festivals.py` (`fetch_public_holidays`, `upcoming_enriched`, gated `FESTIVALS_LIVE_HOLIDAYS=1`, defensive). **BUT live-test: India unsupported (IN → HTTP 204, not in AvailableCountries)** → enrichment static list pe fall back hoti. Static `FESTIVALS_2026_27` (Diwali/Holi/Eid) hi India ke liye primary + better. |

**India live-holidays chahiye to** → **Calendarific** (free tier, needs key, accha India coverage) ya **Abstract Holidays** — `fetch_public_holidays` ke shape me URL/parse swap karke flip. (Scaffold ready hai.)

## 🔜 Ready-to-add (free, no/low key) — jab zaroorat ho
| API | Use for project | Note |
|---|---|---|
| **Open-Meteo** (`open-meteo.com`, NO key) | Weather-based marketing angle (garmi→AC/cold-drink offer, baarish→indoor) | Free, no key, generous. Add as a content-angle helper. |
| **QR Server** (`api.qrserver.com`, NO key) | UPI QR, review QR, mini-site QR (image URL) | Already UPI-QR feature hai; yeh no-key fallback. |
| **is.gd / cleanuri** (NO key) | Trackable short links for WhatsApp/SMS campaigns (wa.me, /b/slug, /demo) | Short + clickable; campaign CTR-friendly. |
| **Nominatim / OSM** (`nominatim.openstreetmap.org`, NO key, UA required) | Geocode business address → lat/lng for lead enrichment | Already OSM Overpass use hota hai prospecting me. |
| **REST Countries** (`restcountries.com`, NO key) | Currency/locale formatting (multi-tenant white-label future) | Low priority. |

## ❌ Skipped (paisa/key/ban-risk/irrelevant)
- Paid/key-gated lead-data APIs (project = free-stack).
- Social auto-post APIs (Meta/Google) — app-review blocked (CLAUDE.md).
- Bulk-SMS/WhatsApp non-DLT — ban risk.

> Rule: koi bhi naya API add karne se pehle — free + no-ban + defensive (inert-without-key) honi chahiye, aur `integration-engineering` skill ka pattern follow kare.
