---
name: admin-friendly-ux
description: Admin/customer dashboards ko non-technical-friendly banane ka pattern — plain-Hinglish aggregator endpoint + "Aaj" home tab. Use jab user bole "samajh nahi aa raha / kya chal raha hai pata nahi".
---

# Admin-Friendly UX (plain-Hinglish overview pattern)

## Problem pattern
Dashboards me data hota hai par TECHNICAL shape me (heartbeat tables, flag names, job keys, raw events). Non-technical admin ko chahiye: "kya chal raha hai, kisne kya kiya, kya toota, kaise theek karoon" — ek nazar me, Hinglish me.

## Solution pattern (2026-06-12 me build hua)
1. **Aggregator module** (`app/platform/today_overview.py`): existing data sources (automation_health + team.team_status + llm_metrics + flags) ko PLAIN HINGLISH sentences me badlo. NO LLM (instant/free), never-raise, koi naya store nahi.
2. **Insaani naam-map**: har job/flag ka `label` + "yeh kya karta hai" + overdue par "kaise fix karein" hint (JOB_INFO / _IMPORTANT_FLAGS dicts — naya job/flag add karo to yahan bhi).
3. **Ek endpoint**: `GET /api/growth/overview/today` (admin) — frontend ko ek hi call.
4. **Default landing tab**: `/app/automation` ka "🏠 Aaj" — headline ("✅ sab theek / ⚠️ N problems"), problems with fixes, staff table ("aaj kisne kya kiya"), jobs status, band flags with matlab.
5. **Customer side bhi same**: `/api/customer/auth/portal/content` — customer ko APNA content dikhao (copy + WhatsApp share), demo-data confusion mat chhodo.

## Related
- **Unified admin overview** (H.5): `/app/dashboards` ek jagah saare admin dashboards. Naya overview/health UI yahin pe surface karo.

## Rules
- Har naya admin feature = UI tab SAATH hi (API-only = adhoora) — CLAUDE.md rule.
- Status emoji-first: ✅/⚠️/❌/⏳ + chhota Hinglish sentence. Raw JSON sirf "details" me.
- Problem item shape: `{kya: "...", fix: "..."}` — fix hamesha actionable.
- Mobile: sidebar hide mat karo — horizontal scroll quick-nav banao (customer_dashboard @820px pattern).
