# AI Voice Calling Agent — Best Pitch (research-backed, 2026-06-25)

> Product 2 (standalone full AI telecaller). Page: `/voice-agent`. Pricing: `app/voice_packages.py`.
> This is the **sales/positioning source-of-truth**. Landing copy = `frontend/voice-agent.html`; compare page = `frontend/compare.html`.
> Deep-research inputs (2026): Indian Voice-AI market, competitor pricing, buyer eval criteria, SOTA stack. Citations at bottom.

---

## 0. One-line positioning (sharpened)

**Old:** "Hinglish AI telecaller jo leads qualify karke deta hai."

**New (sharper, defensible):**
> **"India-legal Hinglish AI telecaller — flat monthly, unlimited calls, aur ab khud appointment book + CRM update + WhatsApp follow-up karta hai. Per-minute vendors se 60-80% sasta, kyunki free AI stack pe bana hai."**

The three words that win the deal: **Flat. Legal. Agentic.**

---

## 1. The wedge — flat-monthly vs per-minute (lead with the math)

Every serious India competitor bills **per-minute or per-outcome**. That is the attack surface.

| Vendor | Pricing (2026) | Real monthly cost @ ~3,000 connected min* |
|---|---|---|
| Bolna | ~₹5.52/min | **~₹16,560** |
| Caller Digital | ₹4–6/min (or ₹8–25/outcome) | **~₹15,000** |
| Tabbly | ~₹6.80/min | **~₹20,400** |
| Retell (DIY stack) | $0.07/min orchestration + $0.13–0.31/min stack (~₹6–11/min all-in) | **~₹18,000–33,000** |
| Bland | $499/mo + $0.11/min | **₹41,000+ +/min** |
| SquadStack | per-call/per-lead, Basic from ₹22,425 | **₹22,425+** |
| Gnani | enterprise ₹40L–₹4Cr ACV | **out of SMB reach** |
| **LeadsGenAI Band A** | **₹4,999 flat, unlimited** | **₹4,999 (fixed, never scales up)** |

\* ~2,000 calls/mo × ~1.5 min connected. **The point to hammer:** per-minute bills *grow with success* — jitne zyada leads aap call karoge, utna zyada bill. Flat = predictable; scale free. **At even modest volume we're 60–80% cheaper; the gap widens every extra call.**

**Verbal line:** *"Inka bill aapke success ke saath badhta hai — zyada call = zyada paisa. Hamara fixed hai. Aap jitni marzi call karo, ₹4,999 hi rahega."*

---

## 2. The three research-backed pillars

The 2026 India buyer's guide (Caller Digital) lists exactly six things buyers evaluate. We map our pitch to the three where we genuinely win:

### Pillar A — Compliance is the product, not fine-print
Research finding: *"Compliance is the product, not a checkbox"* is the top deal-winner; buyers' #1 fear is a **number ban / TRAI notice**. Many vendors have *"no published TRAI/DPDP architecture."*

Our claim (all already in code — `compliance.py`, consent ledger, DND fail-closed):
- TRAI **AI-disclosure** every call ("ek AI assistant…") — built into the greeting leg, barge-locked so it's always heard.
- **9am–7pm** calling window (conservative — TRAI allows 9–9), **DND scrub fail-CLOSED** (lookup fail = block, not call).
- **DPDP** consent ledger + instant opt-out (press-9 / "band karo") + 90-day recording retention.
- **No foreign trunks** — India-domestic foreign-trunk calling is illegal; we're 140-series/DLT native.

**Verbal line:** *"Aapka number ban nahi hoga. Compliance hamara feature hai — har call pe AI-disclosure, DND respect, 9-7 window, sab automatic."*

### Pillar B — Hinglish telephony-grade (the eval bar)
Research bar: *"Does the model handle 8 kHz telephony-codec Hindi with a Bhojpuri accent on a 2G fallback network?"*

Our claim:
- Hinglish + **code-switching** native (Groq Whisper-large-v3 → Gemini audio-in → local fallback; LLM mirrors caller's language).
- Female agent "Riya/Swara", warm natural Hindi TTS (Gemini native TTS "Leda" → EdgeTTS Swara fallback), prosody-tuned for phone.
- Domain-primed STT (niche entity bias) so "solar subsidy", "home loan", "IVF" transcribe right on noisy lines.

### Pillar C — Free-stack = structural price moat
Why we can be flat-and-cheap when others can't: we run a **free multi-provider AI stack** (own LLM chain Mistral→Groq→Cerebras→…, free STT, free TTS) — **zero imported per-minute AI fees**. Competitors resell metered ElevenLabs/Deepgram/OpenAI, so they *must* charge per-minute. Our only real cost = telecom + platform. **The price advantage is structural, not a discount we can't sustain.**

---

## 3. NEW (2026 advancement) — "Agentic", not just a talker

> This is the upgrade that moves us from "AI that talks" to "AI that *does the work*."
> **Status:** in-call tool execution is WIRED into BOTH live brain paths — phone (`vobiz_stream`) **and the web-call demo** (`web_call.py`), via the shared `voice_tools.run_tool_turn` (`VOICE_TOOLS=1`, gated; `app/voice_agent/voice_tools.py` + `function_calling.py`). Web-call parity matters because cold phone outbound is DLT-gated, so the **web-call is the live demo/trial channel** — the agentic feature is now demonstrable there. Enable per client after a free web-call test.
> **Booking is now REAL (no-OAuth, free):** `book_appointment` writes to a durable bookings ledger (`data/bookings/`) that survives restarts, and the business owner is notified instantly (ntfy + email, `BOOKING_NOTIFY` default ON). Admin sees them at `GET /api/admin/voice/bookings`. Optional calendar sync: Cal.com (BYOK `CALCOM_API_KEY`, no OAuth) or Google Calendar — both fall back to the internal ledger.

- **Books the appointment** live on the call (checks slot, confirms) — `book_appointment` / `check_availability`.
- **Captures + structures the lead** (budget, timeline, decision-maker) → straight to dashboard/CRM/webhook — `capture_lead_info` (also runs post-call via `_auto_qualify` → `apply_qualified_downstream`, already live).
- **Sends the WhatsApp follow-up** draft the moment a lead is interested (existing cadence/whatsapp draft path).
- **Warm-transfers hot leads** to a human with a context brief — `transfer_to_human` *(needs Vobiz recharge + DID + `CALL_TRANSFER`; DLT-gated like all cold-outbound)*.

**Pitch line:** *"Yeh sirf baat nahi karta — appointment book karta hai, CRM update karta hai, WhatsApp follow-up bhejta hai, aur hot lead aate hi aapko live transfer karta hai. Ek poori telecalling team, ek AI me."*

---

## 4. Quantified band examples (close the "which plan" gap)

| Band | Sample niches | Flat/mo | "What you get" framing |
|---|---|---|---|
| **A — Volume** | Solar (residential), Insurance, Coaching, Gym, Salon, Real-estate agent | **₹4,999** | High call volume, thinner margins → unlimited reactivation + inquiry callback at one fixed price. |
| **B — Mid-premium** | Home loans, Study-abroad, Dental implants, Modular kitchen, Finance advisory | **₹9,999** | Considered purchases → qualification + multi-touch follow-up where each closed deal pays the year. |
| **C — Premium/HNI** | IVF clinics, Immigration, Hair transplant, Commercial solar | **₹19,999** | One closed client = months of fee. AI never misses a callback at 9pm-inquiry. |

Annual = 10× monthly (2 months free). **Free pilot: 7 days / 50 real calls, no card.**

**Self-select script:** *"Aapka niche bataiye — main aapko band bata deta hoon. Phir 50 free calls aapki database pe; result dekhke decide karna."*

---

## 5. Objection handling (incl. gaps the old page missed)

| Objection | Answer |
|---|---|
| "Kitni calls included?" | **Unlimited** — flat fee, koi per-call/per-lead/quota nahi. |
| "Itna sasta kaise?" | Free/open AI stack — koi imported per-minute AI fee nahi. Structural, sustainable. |
| "Legal hai?" | AI-disclosure + 9-7 window + DND fail-closed + DPDP. Cold-outbound DLT ke baad; tab tak inbound/consented/own-database. |
| **"AI galat lead qualify kar de to?"** *(was missing)* | Har call ki **recording + transcript** milti hai — aap verify kar sakte ho. Flat billing hai, isliye galat/na-uthe call ka koi alag charge nahi; misqualify pe dispute nahi, kyunki aap raw call dekh sakte ho. |
| **"Setup me kya dena padega?"** *(was missing)* | Sirf: business name, products/prices, area, aur (optional) website — AI uska KB bana leta hai. Din 1 live. CRM/webhook optional. |
| **"Pilot ke baad kya?"** *(was missing)* | 50 calls ke baad hum aapke niche ka band recommend karte hain + actual qualified-lead count dikhate hain. No auto-charge. |
| "Human telecaller se better?" | Human ₹15–25k/mo + training + churn + 8hr/day. AI: ₹4,999 se, no churn, har inquiry instant callback, recording har call. |

---

## 6. Ready-to-use pitch assets

**30-second verbal (cold):**
> *"Namaste — main LeadsGenAI se. Hum ek India-legal Hinglish AI telecaller dete hain jo aapki inquiries, missed-calls aur purani database ko call karke qualify karta hai — aur ab appointment book, CRM update, WhatsApp follow-up khud karta hai. Per-minute vendors ₹15-20 hazaar mahina le lete hain; hamara flat ₹4,999, unlimited calls. 50 free calls aapki database pe — try karke dekhiye?"*

**WhatsApp one-liner:**
> *"AI telecaller jo aapke leads ko Hinglish me call karke qualify + book karta hai. Flat ₹4,999/mo, unlimited calls, India-legal (TRAI/DND built-in). 50 calls FREE — link: leadsgenai.in/voice-agent"*

**Landing headline options (A/B):**
1. "Aapka AI Telecaller jo sirf baat nahi — appointment book karta hai." 
2. "Per-minute bill bharna band karein. Flat ₹4,999, unlimited AI calls, India-legal."
3. "Insaan-jaisi Hinglish AI calling — flat monthly, koi per-minute surprise nahi."

---

## 7. Sources (deep research, June 2026)
- Indian Voice-AI market $153.01M (2024) → $957.61M (2030), 35.7% CAGR.
- Competitor pricing: Bolna ~₹5.52/min; Caller Digital ₹4–6/min or ₹8–25/outcome; Tabbly ~₹6.80/min; Retell $0.07/min + $0.13–0.31/min stack; Bland $499/mo+$0.11/min; SquadStack Basic ₹22,425 / Pro ₹59,800; Gnani ₹40L–4Cr.
- Buyer eval (Caller Digital "Top 10 AI Calling Platforms India 2026"): Indian-language depth, TRAI DLT/DPDP, pricing model, integration depth, use-case benchmarks, 7–14 day deployment; "compliance is the product."
- SOTA latency (futureagi/trillet/softcery 2026): sub-500ms aggressive / sub-700ms accepted; streaming STT <300ms, TTS <100ms first-audio, LLM <300ms.
