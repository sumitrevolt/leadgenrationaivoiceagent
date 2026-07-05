# 🏢 Office HQ — Chalane ki Guide (Operating Manual)

> **Page:** https://leadsgenai.in/app/office · **Kaun khol sakta:** sirf admin (tu) · **Data:** live, read-only + kuch real actions
> **Ek line me:** yeh tera *AI CEO command center* hai — 31 AI staff, 8 rooms, poora lead→paisa funnel, approvals, aur system health ek hi screen pe. Roz subah yahin se din start kar.
>
> _Last updated: 2026-07-05 (honesty + paisa-first + UX fixes ke baad)_

---

## 1. Roz ka 2-minute routine (yeh follow kar)

Subah / din me 2-3 baar, upar se neeche is order me dekh:

1. **Top status line** (page ke sabse upar): `27/31 agents active · 5 approvals pending · <health>`.
   - Agar `sab automation healthy` — badhiya.
   - Agar `⚠️ ... dead task(s) · mid-funnel ruka` — kuch tootа hai, neeche jaake dekh (ab yeh **honestly** dikhता hai, pehle jhooth "healthy" dikhता tha).
2. **Priority action stack** (beech wala column): sabse upar `👉 Abhi sabse pehle` wala tile = aaj ka #1 kaam. Usi pe click karke jump kar.
3. **Boss brief** (left): `Risk`, `Opportunity`, `Next move` — teeno clickable hain, click karo to us section pe le jaayega.
4. **Hot Queue** check kar (neeche `📥 Reception Hot Queue`): agar garam replies hain = paisa wait kar raha, pehle unhe jawab.
5. Jo urgent na ho use baad me — Office khud automation chalata rehta hai.

**Bas itna hi roz ke liye kaafi hai.** Baaki sab tabhi kholo jab kuch specific karna ho.

---

## 2. Screen ka layout — kya kahan hai

Upar ki nav (yeh section-jump buttons hain, poori page ek hi lambी scroll hai):

| Tab | Kya milega |
|-----|-----------|
| **War Room** | Boss brief + Priority stack + Live pulse (default view) |
| **Priorities** | Full metrics + legacy priority list |
| **Map** | 🗺️ Live pixel-art office — rooms + agents ghoomte hue |
| **Replay** | Aaj ke office moves ka timeline |
| **Pipeline** | 12-stage Lead → Renewal funnel + drill-down |
| **Approvals** | Pending drafts / code-patches (✓/✕ karne ke liye) |
| **Improve** | Team Improvement Council (AI staff discuss karke plan deta) |
| **Health** | System health + Aaj ka Schedule (37 automation jobs) |
| **Scheduler** | Har job ON/PAUSE + run-now control |
| **Reliability** | Failed/dead tasks (DLQ) + retry-sweep |

---

## 3. Agents ko kaam kaise do (yeh sabse important)

Do tareeke hain. **Dono DRAFT-safe hain** — matlab AI *plan/draft* banata hai, khud bina puchhe send/execute NAHI karta. (Yeh safety feature hai — spam/galti se bachne ke liye.)

### A) HQ Copilot box (upar ka bada box) — sabse tez
Box me likhne ke 2 tareeke:
- **Sawal poochho:** _"aaj sabse important kya hai?"_ → grounded answer milta (aaj ke real numbers pe based).
- **Kaam do:** _"Rohan ko hot leads follow-up karao"_ → AI khud sahi agent (Rohan) ko route karke ek **draft plan** banata hai.

`Run` dabao. Rate-limited hai (bar-bar spam mat karo, LLM heavy hai).

### B) Per-agent "🎯 Kaam do" — kisi specific agent ko
1. **Map** tab pe jao → kisi agent ke avatar pe click **(ya)** room pe click → room panel me agent ka naam (`→` wala) pe click.
2. Agent panel khulta hai → **🎯 Kaam do** box.
3. Goal likho (Hinglish chalega), scope chuno:
   - **solo** = sirf yeh agent kaam karega.
   - **team** = coordinator poori team ko lagayega.
4. Result ek **draft summary** aata hai (`run_id` ke saath).

### ⚠️ Samajhne ki cheez: "task dena" vs "asli workflow"
- **Task dena (upar wale 2 tareeke)** = ad-hoc, ek baar ka draft. Iska output **Approvals** me aata hai ya draft ke roop me — tu review karke aage badha.
- **Agents ka asli auto-workflow** = **Scheduler** (37 jobs, `Health` tab me `Aaj ka Schedule`). Yeh apne aap chalta rehta hai — Rohan har ghante outreach, Isha content, Kavya health-check, waghera. Isko tu `Scheduler` tab se per-job ON/PAUSE/run-now kar sakta.
- **"Run now" sirf kuch agents pe kaam karta** (arjun, meera, kavya, manager, isha, rohan) — baaki ke liye button jaan-boojh ke off hai (jhooth na bole isliye).

---

## 4. Har section ka kaam (reference)

**Boss brief** — aaj ka 1-glance: kitne leads, qualified, hot/warm, MRR. Risk/Opportunity/Next-move clickable.

**Priority action stack** — ranked "abhi kya karo". `👉 Abhi sabse pehle` = #1. Hot replies ho to woh #1 pe aa jaati (paisa pehle).

**Live pulse** — NEW LEADS / QUALIFIED / CALLS / MRR / agents-active / overdue / DLQ / replay counts.

**Map (Live Office)** — visual office. Room pe click = room ka workload + agents. Agent pe click = uska detail + Kaam-do. `Ctrl+scroll` zoom, drag pan. (Yeh mostly "feel" ke liye hai — kaam ke liye Pipeline/Approvals zyada useful.)

**Pipeline (12-stage)** — Lead Source → Cleaning → Scoring → Campaign → Outreach → Follow-up → Appointment → Deal → Onboarding → Delivery → Billing → Retention. Har stage pe click = us stage ke items (assign owner / next-action / move / resolve-stuck kar sakta). `◌ partial` badge = data approximate hai.
> **Hot vs Warm:** ab sach dikhता hai — **hot = score ≥ 70**, **warm = 40-69**. Pehle dono ko "hot" bola जाता tha.

**Approvals** — pending drafts + code-patches. Har item pe `✓` (approve) / `✕` (reject). **`🧠 Boss se review karao`** dabao to AI har item pe recommend karega (approve/reject + reason) — **final click phir bhi tera**. Code-patch approve = sirf review-marker, deploy manual hi hota.

**Health + Schedule** — 37 automation jobs ka din-plan, live status (`✓ ho gaya` / pending). Queue health (celery/dlq).

**Scheduler** — `Full control →`. Per-job ON/PAUSE + run-now. **`platform_dial` yahan PAUSED hai — usse chhedna mat** (user-mandate; galat "interested" mark kar raha tha + paisa jala raha tha).

**Reliability Console** — `Failed (retry-able)` + `Dead (exhausted)`. `🔁 Retry sweep` = failed tasks dobara chalao (dead ko koi nahi chhuta). Abhi **27 dead** pade hain (email_outreach timeout + worker OOM) — inhe engineer-level fix chahiye (neeche section 6).

**DLQ Repair Desk** — dead/failed queue kholने ka shortcut.

**Hot Queue (Reception)** — 🔥 garam replies (interested customers). `kholo →` → har reply pe draft-jawab + 1-click human-send. **Yeh direct paisa hai — roz clear karo.**

---

## 5. Common SOPs (kaam-ke steps)

**"Aaj kya karun?"** → War Room → `👉 Abhi sabse pehle` tile → click → wahin kaam.

**Hot reply ka jawab dena** → Hot Queue card `kholo →` → reply padho → draft edit karo → human-send. (Auto-send OFF hai — ban-safety; 1-click manual hi.)

**Approval clear karna** → Approvals → `🧠 Boss se review karao` (optional AI opinion) → khud `✓`/`✕`.

**Ek job pause/chalu karna** → Scheduler → job dhoondo → ON/PAUSE ya run-now.

**Failed jobs recover** → Reliability → `🔁 Retry sweep`.

**Kisi agent se ek kaam karana** → HQ Copilot box → _"[agent] ko [kaam] karao"_ → Run → draft aayega → Approvals me review.

---

## 6. Abhi 3 cheezein tooti hain — inpe dhyan de (audit se mila)

1. **Mid-funnel ruka hai** — aaj 170 leads aaye par **0 qualified**, aur Outreach/Follow-up/Appointment sab **0**. Funnel ka paisa-wala beech-hissa band hai. (Ab banner + brief yeh **honestly** bolते hain.)
2. **~2000 email → 0 reply (<2%)** — outreach quality/deliverability tooti. AI ne khud `outreach_quality` ko weakest stage flag kiya. Yeh #1 revenue-blocker hai.
3. **27 dead tasks** — `email_outreach TimeLimitExceeded(600)` + worker `SIGKILL` (OOM). Outreach engine crash/timeout ho raha — yehi upar wale 0-reply ki root wajah ho sakti. (Yeh **P4** fix — alag engine investigation, tu bole to karte hain.)

Aur alag: **18 hot replies (~₹35,982)** Hot Queue me unworked pade the — ab woh Priority stack me #1 pe aa jaate hain.

---

## 7. Yaad rakhne wali baatein

- Sab kuch **draft-safe** — AI khud paisa/message nahi bhejता bina tere.
- **Auto-refresh** ~15s — numbers apne aap update hote.
- **Simple view** toggle hai (upar) — kam-tech din ke liye simplified.
- **Briefing** button = Swara ki awaaz me aaj ka audio bulletin.
- Koi bhi panel kabhi poori page nahi todता (har section fail-safe degrade hota).
- **platform_dial ko ON mat karna** bina soch-samajh (paisa + compliance risk).
