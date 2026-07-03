---
name: leadgen-lead-pipeline-quality
description: Lead pipeline quality audit — reliable, deduplicated, explainable, useful Indian local-business acquisition. Use jab scraping/import/enrichment/dedupe/scoring/city-niche rotation/outreach-draft/reply-triage/CRM-movement/WhatsApp-draft/conversion-tracking check karna ho.
---

# LeadGen Lead Pipeline Quality

> Enterprise audit skill. `pipeline-hygiene` = weekly sweep (routine); **yeh = deep architecture audit** (dedupe keys, source ban-risk, scoring explainability). Pehle `context-first`.

## Mission
Pipeline reliable, dedup, explainable, useful banao. Junk deals aur silent overwrites se bachao.

## Pipeline map (repo)
source/import → normalize → dedupe → enrich → score → route → outreach draft → reply triage → CRM → conversion.
- **Harvester**: `app/platform/lead_harvester.py` (`LEAD_HARVESTER=1`) = prospector + SearXNG/Brave + data.gov.in + email-enrich.
- **Maps**: Google Places API (New), cap `PROSPECT_MAX_LOOKUPS=60`/run, OSM Overpass fallback. `NICHE_ROTATION=1` (39 niches) + 15-city pool.
- **Reply triage**: `app/.../reply_agent.py` (`REPLY_AGENT=1`) — IMAP→intent→status+Hinglish draft. **`_is_bulk_sender()` guard** (unknown+bulk = skip; deal sirf known prospect).
- **Cadence**: `cadence.py` (`CADENCE_ENGINE=1`) per-lead multi-channel.

## Ban-risk / ToS (HARD RULE)
justdial · indiamart · sulekha · linkedin · fb · insta = **auto-scrape ToS-BLOCKED** → sirf manual CSV import path. Yeh auto-harvest me kabhi enable mat hone do.

## Workflow
1. source→conversion pura map; source-specific rules + ban-risk identify.
2. Dedupe keys (phone/email/business-name/address/source-URL), city/niche rotation, freshness, caps, status transitions verify.
3. Manual CSV import (fallback path) test.
4. Har outreach action ka source + status + audit-trail confirm.

## Enterprise checks
- Maps/SearXNG/OSM/CSV integrations FAIL-SAFE.
- Dedupe phone+email+name+address+source-URL ke across kaam kare.
- Scoring explainable; manual decision silently overwrite na ho.
- Outreach caps bulk-ban roken.
- CRM stages monotonic (explicit admin reverse ke alawa).

> Lesson (2026-06-12): score 31/100 — 464 "ready" stuck, 2 deals PayU/Instamojo newsletter-reply se JUNK bane the. Guards code me hain; yeh audit unhe VERIFY kare + naye leak pakde.

## Output
Pipeline map + failure points · lead-quality risks · dedupe/scoring test cases · safe daily outreach plan · readiness /100.

## Related repo skills (duplicate mat banao)
`pipeline-hygiene` (weekly routine sweep) · `prospecting` (Apollo-style search/import) · `revops` (sales pipeline) · `leadgen-email-deliverability` (outreach send-safety) · `leadgen-automation-reliability` (harvester jobs).
