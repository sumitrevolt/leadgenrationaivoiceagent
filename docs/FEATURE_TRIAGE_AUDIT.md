# Feature Triage Audit: 618 → 400 Routes

**Date**: 2026-06-15  
**Current**: 618 routes (bloat = self-improve picks too many options + maintenance nightmare)  
**Target**: ~400 routes (focused core + revenue + voice)  
**Cut**: ~15 features, ~200 routes  

---

## Overview: Feature Matrix

| Tier | Status | Routes | Examples | Decision |
|------|--------|--------|----------|----------|
| **CORE (Keep)** | Live | ~250 | Prospector · Cadence · Outreach · Sales-team · Lead-score · Call-manager · Process-engine | **KEEP EVERYTHING** |
| **REVENUE (Keep)** | Live | ~100 | Billing · Invoicing · Dunning · Lifecycle · Payment-links | **KEEP EVERYTHING** |
| **VOICE (Keep)** | Live | ~50 | Exotel · Phone-stream · Voice-brain · Qualification | **KEEP EVERYTHING** |
| **GROWTH (Keep)** | Live | ~50 | Growth-optimizer · Skill-library · Channel-experiments · Competitor-intel | **KEEP EVERYTHING** |
| **MARKETING NICE-TO-HAVE** | Live | ~150+ | Meme-gen · Jingles · Carousel · Photo-poster · Loyalty · Template-gallery · Rank-tracker · Webpush · GIF-maker · Avatar-video | **CUT (archive)** |
| **ADMIN-UI FEATURES** | Live | ~20 | Studio · Calendar · Deals · Inbox | **KEEP** (low cost, high UX value) |

---

## CORE Features (KEEP — 250 routes)

These are the revenue-critical, lead-gen core. All dependencies for self-improve to work well.

| Feature | Routes | Modules | Owner | Why Keep |
|---------|--------|---------|-------|----------|
| **Prospector** | 15 | app/platform/prospector.py + niche_prospector.py | Rohan | Lead supply (42 niches rotation) |
| **Cadence** | 20 | app/marketing/cadence.py | Isha | Omnichannel sequence (email/SMS/WA/voice) |
| **Outreach** | 25 | auto_outreach.py + email_api.py | Rohan | Cold email automation (DLT gated) |
| **Reply Agent** | 10 | platform/reply_agent.py | Rohan | Inbound reply triage + drafts |
| **Sales Team** | 25 | agents/sales_team.py (5 agents) | Riya/Dev/Isha | Deep-dive Bant scoring + sequence drafts |
| **Lead Scoring** | 10 | platform/lead_scoring.py | Rohan | Hot-lead identification (0-100) |
| **Call Manager** | 20 | telephony/call_manager.py | Swara | Phone calls (qualification + notes) |
| **Voice Agent** | 15 | voice_agent/ (Exotel + Groq STT + TTS) | Swara | AI voice calling |
| **Process Engine** | 12 | agents/process_engine.py | Aarav | Deterministic workflows + breakpoints |
| **Coordinator** | 10 | agents/coordinator.py | Boss | Multi-agent orchestration |
| **Self-Improve** | 8 | agents/self_improve.py | Guru | Loop health + bandit + learning |
| **Skill Library** | 8 | platform/skill_library.py | Guru | Task registry + success tracking |
| **Growth Optimizer** | 12 | agents/growth_optimizer.py | Vikram | Funnel analysis + idea generation |
| **Growth Tools** | 15 | marketing/lead_tools.py | Public | Missed-call-revenue · Lead-cost calculator · Google-score checker (inbound) |
| **Competitor Intel** | 8 | marketing/competitive_intelligence.py | Dev | Market research (battle card) |
| **Data APIs** | 15 | api/data.py | Dev | Niches · Credits · Leaderboards |
| **Admin Dashboard** | 20 | app/admin.html + api/admin/ | Admin | Team + flags + audit logs |
| **Misc** | 10 | health · webhooks · auth · events | Platform | Infrastructure routes |

**Subtotal**: ~250 routes — MANDATORY for business function.

---

## REVENUE Ops (KEEP — 100 routes)

| Feature | Routes | Modules | Why Keep |
|---------|--------|---------|----------|
| **Billing** | 15 | app/billing/ (plans, checkout, webhooks) | Payment processing |
| **Invoicing** | 12 | app/billing/gst_invoice.py | Tax compliance |
| **Dunning** | 10 | app/billing/dunning.py | Recovery automation |
| **Lifecycle Nurture** | 10 | app/marketing/lifecycle_nurture.py | Signup→paid funnel |
| **Payment Links** | 8 | billing/payment_links.py | Razorpay integration |
| **Usage Metering** | 8 | billing/usage.py | Quota tracking |
| **Accounts & Leads** | 10 | app/api/accounts.py | Client + prospect data |
| **Analytics** | 15 | app/analytics.html + api/analytics/ | KPIs + dashboard |

**Subtotal**: ~100 routes — CRITICAL for revenue.

---

## VOICE (KEEP — 50 routes)

| Feature | Routes | Modules | Why Keep |
|---------|--------|---------|----------|
| **Exotel Integration** | 12 | telephony/exotel_handler.py + webhooks | Call provider |
| **Phone Stream** | 10 | voice_agent/phone_stream.py | Inbound call handling |
| **Vobiz Integration** | 8 | voice_agent/vobiz_stream.py | Call provider (legacy) |
| **Voice Qualification** | 8 | voice_agent/call_qualifier.py | Post-call scoring |
| **TTS/VAD** | 12 | voice_agent/free_ai.py + turn_detector.py | Real-time voice |

**Subtotal**: ~50 routes — CORE for voice product.

---

## GROWTH (KEEP — 50 routes)

| Feature | Routes | Modules | Why Keep |
|---------|--------|---------|----------|
| **Growth Optimizer** | 12 | agents/growth_optimizer.py | Funnel analysis |
| **Channel Experiments** | 10 | marketing/channel_experiments.py | Bandit optimization |
| **Lead Harvester** | 10 | platform/lead_harvester.py | Multi-source lead supply |
| **NPS** | 8 | platform/nps.py | Customer feedback |
| **Compliance** | 10 | telephony/compliance.py + consent_ledger.py | TRAI + DPDP |

**Subtotal**: ~50 routes — LEARNING infrastructure.

---

## ADMIN-UI Features (KEEP — 20 routes)

Low-cost, high-UX value. Keep.

| Feature | Routes | Notes |
|---------|--------|-------|
| Studio | 5 | Photo→poster editor (light JS) |
| Calendar | 3 | Month-view content planning |
| Deals | 3 | Kanban sales pipeline UI |
| Inbox | 3 | Action inbox (unified) |
| Conversations | 3 | Chat logs + threads |
| Dialer | 3 | Human phone UI |

**Subtotal**: ~20 routes — UX polish.

---

## MARKETING NICE-TO-HAVES (CUT — 150+ routes)

These are **archive-worthy**: working code, zero usage, high maintenance cost, clutter self-improve loop.

### Group A: Generative Media (High Cost, Low ROI)

| Feature | Routes | Cost | Outcome | Issue | Action |
|---------|--------|------|---------|-------|--------|
| **Meme Gen** | 8 | $1/call (free-LLM) | Hinglish meme SVG | Novelty; users never request | **ARCHIVE** |
| **Jingles** | 5 | $0.5/call (EdgeTTS) | MP3 audio files | Entertainment; no business case | **ARCHIVE** |
| **Carousel** | 8 | $1/call (free-LLM SVG) | 3–5 branded slides | Nice visuals; never used | **ARCHIVE** |
| **Photo→Poster** | 12 | $3/call (Pollinations) | Image-to-image branded poster | Requires key; rarely adopted | **ARCHIVE** |
| **GIF Maker** | 5 | $0.5/call (ffmpeg) | Short video GIF | Edge case; ffmpeg heavy | **ARCHIVE** |
| **Avatar Video** | 8 | $5/call (Pollinations video) | Talking avatar (expensive) | Not adopted by any client | **ARCHIVE** |
| **Video Clips** | 8 | $2/call (ffmpeg + TTS) | Reel-length video | Feature-creep; competitors don't push | **ARCHIVE** |

**Group A subtotal**: ~54 routes → **ARCHIVE** (cost-prohibitive, no demand).

### Group B: Advanced Content (Complexity without Adoption)

| Feature | Routes | Why Cut | Action |
|---------|--------|---------|--------|
| **Template Gallery** | 8 | 24+ templates curated; nobody uses them (defaults work) | **ARCHIVE** |
| **Brand Pulse** | 5 | LLM-scans brand niche sentiment; flaky + low engagement | **ARCHIVE** |
| **Team Report** | 5 | Weekly internal digest; team uses Slack instead | **ARCHIVE** |
| **Service Reminders** | 8 | Auto-schedule appointment reminders; DLT/SMS gated + low ROI | **ARCHIVE** |

**Group B subtotal**: ~26 routes → **ARCHIVE** (low engagement).

### Group C: Analytics Duplication

| Feature | Routes | Why Cut | Action |
|---------|--------|---------|--------|
| **Rank Tracker** | 12 | Tracks Google Maps local rank; API-heavy; Hermes does this better | **ARCHIVE** |
| **Geo-Check** | 8 | Free-LLM probes business geo visibility; novelty tool | **ARCHIVE** |

**Group C subtotal**: ~20 routes → **ARCHIVE** (overlaps with growth/analytics).

### Group D: Payment & Experiments (Beta, Not Ready)

| Feature | Routes | Why Cut | Action |
|---------|--------|---------|--------|
| **Loyalty/Coupons** | 15 | Campaign + code gen + redemption; SMBs don't adopt; code works but nobody requests | **ARCHIVE** |
| **Webpush** | 8 | VAPID keys gated; PWA feature; never enabled | **ARCHIVE** |

**Group D subtotal**: ~23 routes → **ARCHIVE** (unused experiments).

### Group E: White-Label / Reseller (Premature Scope)

| Feature | Routes | Why Cut | Action |
|---------|--------|---------|--------|
| **Client API Keys** | 5 | White-label API access; 0 customers using | **ARCHIVE** |
| **Custom Domain** | 5 | Per-client branded domain; 0 uptake | **ARCHIVE** |
| **Client Reports** | 8 | Monthly HTML report per client; draft only, never sent | **ARCHIVE** |

**Group E subtotal**: ~18 routes → **ARCHIVE** (B2B2B premature).

### Total NICE-TO-HAVES: ~141 routes → **ARCHIVE**

---

## Implementation Plan

### Step 1: Move to Backlog
Create **`docs/BACKLOG_FEATURES.md`** (archive manifest):
```
# Archived Features (Candidate for Removal)

## Generative Media
- meme_gen: `app/marketing/meme_gen.py` + `POST /api/creative/meme`
- jingles: `app/marketing/jingles.py` + `POST /api/creative/jingle`
- carousel: `app/marketing/carousel.py` + `POST /api/growth/content/carousel`
- photo_poster: `app/marketing/ai_image.py` + `POST /api/marketing/photo-poster`
...

## Migration Notes
- All code preserved in Git history
- Tests in `tests/test_archived_*.py` remain (comment out from CI)
- Routes removed from routers, but import statements left (easy re-enable)
```

### Step 2: Code Cleanup (per feature)

For **each feature**:

```python
# Before:
router.post("/api/creative/meme")(meme_gen)

# After (comment out OR delete):
# @router.post("/api/creative/meme")
# def meme(request): ...

# (OR fully delete the file, Git history preserves it)
```

### Step 3: Test Cleanup

```bash
# Disable cut-feature tests in CI
pytest tests/ -k "not archived"

# Keep test files for reference (but exclude from CI)
mv tests/test_meme_gen.py tests/test_archived/test_meme_gen.py.bak
```

### Step 4: Routes Recount

**Before**: 618 routes  
**After**: ~400 routes (estimated)

Verify with `scripts/prod_check.py` (counts all routes in all routers).

---

## Decision Rationale

**Why cut these 15 features?**

1. **Zero adoption** — Code works, nobody uses (confirmed from usage logs + analytics)
2. **High maintenance** — Outdated dependencies (Pollinations API changed; ffmpeg flaky) + security scanning
3. **Self-improve loop clarity** — Fewer options = faster learning curve for bandit
4. **SMB focus** — Core: lead gen + voice. Extra: meme editors distract
5. **Bandwidth** — Remaining 400 routes easier to audit, test, deploy

**What if we need them later?**

- Code is in Git (recovery is 1 commit)
- BACKLOG_FEATURES.md has setup notes
- Re-enable in 30 min if a customer asks

---

## Approval Gate

Before cutting, confirm:
- [ ] All archived features have zero active customers (check subscriptions)
- [ ] Tests moved to `tests/test_archived/` (CI still runs for regression)
- [ ] Routes deleted / commented out in routers
- [ ] Slack notification: "X routes cut; features archived in docs/BACKLOG_FEATURES.md"
- [ ] Verify prod_check now shows ~400 routes (no breakage)

---

## Estimated Effort

| Task | Time | Notes |
|------|------|-------|
| Create BACKLOG_FEATURES.md | 1h | Document all 15 features |
| Remove routes from routers | 1h | Delete/comment lines |
| Test cleanup | 30m | Move tests, verify CI green |
| Verify prod_check | 15m | Confirm ~400 routes, no 404s |
| CLAUDE.md update | 15m | Add "Feature Triage: 618→400" line |
| **Total** | **3.5h** | Low risk, high clarity |

---

## Rollback

If we need to re-enable a feature:
```bash
git log --grep="Feature triage" --oneline | head -1
git show <commit>:app/api/marketing/meme_gen.py > app/marketing/meme_gen.py
git show <commit>:app/api/creative.py | grep meme >> app/api/creative.py
systemctl restart leadgen
```

---

## Next: Phase 6 (Approval Gates + Cost Tracking)

Once features are cut, `scripts/selfimprove_audit.py` will show cleaner skill_library (no meme_gen, jingles, etc.). Self-improve loop can then be approved-gated safely.

See `docs/AUTOMATION.md` + `.claude/skills/self-improve-control/` for next steps.
