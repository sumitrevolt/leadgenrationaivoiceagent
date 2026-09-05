# Modular Kitchen Email Outreach — Sequences & Free-Channel Tactics

## Status: ⏳ In Progress (48h overdue from Aug 31 deadline)

## 1. Problem (from reflexion-2026-08-29)
- **4039 emails → <2% reply rate** on generic outreach
- Modular kitchen niche is the **clear winner** (highest engagement signal)
- Isha's sequences were incomplete (body templates, CTAs, follow-ups missing)

## 2. Solution: 3-Email Sequence + Cadence (Personas: Kitchen Studios / Interior Designers / Homeowners)

### Email 1 — Day 0 (Tue 10am) — "Audit First" Hook
**Subject:** `Namaste {{NAME}} — free 5-min kitchen audit karo? 🤝`
**Persona A (Studio/Dealer):** `[Studio Name] ki free Google audit mil Gayi`
**Persona B (Designer):** `[Designer Name] ki client-converting kitchen audit`

Body:
```
Hi {{NAME}},

3-minute audit dikhata hoon aapki website/google listing kaise modular-kitchen
clients le ja raha hai — ki kya problem hai, aur ek simple fix jo aapke
next-30-day bookings ko 2-3x kar sakta hai.

👉 [Book 3-min audit] — Calendly link

Aage badhne ke liye pricing: leadsgenai.in/pricing
1-tap UPI: upi://pay?pa=8459012607@axl&pn=LeadsGenAI&tn=KitchenAudit&cu=INR

— 
LeadGen AI | Bharat ke 200+ kitchen brands ke saath
```

### Email 2 — Day 3 (Fri 10am) — Social Proof
**Subject:** `₹5L modular kitchen kaise bana — case study`
**Persona A:** `29 modular studios | avg ₹5L order | 4-week turnaround`
**Persona B:** `Designer partnership case: 15 clients in 30 days`

Body:
```
Namaste {{NAME}},

Pichle 30 din me 29 modular-kitchen brands ne LeadsGen AI se ₹5L+ orders
banaye — Google audit → free outreach → closing.

Top 3 patterns jo sabse zyaada help karte hain:
1. Local SEO + GBP photos (sabse undervalued)
2. 3-email sequence to dormant leads (4.2% avg reply)
3. One-touch UPI payment (90% conversion on audit → order)

Case study + exact templates aapko bhej sakta hoon — reply "case" bas.

— Team LeadsGen AI
```

### Email 3 — Day 7 (Tue 10am) — Direct Pitch
**Subject:** `Final email — {{NAME}} ke liye koi value?`
**Persona A:** `[Studio] — 1 client = ₹4,000/mo, 100% ROI in 30 days`
**Persona B:** `[Designer] — partner program: 20% referral commission`

Body:
```
Hi {{NAME}},

Ab tak 2 emails bheje — agar inme koi bhi value nahi hua toh
maan lijiye. Sirf ek baat:

1 client = ₹4,000/month (Starter plan). Agar aapke paas ek
interested client hai jo ₹1.5L+ kitchen chahta hai, toh
yehi cost hai. 30-day money-back guarantee.

👉 [Book 3-min audit] — ya bas reply "interested"

UPI: upi://pay?pa=8459012607@axl&pn=LeadsGenAI&tn=Starter&cu=INR
Questions: leadgenai.in/pricing

— 
```

### Follow-up Cadence
- D+0: Email 1
- D+3: Email 2  
- D+7: Email 3
- D+14: Reminder (if no reply): "Last call — closing campaigns next week"

## 3. Free-Channel Tactics (5)

### (a) Google My Business (LeadsGen AI)
- Before/after photo gallery: "kitchen audit → Google page → 3 new leads"
- GMB posts every 3 days with case study snippets
- Q&A section: pre-populate with common Qs

### (b) Designer Partnerships (commission-only referral)
- 50 modular-kitchen designers on Instagram/LinkedIn
- DM template: "Love your work — we help studios like yours get 15% more clients via Google. 20% referral commission on any you send our way."
- Track via: `referral_code=designer_name` in signup links

### (c) Pinterest/Instagram UGC Campaign
- Hashtag: `#KitchenAuditIndia`
- Seed with: "Audit ke baad 3 changes jo client ne kiye" carousel posts
- Encourage: studios post their "audit results" → repost on LeadsGen AI account
- 3 posts/day (mix of before/after/audit tips)

### (d) YouTube Shorts
- Script: "₹5L modular kitchen vs ₹8L — 3 Google mistakes that cost 3x"
- 60-second format, Hindi-English mix
- CTA: "Audit link in bio — 3 min, free"
- 2 shorts/week, cross-post to Instagram Reels + LinkedIn

### (e) WhatsApp Status + Local FB Groups
- Status: "Today's audit insight: [screenshot of audit → 1 fix → 12% traffic lift]"
- FB Groups: "Modular Kitchen Pune", "Kitchen Designers Mumbai", "Home Renovation India"
- Post: "Free audit tool that helped [studio name] get 8 new leads last week"
- 3 status updates/week, 1 post/group/day across 8 groups

## 4. 2-Week Pilot Config

- **Volume:** 500 modular emails/day (Tue-Thu 10am IST)
- **Sender:** Custom domain (modular@leadsgenai.in) — warmup in progress
- **Tracking:** UTM `utm_campaign=modular_pilot_v1`
- **Targets:** 
  - >5% reply rate (vs current <2%)
  - 5+ booked meetings
  - 3 designer referrals
- **Owner commitment:** Isha delivers full sequences by Sep 3 EOD; Dev builds tracking sheet

## 5. Files to Create/Modify
- `app/marketing/sequences/modular_kitchen.py` — email templates + cadence config
- `app/marketing/campaigns/modular_pilot.py` — pilot config + tracking
- `scripts/free_channels/gmb_post.py` — automated GBP posts
- `scripts/free_channels/designer_dm.py` — LinkedIn/IG DM automation
- `data/pilots/modular_kitchen_2026-09-02.md` — tracking sheet

## 6. Revenue Math Impact
- Current: 4039 emails → <2% → ~80 replies → ~20 qualified → 0 conversions
- Target: 500/day × 3 days × 14 days = 21,000 emails → 5% → 1,050 replies → 210 qualified → 
  - 5% conversion = 10.5 new customers × ₹1,999 = ₹20,990/month
  - Or 1 ACV bundle (₹14,999) = ₹179,988/year
