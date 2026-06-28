# First Customer — 7-Day Acquisition Sprint (Product 1: AI Automated Marketing)

> **Banaya:** 2026-06-28 (revenue-first sprint goal). **Builds on:** `docs/GTM_PILOT_PLAYBOOK.md` (strategy) + `docs/Sales_Kit_Hinglish.md`. Yeh doc = **execution pack** (day-by-day + scripts + SOPs + checklists).
> **Platform status:** GREEN — `ready_for_first_paid_customer=true`, 0 blockers, UPI LIVE (`8459012607@axl`). Code bottleneck NAHI hai — **execution** hai. Deal insaan close karta, automation sirf activity banata.
> **Pricing (LIVE truth, `packages.py`):** Starter **₹1,999/mo** · Combo (Marketing+Voice feature) **₹5,999/mo**. Pilot pe sirf **Starter** becho.
> **Scope guardrail:** sirf Product 1 (Marketing). Voice cold-calling = DLT+Vobiz tak HAATH MAT lagao.

---

## 0. The Offer (proof-first, friction-zero)

> "Pehla hafta **₹0** — main aapka marketing AI se khud chalaa ke result dikhata hoon (Google pe dikhna, daily content, leads). Pasand aaye to **₹1,999/mo**, nahi to band — koi contract, koi card nahi."

- **Kyun ₹0 pilot:** abhi koi case-study nahi → trust-barrier ₹0 todta hai. Maqsad = pehla **paid logo + proof** (1 result-screenshot + 1 testimonial).
- **Success metric (7 din):** **≥1 UPI-activated paid customer** (₹1,999) YA 3 live pilots jo Day-8/10 pe paid convert honge.
- Warm/referral lead jo already trust karta → seedha **₹1,999/mo paid** offer karo (pilot skip).

---

## 1. Target — Nagpur local SMBs (ONE niche × ONE city = leverage)

Ek niche pakdo is hafte (referral + "main aapke ilaake me X businesses ke saath kaam kar raha hoon" credibility). Nagpur ke liye ranked picks:

| Rank | Niche | Kyun Nagpur me strong | Pain (jo hum bharte) |
|---|---|---|---|
| **#1 PICK** | **Solar dealers/installers** | Vidarbha sun-belt, govt subsidy demand high, dealers ko leads chahiye | Online dikhna nahi, inquiry follow-up weak |
| #2 | **Coaching / tuition classes** | Nagpur = education hub (NEET/JEE/MPSC) | Admission season leads, daily social presence |
| #3 | **Real-estate brokers** | Plots/flats active market | Listings ka online reach, lead capture |
| #4 | **Interior designers / modular kitchen** | Mid-income housing growth | Portfolio dikhana, inquiry-to-meeting |
| #5 | **Dental / skin / diet clinics** | High-margin, repeat-patient | Reviews + appointment leads |

> **Is hafte SIRF #1 (Solar dealers — Nagpur).** Focus = referrals + neighbourhood credibility. Baaki backup.

---

## 2. 50-Prospect List Strategy (LEGAL sources only)

> **COMPLIANCE HARD RULE:** Justdial / IndiaMART / Sulekha / LinkedIn / FB / Insta ka **auto-scrape KABHI nahi** (ToS + IT-Act). Manual note (founder khud public listing dekh ke likhe) = theek. Automation = nahi.

**Target: 50 verified Solar-dealer prospects (naam + phone + area), 1-2 ghante me.**

| # | Source | Kaise (step) | Expected |
|---|---|---|---|
| A | **Platform Prospector** (`/app/outreach` → Google Maps Places, real phones+reviews) | Niche="solar", city="Nagpur" → run. Cap `PROSPECT_MAX_LOOKUPS=60`/run. | ~30-40 |
| B | **OSM Overpass fallback** (platform, keyless) | Prospector auto-falls-back; ya manual Overpass `shop=solar`/`craft` Nagpur bbox | ~10 |
| C | **Google Maps manual** ("solar dealers Nagpur", "solar EPC Nagpur") | Public listing se naam+phone copy (manual, ToS-safe) | 10-15 |
| D | **GBP / Google search** ("solar installer Nagpur sitabuldi/dharampeth/...") | Area-wise public profiles | top-ups |
| E | **Referral / walk-in** | Jaan-pehchaan, local electrical market visit | 5 (best-quality) |

**Process:**
1. `/app/outreach` se Maps prospect run → CSV/list export → leads `clients`/prospect store me.
2. Dedupe + phone-verify (platform MX/phone clean already karta).
3. Manual sources (C/D/E) se gaps bharo → ek sheet: `Naam | Area | Phone | Source | Status`.
4. **NICHE_ROTATION/LEAD_HARVESTER already ON** — roz auto top-up bhi aata rahega.

> Quality > quantity: 50 verified Nagpur-solar > 500 random. Founder in se roz 20-30 ko khud touch karega.

---

## 3. The 7-Day Plan (day-by-day)

| Day | Focus | Concrete actions | Target |
|---|---|---|---|
| **Day 0 (prep)** | Setup | Demo assets ready (Section 7), 50-list banao (Section 2), apna LeadsGenAI sample mini-site/content pack handy | List=50 |
| **Day 1** | First touch | 25 WhatsApp/call (Section 4-5 script). Hot reply → 1 ghante me khud call. | 25 touched, 2-3 interested |
| **Day 2** | Follow + demo | Day-1 no-replies ko D1 follow-up. Interested ko **live demo** (Section 6). | 2 demos |
| **Day 3** | Pilot start | "Haan" walon ko **same-day onboard** (Section 7). Mini-site + content live. | 1-2 pilots live |
| **Day 4** | Result build | Pilots ke liye 1 **visible result** banao (GBP optimize / 1 lead / content calendar) → screenshot. New 25 touches. | 1 result-shot |
| **Day 5** | Show + close | Result dikha ke: "Pasand aaya? ₹1,999/mo se continue" → **UPI** (Section 8). | 1 paid ask |
| **Day 6** | Activate | UPI screenshot verify → activate (Section 8). Day-1 success (Section 9). | **1 PAID ✓** |
| **Day 7** | Proof + scale | Logo + testimonial + result-shot → landing pe. Pipeline review, agle hafte ka 50-list. | proof + plan |

**Roz shaam (5-min tracker):** reach kiye / reply / demo / pilot-haan / paid. (3-5 pilot-haan ya 1 paid = hafta safal.)

---

## 4. Manual Sales Call Script (founder, Hinglish)

**Open (10 sec):**
> "Namaste [Naam] ji, main [Tumhara naam] LeadsGenAI se. 30 second loonga — aap solar ka kaam karte ho Nagpur me, sahi? Main aapke jaise dealers ka online marketing AI se chalata hoon — Google pe dikhna, roz content, aur jo inquiry kare uska turant follow-up."

**Discover (1-2 sawaal — sunna zyada):**
> "Abhi aapke leads kahan se aate hain — reference se ya online bhi? Aur Google/Insta pe regular post karne ka time milta hai?"

**Pitch (pain → outcome):**
> "Dekhiye, problem ye hai ki customer pehle Google pe dekhta hai — wahan aap strong nahi dikhte to lead competitor le jaata. Main wahi fix karta hoon: aapka mini-site + Google profile, roz ready-to-post content, aur inquiry ka auto follow-up. **Pehla hafta free** chala ke result dikhata hoon — pasand aaye to ₹1,999/mo, warna band."

**Objections:**
- *"Time nahi / samajh nahi aata"* → "Aapko kuch nahi karna — setup main karta hoon, aaj hi. Aap bas leads dekhna."
- *"Mehenga to nahi?"* → "Ek lead ka solar deal hi ₹X hai — ₹1,999/mo me agar mahine me 1 extra lead bhi aaya to ye free pad gaya. Aur pehla hafta to ₹0 hi hai."
- *"Pehle dekhna hai"* → "Bilkul — 2 min ka demo abhi WhatsApp pe bhej deta hoon, ya 5 min me live dikha doon?"
- *"Baad me"* → "Theek hai, free pilot ka slot is hafte hai — main aaj setup kar doon, pasand na aaye to band. Risk ₹0."

**Close:**
> "Bढ़िया — main aaj aapka setup kar deta hoon, kal tak aapko content + mini-site link dikha doonga. Bas business ka naam, area aur ek photo/logo WhatsApp kar dijiye."

---

## 5. Cold Email + WhatsApp Scripts (human-send only)

> **COMPLIANCE:** WhatsApp = **1-click human send** (bulk auto = number ban). Email = founder/Rohan personalized, cap 25/day, MX-verified. Koi bulk auto-blast nahi.

### WhatsApp opener (copy/paste, personalize [..])
> "Namaste [Naam] ji 🙏 Main [naam] — LeadsGenAI. Nagpur ke solar dealers ka online marketing AI se chalata hoon (Google pe dikhna + roz content + leads ka follow-up). Aapke liye **pehla hafta free** chalaa ke result dikhaun? Pasand aaye to ₹1,999/mo, warna koi baat nahi. 👍"

### "Kya hota hai usme?"
> "Aapka ek mini-site + Google profile optimize, roz social content ready, aur jo inquiry kare usko AI se turant follow-up. Aap bas leads dekho — setup main karta hoon, aaj hi shuru. 5 min lagega."

### Follow-up D1 (no reply)
> "[Naam] ji, bas free pilot ka pooch raha tha — 5 min me setup, koi paisa nahi pehle hafte. Ek baar try karein? 🙂"

### Result-ready (pilot ke baad)
> "[Naam] ji 👀 dekho — aapka [mini-site link] live hai + ye raha aaj ka content. [screenshot]. 1 hafte me aur aayega. Continue karein ₹1,999/mo pe?"

### Cold email (Rohan/founder — subject + 3-line body)
- **Subject A:** `[Business] ke liye Google pe zyada solar leads?`
- **Subject B:** `Nagpur solar — 1 hafta free marketing trial`
> "Namaste [Naam] ji, main [naam] LeadsGenAI se. Nagpur ke solar dealers ka online marketing (Google profile + daily content + lead follow-up) AI se chalata hoon. **Pehla hafta ₹0** — result pasand aaye to ₹1,999/mo. 2-min demo bhejun? — [naam], [phone]"
- **D3 follow-up:** "[Naam] ji, upar wale free-trial ka reminder — abhi slot hai. Haan/na ek line me bata dijiye. 🙏"

---

## 6. Demo Checklist (live, 5 min)

- [ ] **`/audit`** — prospect ka business naam/website daal ke live GBP/site audit score dikhao (instant "aapka ye-ye missing hai" hook).
- [ ] **Sample mini-site** `/b/{slug}` — ek ready client ka (ya apna) — "aisa aapka banega".
- [ ] **Content pack** — 2-3 ready Hinglish posts + branded poster (unke niche ka).
- [ ] **Customer portal** — "yahan roz content aata, 1-click WhatsApp share, leads sab".
- [ ] **Lead widget** — "ye aapki site pe lagega, inquiry seedha yahan."
- [ ] **Pricing clarity** — "₹1,999/mo Starter, pehla hafta free. Combo ₹5,999 me AI voice callback bhi (baad me)."
- [ ] Close: "Setup aaj — naam + area + logo bhej do."

---

## 7. Onboarding Checklist (haan ke baad — SAME DAY)

- [ ] **`/app/clients`** (ya admin `POST /api/admin/customers/onboard`) — client add: business_name, niche=solar, city=Nagpur, phone, plan=`trial` (pilot) ya `starter` (direct paid).
- [ ] Login banao → email + password customer ko bhejo (`/app/login`).
- [ ] **Mini-site** `/b/{slug}` auto-banta — link verify + customer ko bhejo.
- [ ] **AUTO_ONBOARD** (ON): website→KB seed + first content pack + **day-1 content queue** (ab onboarding queue bhi bharta — portal pe content turant dikhta, ≤50-min sweep). Verify `/app/customer/marketing` → "Aapka Content" me items aaye.
- [ ] **Widget** embed snippet customer ki site ke liye do (`/b/{slug}/widget.js`).
- [ ] GBP audit chala ke top-5 fixes customer ko bhejo (Day-1 visible value).
- [ ] Customer ko portal walkthrough (2-min WhatsApp voice-note ya call).

---

## 8. UPI Activation SOP (paisa → activate)

> **Payment rail LIVE.** Razorpay nahi — manual UPI. VPA `8459012607@axl`.

**Customer side (self-serve, portal pe):**
1. `/app/customer` → "💳 Plan lena hai? UPI se pay karo" box.
2. QR scan / VPA pe pay (Starter ₹1,999 ya Advanced ₹5,999).
3. **"✅ Maine Pay Kiya — Submit"** → plan chuno + UPI ref no. daalo (ya WhatsApp pe screenshot `918459012607`).

**Admin side (founder, 1 min):**
1. Submission aata: `GET /api/admin/upi/pending` (ya `/api/upi/pending`) — admin UI me list.
2. UPI ref / screenshot verify karo (paisa aaya bank/UPI app me).
3. **Activate:** `POST /api/admin/upi/activate` `{client_id, plan, clear_trial:true}` (ya admin UI button). → plan set + usage period reset + `payment.received`/`subscription.activated` webhooks fire.
4. Confirm: client `status=active`, plan correct. Customer ko WhatsApp: "Activate ho gaya ✓ — portal me sab unlock."
5. GST invoice (`GST_GSTIN` set ho to) portal me auto.

> **Reject path:** paisa na mile → `/api/upi/pending/{pid}/reject`. Idempotent — double-activate nahi hota.

---

## 9. Customer Success — Day 1 / Day 7

### Day-1 checklist (activate hote hi)
- [ ] Welcome WhatsApp + portal login confirm.
- [ ] Portal me **content queue bhara** dikhe (≥3 posts/poster) — NA dikhe to admin `auto_onboard`/daily-content trigger karo.
- [ ] Mini-site `/b/{slug}` live + link diya.
- [ ] GBP audit + top-5 fixes share kiye.
- [ ] 1 "quick win" set (Google profile update ya 1 post publish) → screenshot.
- [ ] Expectation set: "Roz subah ~7 baje naya content. Inquiry aaye to turant dikhega."

### Day-7 checklist (retention + proof)
- [ ] 7-din ka result recap: kitna content gaya, GBP improve, koi lead/inquiry.
- [ ] **Proof maango:** 1-line testimonial + logo use permission + result-screenshot.
- [ ] Upsell soft: "Combo ₹5,999 me inquiry pe AI voice callback bhi (jab DID live ho)."
- [ ] Renewal/continue confirm (agar pilot tha → paid ₹1,999 ko convert).
- [ ] Referral ask: "Aapke jaise 1-2 aur solar dealer jaante ho jinko leads chahiye?"

---

## 10. Compliance Guardrails (kabhi cross mat karo)

- ❌ Justdial / IndiaMART / Sulekha / LinkedIn / FB / Insta **auto-scrape** — manual note only.
- ❌ WhatsApp **bulk auto-send** — sirf 1-click human send.
- ❌ Cold-email volume spike — cap 25/day, warmup, MX-verified (domain reputation).
- ❌ Voice **cold-calling** — DLT + Vobiz DID tak band. Inbound callback bhi abhi nahi becho.
- ✅ Email unsubscribe (RFC8058) + consent honor — always.

---

## 11. Daily Tracker (founder, shaam 5-min)

```
Din ___  | Reach: ___  Reply: ___  Demo: ___  Pilot-haan: ___  PAID: ___
Hot leads (naam/phone/next-action):
1.
2.
3.
Kal ka focus:
```

**Hafte ka win = ≥1 PAID (₹1,999 UPI-activated) ya 3 live pilots → Day-10 paid.**

---
*Sources: `docs/GTM_PILOT_PLAYBOOK.md` · `docs/Sales_Kit_Hinglish.md` · `packages.py` (pricing truth) · activation summary (0 blockers). Platform ready — ab sirf yeh chalaana hai.*
