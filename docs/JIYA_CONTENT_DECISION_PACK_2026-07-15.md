# Jiya Makeover Studio — Content Decision Pack

**Date:** 2026-07-15. **Scope:** read-only review of `data/content_queue/jiya-makeover.jsonl`
(9 items, all `status: draft`) plus what was seen live on `/app/clients` this session. **No
record was approved, rejected, scheduled, delivered, or published while preparing this pack.**
Client: Jiya Makeover Studio (`jiya-makeover`), Starter plan, niche `beauty_makeover`, Nagpur,
phone 9359984977 (per her client record — see the phone-number defect on item 3 below).

Cross-cutting fact affecting every item: this session did not verify Jiya's own
Instagram/Facebook/WhatsApp channel connection status in the admin UI (only her website
"Site dekho" link was visible) — and product-wide, customer-side auto-posting is not live yet
(per `CLAUDE.md`: "abhi 1-click copy/download"). So **no item here can currently go live with a
single click regardless of its bucket** — every "approve" only marks an internal status; a human
still has to manually copy/paste or hand it to Jiya to post herself.

## Per-item facts

| ID | Title / Type | Created | Intended date | Caption summary | Brand OK? | Service-relevant? | Area-correct? | Duplicate risk | Festival/date relevance | Quality issues | Recommended action | Could publish publicly? | Channel connected? |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `0163113a446d` | Tip / Gyaan (post) | 2026-07-13 | 2026-07-13 (past) | Generic "flawless makeover, quality/sahi daam/bharosa" blurb | Yes | Generic, no specific tip | N/A | **High** — identical caption+hashtags to `0b8f93f81312`, `913de55616e7`, `4171cf3fbc00` | None — evergreen | Date already passed; not an actual "tip", just brand tagline | **Obsolete** — regenerate as a real tip | Not without a human copy/paste step | Not verified this session |
| `6bef973fa678` | Offer / Deal (post) | 2026-07-13 | 2026-07-14 (past) | "Is hafte ka special makeover" (this week's special) | Yes | Yes — a deal | N/A | Low | **Time-locked language now stale** — "this week" no longer applies | Date-specific offer copy that has expired | **Obsolete** — regenerate with a current offer/date | Not without a human copy/paste step | Not verified this session |
| `1d87e97e52f0` | Brand Poster (poster/SVG) | 2026-07-13 | 2026-07-15 (today) | "Premium Bridal & Event Makeup — Special Offer, Shubh Avsar" | Yes | Yes | N/A | Low | Generic "auspicious occasion" framing, not tied to a specific festival | **Wrong phone number** — poster shows `+919876543210` (a template placeholder), not Jiya's real number `9359984977` | **Edit** — fix the phone number before any use | No — factual error must be fixed first | Not verified this session |
| `0b8f93f81312` | Reel Idea (reel) | 2026-07-13 | 2026-07-16 (upcoming) | Same generic blurb as `0163113a446d` | Yes | No reel-specific script/hook | N/A | **High** — verbatim duplicate of 3 other items | None | Labeled "Reel Idea" but contains no reel-specific content (no shot list/hook) | **Duplicate/redundant** — needs unique reel content | Not without a human copy/paste step | Not verified this session |
| `913de55616e7` | Festival / Fun (post) | 2026-07-13 | 2026-07-17 (upcoming) | Same generic blurb as `0163113a446d` | Yes | Not festival-specific | N/A | **High** — verbatim duplicate | **Mismatch**: labeled "Festival / Fun" but references no actual festival (other clients' equivalent slot this session used a real festival, e.g. Rath Yatra) | Category/content mismatch | **Duplicate/redundant** — needs a real festival tie-in | Not without a human copy/paste step | Not verified this session |
| `444228aa96d0` | Product Spotlight (post) | 2026-07-13 | 2026-07-18 (upcoming) | "Quality ka magic, sahi daam ke saath" — unique text | Yes | Yes | N/A | Low — unique caption | None claimed | None found | **Approve internally** after human review | Yes, once a human posts it manually | Not verified this session |
| `4171cf3fbc00` | Engagement Question (post) | 2026-07-13 | 2026-07-19 (upcoming) | Same generic blurb as `0163113a446d` | Yes | Not a question | N/A | **High** — verbatim duplicate | None | Labeled "Engagement Question" but contains no actual question | **Duplicate/redundant** — needs a real question | Not without a human copy/paste step | Not verified this session |
| `14e4d7579b7b` | WhatsApp Promo Message | 2026-07-13 | 2026-07-13 (past) | Broadcast-style promo text | Yes (mostly) | Yes | N/A | Low | None | **Malformed/truncated** — contains stray `**`/markdown artifacts and cuts off mid-word ("...Limi") | **Obsolete** — regenerate, do not send as-is | No — broken text, would look unprofessional | Not verified this session |
| `6e299d926fb9` | Local Offer Campaign Suggestion | 2026-07-13 | 2026-07-13 (past) | "Monsoon Glow Referral Fest" — refer-a-friend discount idea | Yes (concept) | Yes (concept) | **No — references "local Mumbai cafés"; Jiya is in Nagpur** | Low | Monsoon-seasonal, still broadly timely | **Wrong city** — geography doesn't match the client | **Edit** — replace Mumbai references with Nagpur, then confirm discount terms with Jiya | No — needs correction first | Not verified this session |

## Grouped for decision

**1. Recommended for approval after human review**
- `444228aa96d0` — Product Spotlight. Clean, on-brand, no defects found.

**2. Requires editing**
- `1d87e97e52f0` — Brand Poster: fix the wrong phone number (`+919876543210` → `9359984977`) before any use.
- `6e299d926fb9` — Local Offer Campaign Suggestion: replace "Mumbai cafés" with a Nagpur-appropriate partner/venue, then confirm the specific discount % with Jiya before running it (recommend also treating this one as **needs customer input** on the exact offer terms).

**3. Obsolete or date-expired**
- `0163113a446d` — Tip/Gyaan: intended date (07-13) already passed; also part of the duplicate cluster below.
- `6bef973fa678` — Offer/Deal: "this week's special" language is now stale (intended date 07-14 passed).
- `14e4d7579b7b` — WhatsApp Promo: intended date (07-13) passed AND text is malformed/truncated — recommend discarding and regenerating rather than editing.

**4. Duplicate/redundant**
- `0b8f93f81312` (Reel Idea), `913de55616e7` (Festival/Fun), `4171cf3fbc00` (Engagement Question) — all three share the exact same generic caption/hashtags as `0163113a446d` and none delivers on its own category label (no reel script, no festival reference, no actual question). Recommend regenerating all three with category-appropriate content rather than approving as-is.

**5. Blocked by missing channel or customer information**
- None individually blocked beyond the cross-cutting fact above (no customer-side channel connection was verified this session, and auto-posting to a live channel isn't available product-wide yet — every item above is "internal record only" regardless of bucket).

## What was NOT done

No approve/reject/skip/obsolete/edit action was applied to any of these 9 records. No delivery
or publish action was triggered. This pack is read-only synthesis for your decision.
