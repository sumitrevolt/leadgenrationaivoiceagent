# GTM 0→1 Design — "Reply-Mine + Dialer Beachhead" (A+B, 4 tracks)

**Date:** 2026-07-02 · **Status:** APPROVED (user: "haan spec likho") · **Owner:** Sumit (full-time founder)
**Goal:** Pehla paying customer ≤7 din, 5 paying ≤30 din — Product 1 (AI Marketing Automation ₹1,999/mo) wedge se.
**North star (user):** "1500 calls/day karne wala startup" — Track 4 isi ka ramp hai; Track 1-3 aaj se revenue nikaalte hain jab tak woh unblock hota hai.

## Funnel diagnosis (live VPS data, 2026-07-02)
| Signal | Number | Conclusion |
|---|---|---|
| Prospects harvested | 6,466 | Top-of-funnel machine works |
| Emailable / emailed | 1,794 / 1,787 (**6 pending**) | Email backlog EXHAUSTED — refill chahiye |
| Website inquiries (ever) | 3 | Inbound ~dead; SEO abhi paisa nahi |
| Reply drafts | 1,100 · last-200: **80 interested + 7 question** | 🔥 Warm replies unworked pade hain |
| Phone-only prospects | ~4,672 | Dialer ka untapped ammo (email se unreachable) |

**Bottleneck = mid-funnel execution, not top-of-funnel.** Interested log jawab ka wait kar rahe hain; 4.6k phones kabhi dial nahi hue.

## Track 1 — Hot-Reply Sprint (Day 1, roz subah 30-60 min)
- **Tool: Hot Queue** (isi session me SHIPPED — neeche spec): `/app/inbox` → "🔥 Hot Queue" tab. interested/question replies, handled-filter + sender-dedupe + freshness-sort + prospect phone/business JOIN. Har card: draft-copy, ✉️ mailto, 📞 tel, 💬 wa.me, ✅ Done.
- **Kaam:** queue upar-se-neeche — 1-click draft send + phone walon ko same-day call/WhatsApp. Pehle 10-15 manually eyeball (classifier "interested" inflate kar sakta hai — feedback endpoint se correct karo, woh training signal hai).
- **Target:** 80 interested → ≥20 real conversations → 3-5 demos → pehla paying yahi se sabse likely.

## Track 2 — Founder Dialer Beachhead (Approach A core, roz 2-3 ghante)
- 1 city × 2-3 S-tier niches (prospect data se highest-count combo pick — session me compute karke choose karo). ~4,672 phone-only prospects me se.
- Roz 30-50 **human calls** (DLT ke bina legal — human call pe TRAI DLT lagti nahi; timing waise bhi 9am-7pm rakho).
- **Pre-call asset:** har prospect ka `/audit` report + `/b/{slug}` demo mini-site pehle generate — opener: "maine aapki online presence dekhi, 3 problem mili".
- Follow-up: WhatsApp 1-click (audit link + demo) → close ₹1,999 UPI self-serve.
- Playbook refs: `dialer-sprint-ops` skill, `docs/Sales_Kit_Hinglish.md`, `/app/battlecard`.
- **Math:** ~100 conversations → ~10 demos → 2-3 paying / 2 hafte.

## Track 3 — Automated refill (Approach B, background — already running)
- Harvester + email-enrich naye prospects (emailable pipeline refill — 6-pending wala tank bharna).
- Day-3/7 followups + cadence + reply-triage automatic chalte rahenge.
- Cap 25/day HOLD; bounce-rate green rahe tabhi 40 tak ramp (deliverability > volume).

## Track 4 — AI-Dialer Scale Path ("1500 calls/day startup")
Yeh user ka end-state hai; abhi 2 USER-side unblocks pe gated:
1. **DLT registration** — Udyam cert ready hai → Proprietorship se DLT re-apply (sirf yahi AI cold-calling kholta hai).
2. **Vobiz recharge + DID** — `VOBIZ_CALLER_ID=+91<DID>` set + restart.
- Code-side READY: `platform_dial` self-sale batch engine tree me committed + aaj ke rebuild me image me BAKED (flag `data/platform_dial.json` se arm hota hai). Compliance gates (DND fail-closed, 9am–7pm clamped, AI-disclosure, consent-ledger) is repo me NON-NEGOTIABLE enforced — aaj aur harden bhi hue.
- **Ramp (VOICE_SELFHOST_FINETUNE_PIPELINE.md ke mutabik): 50/day → 200/day → 1500/day.** 50 se shuru: script/close-rate tune karo (web-call pe free tuning), phir scale. 1500/day = ~45k voice recs/month = STT fine-tune flywheel ka data bhi.
- Economics: Vobiz ₹0.45/min ladder; 1500 × ~2min ≈ ₹1,350/day telephony — pehle Track 1-2 se revenue aane do, phir yeh spend justify hota hai.
- **Track 2 ka har human call Track 4 ka script-training hai** — jo objections/hooks kaam karte hain woh `niche_scripts.py`/KB me feed karo.

## Daily rhythm + scorecard
- Subah: Hot Queue clear (30-60 min) → Dialer sprint (2-3 hr) → shaam: WhatsApp follow-ups.
- Roz 5-line scorecard: calls / conversations / demos / UPI-links / **PAID**. (Aaj tab + `/app/inbox` counters.)
- Weekly: jis niche×city me demos nikle → double-down; dead combos rotate.

## Hot Queue — feature spec (SHIPPED 2026-07-02)
- **Module** `app/platform/reply_agent.py`: `hot_queue(limit)` — intents (interested,question) filter · `hq_status=done` excluded · sender-dedupe (latest wins) · newest-first · `_full_prospect_map()` (full-store read; list_prospects newest-cap lesson) se phone/business/niche/city join · `hq_id` = sha1(from+at)[:12] · `age_days`. `mark_handled(hq_id)` — in-place rewrite, temp+atomic replace, idempotent-false. Dono never-raise.
- **API** `app/api/growth.py`: `GET /api/growth/reply/hot-queue` (admin, limit≤200) · `POST /api/growth/reply/hot-queue/done` (admin, rate-limited, 404 on unknown/already-done).
- **UI** `frontend/inbox.html`: naya default "🔥 Hot Queue" tab — card = business/from + intent + age + injection-flag warning + draft copy + mailto/tel/wa.me + ✅ Done.
- **Tests** `tests/test_hot_queue.py` (4 green): filter/dedupe/join · mark-handled idempotency · missing-file never-raise · endpoint roundtrip. (Anon-reject security-suite convention me covered.)
- **Rollback:** UI tab + endpoints additive — `git checkout` 3 files. Data me sirf `hq_status/hq_done_at` keys add hote (backward-safe).

## Self-review notes
- Scope: single plan me executable; koi TBD nahi. Classifier-quality risk explicitly Track 1 me mitigated (manual eyeball + feedback loop). Track 4 deliberately user-action-gated — koi compliance shortcut nahi.
- Ambiguity resolved: "1500/day" = Track 4 ramp end-state, not Day-1 commitment; Day-1 revenue path = Track 1-2.
