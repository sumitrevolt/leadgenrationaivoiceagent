# Landing-Page Voice Onboarding — Design

**Date:** 2026-07-03 · **Status:** APPROVED (user: "han") · **Owner:** Sumit
**Goal:** `/app/test-call` ko landing page ka ek real onboarding-path banao — prospect AI se browser me baat kare aur usi call/session me free-trial account ban jaaye, bina WhatsApp/phone pe switch kiye.

## Current state (live today, commit 048f0b5, 2026-07-03 morning)

Close-the-loop plumbing already prod me hai:
- `TelecallerBrain._on_close_signal()` (`app/voice_agent/telecaller_brain.py:775-821`) — close-intent detect + phone known hone par ek `sales_pipeline` deal (`stage="negotiating"`) banata hai, phir fire-and-forget `_send_close_whatsapp()` (`:823-851`) call karta hai. Gate: `self.caller_phone` khali ho to silent no-op (`:799`).
- `_send_close_whatsapp()` generic message bhejta hai: *"7-din FREE trial yahan shuru karein: https://leadsgenai.in/start"* — koi query-param nahi, `VOICE_CLOSE_WHATSAPP=1` prod pe ON.
- Payment ke baad `app/platform/upi_payments.py` `_mark_deal_won()` + `_trigger_onboarding()` (deal "won" flip + Celery `onboard` job front-run) — ye already sahi kaam karta hai, is design me iska koi part badalta nahi.
- `web_call.py` ki WS session already `TelecallerBrain` instance ko `session["tcbrains"]` me cache karta hai (`web_call.py:964-989`) — ek hi instance pura session jeeta hai.

**Gap** (jo customer-onboarding-via-call ko todta hai):
1. Landing page pe sirf chhoti footer-link hai ("🎧 Live Demo"), aur page pe "**TEST MODE**" banner hai — real customer trust nahi karega.
2. WhatsApp link generic hai — customer ko sab dobara type karna padta hai.
3. **Sabse bada gap:** onboarding sirf WhatsApp round-trip se hota hai — customer ko browser chhodna padta hai. Same-session me signup poora karne ka koi rasta nahi.

## Design — 4 additive pieces

### 1. Landing-page CTA
`frontend/website/index.html` hero section me ek prominent button add: *"📞 Abhi AI se baat karo — free trial shuru karo"* → `/app/test-call`. `frontend/pricing.html` pe bhi secondary option: "ya AI se baat karke shuru karo" (existing footer links jo already `/app/test-call` point karte hain unhe hero-level prominence tak upgrade karna hai, naya link type nahi).

### 2. Honest, trust-building copy (no new URL, same `/app/test-call`)
`frontend/web_call.html` "TEST MODE" banner (lines 242, 475-476, 577, 845-846) reword: *"🔒 Free & safe — koi charge nahi, koi real phone call nahi, sirf browser me AI se baat karo."* Meaning same rehta hai (no charge/no real call), sirf "TEST" ka stigma hatta. Internal staff-tuning use unaffected (same page, same UI).

### 3. Personalized handoff link (extends existing flagged flow, no new flag)
`telecaller_brain.py::_send_close_whatsapp()` ka bare `https://leadsgenai.in/start` → query-string ke saath: `?phone=<digits>&biz=<urlencoded client_name>&niche=<niche>` (`biz` param omit ho agar `client_name` khali hai — jaisa `ai_marketing` persona ke liye already hota hai, `_on_close_signal` line 807). `frontend/pricing.html` (jo `/start` serve karta hai) load pe `URLSearchParams` se `phone`/`biz` padhe aur business-name/phone form-fields prefill kare — customer sirf email+password confirm kare.

### 4. Same-session in-page signup (the core fix) — flag-gated `WEBCALL_INLINE_SIGNUP` (default OFF)
Naya `self.close_signal_fired` bool `TelecallerBrain.__init__` me — `reply()` ke shuru me har turn `False` reset, `_on_close_signal()` ke andar phone-guard pass hone ke baad `True` set. Koi return-signature change nahi (existing `reply() -> str` contract untouched — zero-risk).

`web_call.py`'s `_brain_turn()` me, `tc_reply = await tcbrain.reply(...)` ke turant baad: agar `WEBCALL_INLINE_SIGNUP=1` aur `tcbrain.close_signal_fired` True hai, ek naya WS message bhejo:
```json
{"type": "close_signal", "business_name": tcbrain.client_name, "niche": tcbrain.niche, "phone": tcbrain.caller_phone}
```
(naya `type`, docstring `web_call.py:16-26` ki list me add karna — koi existing type overload nahi).

`frontend/web_call.html`'s WS dispatch (`:468-513` `if/else if` chain) me naya branch: `close_signal` aate hi ek chhota overlay-form dikhao — prefilled business-name/niche/phone (readonly), sirf email+password maango. Submit → seedha `POST /api/public/signup` (existing endpoint, `plan="trial"`, `app/api/public_site.py:504-620`) — koi naya backend account-creation code path nahi, wahi proven validation + anti-hijack dedupe (`:570-575`) reuse hota hai. Success response ka JWT (`:592-598`) localStorage me store karke seedha `/app/customer` redirect (jaisa `pricing.html` ka existing signup-success handler already karta hai — same pattern copy karna, dobara invent nahi).

## Explicitly OUT of scope (YAGNI)
- Voice se password bolna/sunna — insecure + bad UX, form-field hi rahega.
- Naya OTP/SMS phone-verify system — existing `add_client()` phone/business-name dedupe hi spam-gate hai, sufficient for a ₹0 trial.
- `/app/test-call` ka internal tuning-behavior badalna — sirf copy + additive WS-event, staff-flow untouched.
- Naya public URL/alias (e.g. `/talk`) — literal ask "test-call ko landing page pe lao" ko follow kiya, ek hi URL reuse.

## Files touched
| File | Change |
|---|---|
| `app/voice_agent/telecaller_brain.py` | `close_signal_fired` flag (init+reset+set); `_send_close_whatsapp()` personalized query-string |
| `app/api/web_call.py` | post-`reply()` check + `close_signal` WS emit, flag-gated `WEBCALL_INLINE_SIGNUP` |
| `frontend/web_call.html` | banner reword; `close_signal` WS branch + inline signup overlay + submit→`/api/public/signup` |
| `frontend/website/index.html` | hero CTA button |
| `frontend/pricing.html` | `?phone=&biz=` query-param prefill on load |

## Compliance
Koi naya surface nahi — inline signup wahi `/api/public/signup` validation+dedupe reuse karta hai jo form-path already use karta hai. AI-disclosure call-start pe unchanged. Web-mic call inbound/self-triggered hai, DLT/DND gate lagta hi nahi (existing confirmed fact, CLAUDE.md).

## Testing plan
- `telecaller_brain.py`: naya test — `close_signal_fired` set/reset per-turn; existing `test_on_close_signal_no_whatsapp_task_without_phone` green rehna chahiye (regression); personalized-link test (biz present vs blank-ai_marketing case).
- `web_call.py`: flag-OFF → koi `close_signal` message kabhi nahi (regression safety); flag-ON + `close_signal_fired=True` → exact JSON shape.
- Frontend: manual WS-probe (existing `web-call-triage` skill method) — close-signal trigger karke overlay render + signup POST + dedupe-on-double-submit confirm.
- `/pricing?phone=..&biz=..` manual prefill check.
- Full regression: relevant `tests/test_*voice*`/`test_*web_call*`/`test_*sales*` suites + `scripts/prod_check.py` green.

## Rollback
Sab additive + `WEBCALL_INLINE_SIGNUP` default OFF (disables overlay+WS-event completely, zero behavior change). Link-personalization degrades gracefully even if `/pricing` prefill-read kabhi fail ho (extra query-params bas ignore ho jaate). Copy/CTA changes = plain revert via `git checkout`.

## Self-review notes
- Placeholder scan: koi TBD nahi, sab concrete file:line ke saath.
- Consistency: Part 3 (link personalize) aur Part 4 (inline overlay) dono independently ship-able hain — Part 4 fail/delay ho to Part 1-3 akela bhi improvement hai (staged rollout possible).
- Scope: single implementation plan me executable, 5 files, sab additive.
- Ambiguity resolved: "real onboarding" = full self-serve trial account (business-name+email+password → `/api/public/signup`, `plan=trial`, $0), NOT full voice-spoken account-creation aur NOT sirf hot-lead-handoff — existing proven signup endpoint hi target hai, browser-native flow.
