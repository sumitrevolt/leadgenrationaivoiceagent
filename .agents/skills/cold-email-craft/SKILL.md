---
name: cold-email-craft
description: B2B cold-email copy craft for Rohan's daily outreach (auto_outreach.py) — Hinglish subject lines, 3-line bodies, CTA, D3/D7 follow-ups, OUTREACH_AB subject variants. Use jab "cold email", "outreach copy", "reply nahi aa rahe", "subject line", "follow-up sequence", ya `_email_subject_body`/`DEFAULT_SUBJECT_VARIANTS` templates upgrade karne ho.
---

# Cold Email Craft (Hinglish Indian-SMB)

Rohan roz 10:30 IST max 25 MX-verified emails bhejta (`app/platform/auto_outreach.py`). Copy yahin se nikalti hai — is skill se templates upgrade karo, naya sender-engine MAT banao.

## Where the copy lives
- **Body**: `auto_outreach.py` `_email_subject_body(prospect)` → (subject, text, html). Real Google signal (rating/reviews) acknowledge karta hai — yeh personalization pattern RAKHO.
- **Subject A/B**: `app/marketing/outreach_variants.py` `DEFAULT_SUBJECT_VARIANTS` (spintax, gated `OUTREACH_AB=1` — ON). Naya variant = is list me add.
- **Follow-ups**: Day-3/Day-7 same module me. Cap 25/day + warmup ramp (`email_warmup.py`) — volume kabhi mat badhao, copy quality badhao.

## Rules (distilled, India-tuned)
1. **Peer, not vendor.** Padh ke lage colleague ne bheja. "I hope this email finds you well" / "leverage" / ALL-CAPS = delete.
2. **Subject = chhota, boring, internal-looking.** 3-6 words, lowercase-ish, no emoji/urgency. Business ka NAAM dalo (Indian SMB owner apna naam dekhte hi kholta hai).
3. **3-line body**: (a) REAL observation (rating/reviews/city — prospect dict me hai), (b) ek specific problem + hum kya karte, (c) low-friction ask. Har sentence kamai kare, warna cut.
4. **CTA = interest-based, 1-line reply yogya.** "Free audit bhej doon?" > "30-min call book karein?". WhatsApp number footer me (SMBs WA prefer karte).
5. **Follow-up = naya angle, never "just checking in".** D3 = proof/sample (3 posters offer), D7 = polite breakup ("aakhri mail — kabhi zaroorat ho to ye link"). Har email standalone padhe.
6. **Honest hamesha** — fake stats/clients nahi; unsubscribe line rakho (sender-rep + law).

## Ready Hinglish templates
- **Subject (generic)**: `{name} — Google profile pe ek cheez dikhi` · `{name} ke reviews` · `{city} me naye customer` · `{name} — free audit`
- **Niche-agnostic body**: "Namaste — maine {name} ka Google profile dekha, {rating}⭐ aur {reviews} reviews, achhi shuruat hai. Par naye customer tak pahunchne me 2-3 cheezein miss ho rahi hain (photos/posts/reply pattern). Free audit report bhej doon? 1-line reply kaafi hai."
- **Solar**: Subj `{name} — subsidy wale customer`. "Subsidy ke chakkar me log roz Google pe solar installer dhoondte hain — {city} me aapka profile unhe poora convince nahi kar raha. Humne ek solar client ke liye inquiry-flow set kiya tha; wahi free audit aapke liye banaa doon?"
- **Gym**: Subj `{name} — naye members ka season`. "New year/monsoon-baad gym search badh jaati hai, par {name} ke recent posts/offers Google pe nahi dikh rahe. 3 ready-made posters + free profile audit bhejun? Pasand aaye tabhi aage baat."
- **D7 breakup**: Subj `aakhri email :)`. "Lagta hai abhi sahi time nahi — koi baat nahi. Free audit link rakh lijiye: leadsgenai.in/audit. Kabhi zaroorat ho to seedha WhatsApp kar dena. Shubhkamnayein!"

## Verification
Template change ke baad: `pytest tests/ -k outreach` green · spam-smell check (caps/emoji/links ≤1) · `OUTREACH_AB` variant count balanced · live me reply-rate `reply_agent` triage se dekho.

Adapted from coreyhaines31/marketingskills (via VoltAgent/awesome-agent-skills)

> Cross-link (2026-07-05): generic copy-craft rules ka authoritative source = `cold-email` skill — yahan sirf India/project-specific deltas rakho.
