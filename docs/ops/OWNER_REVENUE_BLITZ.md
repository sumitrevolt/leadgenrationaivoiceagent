# Owner Revenue Blitz — Daily 15-Minute Runbook

**Goal:** Convert Hot Queue leads → 2nd paid customer this week

**Time Required:** 15-30 minutes/day (Hot Queue) + 5 minutes per UPI approval

---

## Part 1: Hot Queue Daily Blitz

### When
**Daily:** Best times:
- Morning: 10:00-11:00 AM IST (fresh overnight inquiries)
- Evening: 5:00-6:00 PM IST (after-work inquiries)

**Duration:** 15-20 minutes (10-15 leads)

### Where
`https://leadsgenai.in/app/inbox`

**Login:** `/app/admin-login` (admin credentials)

### What You See
**Unified Inbox** with tabs:
- 🔥 **Hot Queue** ← START HERE (interested/question intent)
- 📬 Inbox (all inquiries)
- ✅ Done (closed/converted)

### Steps

#### 1. Open Hot Queue Tab
Click "🔥 Hot Queue" tab in `/app/inbox`

**Each card shows:**
- Business name
- Niche (e.g. "beauty-salon", "gym")
- City
- Phone number
- Inquiry text
- Intent score
- Time since inquiry (SLA: 5 min target)

#### 2. Review Top Card
Read inquiry text. Look for:
- **Interested signals:** "kitne ka hai", "kaise shuru kare", "demo dikha do"
- **Questions:** "ye kya hai", "kaise kaam karta hai"
- **Objections:** "bahut mehenga", "pehle free try karne do"

#### 3. Take Action

**Option A: WhatsApp (Recommended for most leads)**
1. Click "📋 Copy" button → draft message copied to clipboard
2. Click "💬 WhatsApp" button → opens `wa.me/91XXXXXXXXXX` in new tab
3. Paste draft message (already copied)
4. **Edit message** to personalize:
   - Add name if known
   - Reference their inquiry ("aapne salon ke liye AI marketing ke baare me poocha tha")
   - Offer specific next step ("10 min ka demo call kar lete hain?")
5. Send WhatsApp message
6. Return to inbox tab → click "✅ Done" on the card

**Draft message template (auto-generated):**
```
Namaste [Business Name]!

Aapki inquiry mili - [Niche] ke liye AI Marketing Automation.

Humara platform automatically:
- Google/FB posts banata hai
- Leads collect karta hai
- Follow-up calls/WhatsApp karta hai

15 min ka demo dikha du? Free audit bhi mil sakta hai.

Demo booking: https://leadsgenai.in/demo
Pricing: https://leadsgenai.in/pricing

Questions? Reply kare ya call kare.

Sumit
LeadsGen AI
```

**Option B: Phone Call (For hot/urgent leads)**
1. Click "📞 Call" button → phone number shown
2. Call the number directly (your phone or Swara dialer)
3. **Script:**
   - "Hello, main Sumit bol raha hu LeadsGen AI se"
   - "Aapne hamare website pe inquiry ki thi [niche] ke liye AI marketing ke baare me"
   - "Kya aapko 10 minute ka demo convenient hoga? Dikhata hu kaise automatically posts/leads handle hote hain"
4. If interested:
   - Schedule demo call (Zoom/Google Meet link)
   - OR share `/demo` link for self-service preview
   - Note their preferred time
5. Return to inbox → click "✅ Done"

**Option C: Council Decide (If unsure)**
1. Click "🤔 Council Decide" button
2. System runs multi-LLM council (3 AI agents vote)
3. Returns recommended action: Call / WhatsApp / Park
4. Follow the recommendation

**Option D: Park (If not ready)**
1. Click "⏳ Park" if:
   - Lead needs more time
   - Wrong number / no answer
   - Need to prepare custom demo
2. Card moves out of Hot Queue
3. Can review later in "📬 Inbox" tab

#### 4. Repeat for Next Card
Move to next card in Hot Queue. Target: 10-15 cards per session.

### Tips for High Conversion

**Do:**
- Respond FAST (within 5 min if possible) → 10x higher close rate
- Personalize every message (name, niche, specific pain point)
- Offer demo call (not just pricing link)
- Ask qualifying questions ("kitne leads chahiye per month?")
- Reference their website if they shared it

**Don't:**
- Copy-paste generic message (feels like spam)
- Lead with pricing (first show value)
- Push for immediate payment (demo → trust → sale)
- Ignore low-score cards (sometimes system misses intent)

### Success Metrics

**Target per session:**
- 10-15 cards reviewed
- 3-5 WhatsApp messages sent
- 1-2 phone calls made
- 1-2 demos scheduled

**Target per week:**
- 50-75 total touches
- 5-10 demos given
- 1-2 conversions (at 10-20% close rate)

---

## Part 2: UPI Approval (When Payment Comes)

### When
**Trigger:** Lead says "maine payment kar diya" (WhatsApp/call)

**OR:** Check pending submissions daily at `/app/admin` → "Pending UPI Submissions" section

### Where
`https://leadsgenai.in/app/admin` → scroll to "💰 Pending UPI Submissions"

### What You See
**Table of pending UPI submissions:**
- Customer name (or "Guest")
- Amount (₹1,999 or ₹5,999)
- UPI ref (e.g. "403012345678")
- Submitted at (timestamp)
- Status: Pending / Approved / Rejected
- Actions: Approve / Reject / Bind (for guests)

### Steps for Logged-In Customer

#### 1. Check Bank
Open your UPI app (Google Pay / PhonePe / Paytm) or bank statement.

**Look for:**
- Amount matches (₹1,999 or ₹5,999)
- Ref matches (last 6-8 digits usually enough)
- Time matches (within 24 hours of submission timestamp)

#### 2. Verify in Table
Find the matching row in "Pending UPI Submissions" table.

**Check:**
- Customer name matches (from WhatsApp/call)
- Amount is correct
- Ref matches bank transaction

#### 3. Approve
Click "✅ Approve" button.

**System will:**
- Activate subscription immediately
- Grant portal access (`/app/automation`)
- Generate invoice (INV/2026-27/000X)
- Send welcome email (if configured)

#### 4. Notify Customer
**WhatsApp message:**
```
Payment verified! 🎉

Aapka subscription activate ho gaya hai:
- Plan: Marketing Automation Main (₹1,999/mo)
- Portal login: https://leadsgenai.in/login
- Invoice: INV/2026-27/000X (email me bhi milega)

Portal me jaake apna business details fill kare, phir automation shuru ho jayega.

Koi help chahiye to reply kare!

Sumit
LeadsGen AI
```

### Steps for Guest Payment (No Login)

#### 1. Check Bank (Same as above)
Verify amount + ref in your UPI app.

#### 2. Find Guest Submission
Look for row with:
- Customer name: "Guest" or email only
- Amount matches
- Status: "Pending" or "⚠️ Approved but Unbound"

**Warning sign means:** Payment verified BUT no client account linked yet.

#### 3. Bind Client ID

**Option A: Create New Client (First-time customer)**
1. Click "🔗 Bind Client" button
2. Modal opens: "Bind Guest Submission to Client"
3. Click "➕ Create New Client" tab
4. Fill form:
   - **Business Name:** (from inquiry/WhatsApp)
   - **Email:** (from UPI submission or WhatsApp)
   - **Phone:** (from inquiry)
   - **Niche:** (e.g. "beauty-salon", "gym")
   - **City:** (from inquiry)
5. Click "Create & Bind"
6. System creates client account + binds submission

**Option B: Link to Existing Client (If they already have account)**
1. Click "🔗 Bind Client" button
2. Modal opens: "Bind Guest Submission to Client"
3. Click "🔍 Search Existing" tab
4. Search by name/email/phone
5. Select matching client from results
6. Click "Bind to This Client"

#### 4. Re-Approve
After binding, the submission shows "⚠️ Approved but Unbound" → changes to "Pending".

Click "✅ Approve" button again.

**System will:**
- Activate subscription for the bound client
- Grant portal access
- Generate invoice
- Send welcome email

#### 5. Notify Customer
Send WhatsApp message with login link (same as logged-in flow above).

**Also provide password** (if you created account):
```
Aapka account ready hai! 🎉

Login: https://leadsgenai.in/login
Email: customer@example.com
Password: [temporary password]

Pehli login pe password change kar lena.

Portal me business details fill kare, phir automation start hoga.
```

### If Payment NOT Found in Bank

**Do NOT approve yet.**

#### Check:
1. Amount mismatch? (wrong plan selected)
2. Ref typo? (customer might have entered wrong ref)
3. Delayed transfer? (sometimes UPI takes 5-10 min)
4. Wrong UPI ID? (customer paid to wrong VPA)

#### Contact customer:
```
Hi [Name],

Maine payment check kiya bank me - abhi tak nahi dikha.

Kya aap screenshot bhej sakte ho:
1. Payment success message (Google Pay / PhonePe)
2. UPI transaction ID

Ya phir 10 min baad retry kar sakte ho (kabhi delay hota hai).

Sumit
```

**If still not found after 30 min:**
1. Click "❌ Reject" button
2. Reason: "Payment not found in bank"
3. Contact customer to retry OR investigate with bank

---

## Part 3: Daily Checklist (15-30 Min Total)

### Morning (10-15 min)
- [ ] Check overnight Hot Queue leads (5-10 cards)
- [ ] Send 3-5 WhatsApp messages (personalized)
- [ ] Check pending UPI submissions (if any)

### Evening (10-15 min)
- [ ] Check afternoon Hot Queue leads (5-10 cards)
- [ ] Follow up on morning messages (if no reply)
- [ ] Approve any new UPI submissions

### Weekly Review (30 min, Friday)
- [ ] Count total touches (target: 50-75)
- [ ] Count demos given (target: 5-10)
- [ ] Count conversions (target: 1-2)
- [ ] Identify bottleneck (if < 1 conversion):
  - Not enough Hot Queue leads? → Increase SEO/ads
  - Low WhatsApp reply rate? → Improve message copy
  - Demos not converting? → Improve demo script / pricing objection handling

---

## Part 4: Troubleshooting

### Hot Queue is Empty
**Reasons:**
- Low website traffic (check Google Analytics)
- Inquiry form broken (test `/audit`, `/site-audit`, `/demo`)
- Bridge disabled (check `INQUIRY_BRIDGE_ENABLED` flag)

**Fix:**
1. Test inquiry form yourself (submit test inquiry)
2. Check `/app/inbox` → "📬 Inbox" tab (all inquiries, not just hot)
3. If still empty → increase lead magnet traffic (SEO/ads)

### WhatsApp Link Not Working
**Reasons:**
- Phone number format wrong (should be `91XXXXXXXXXX`, no spaces/dashes)
- `wa.me` blocked by firewall/proxy

**Fix:**
1. Copy phone number manually
2. Open WhatsApp Web: `https://web.whatsapp.com`
3. Start new chat → paste number
4. Send message

### UPI Approval Not Activating Subscription
**Reasons:**
- Guest submission not bound (see "Approved but Unbound" warning)
- Client account disabled/deleted
- Plan ID mismatch (wrong package selected)

**Fix:**
1. Check admin dashboard → client details → subscription status
2. If status = "pending" → manually activate via "Activate Subscription" button
3. If still broken → check logs at `/app/admin` → "System Logs" tab

### Customer Says "Portal Login Nahi Ho Raha"
**Reasons:**
- Wrong email (case-sensitive)
- Password forgotten (never set)
- Account not created (guest payment but bind failed)

**Fix:**
1. Verify email in admin dashboard → search client by phone
2. If account exists → send password reset link: `/forgot-password`
3. If no account → create manually:
   - `/app/admin` → "Clients" → "➕ Add Client"
   - Fill details → "Create"
   - Approve pending UPI → bind to new client

---

## Part 5: Conversion Scripts

### Discovery Call Script (5-10 min)

**Goal:** Qualify lead + schedule demo

**Opening:**
> "Namaste [Name], main Sumit bol raha hu LeadsGen AI se. Aapne inquiry ki thi [niche] ke liye AI marketing automation ke baare me. Kya 2 minute bat kar sakte hain?"

**Qualify:**
> "Aap abhi marketing kaise karte ho? Manual posts / ads / WhatsApp broadcast?"

**Pain:**
> "Sabse bada problem kya hai? Time lagta hai? Consistent nahi ho pata? Leads follow-up nahi hota?"

**Solution Teaser:**
> "Humara platform automatically sab handle karta hai - daily posts, lead capture, follow-up calls. Aapko sirf approve karna hai, baaki AI karta hai."

**Demo Offer:**
> "10 minute me live dikha du? Aapke business ka example use karke. Kab convenient hai - abhi ya shaam ko?"

**Objection Handling:**
> - "Pehle free try karenge" → "Demo hi free hai, paid me jaane se pehle pura dekh lo"
> - "Bahut mehenga hoga" → "₹1,999/mo se shuru hota hai, ek employee se bhi sasta"
> - "Hum already kisi agency ko dete hain" → "Agency ko supervision dena padta hai na? Ye fully automated hai"

**Close:**
> "Theek hai, main aapko WhatsApp pe demo link bhej raha hu. 10 min ka time nikal lena, value samajh ayegi."

### Demo Call Script (10-15 min)

**Goal:** Show value → handle objections → close sale

**Opening:**
> "Thanks for the time! Screen share kar raha hu, dikha raha hu kaise kaam karta hai."

**Show (Live Portal):**
1. Login to `/app/automation` (demo account)
2. Show "Mission Control" dashboard:
   - "Ye daily automated posts hai - aapko sirf approve karna hai"
   - "Ye lead capture form - automatically website pe lagta hai"
   - "Ye follow-up scheduler - missed leads ko auto WhatsApp/call"
3. Show one post example:
   - "Ye salon ke liye AI-generated post hai - image bhi automatic, caption bhi"
   - "Aap edit kar sakte ho, ya direct approve"
4. Show lead pipeline:
   - "Jab koi inquiry karta hai, automatically Hot Queue me aata hai"
   - "1-click WhatsApp draft ya call button - 5 min me respond kar sakte ho"

**Value Prop:**
> "Basically, aapko 1 day me 30 min dena hai - morning me approvals, evening me leads respond. Baaki sab AI handle karta hai."

**Pricing:**
> "₹1,999/mo main plan hai - unlimited posts, lead capture, follow-ups sab included."
> "₹5,999 me advanced plan hai - usmein 500 minute voice callback bhi hai (AI receptionist)."

**Objection Handling:**
> - "Humari industry me kaise kaam karega?" → "Already [similar niche] me kaafi clients hain, template ready hai"
> - "Setup kaun karega?" → "Hum kar dete hain - 1 din me live ho jayega, aapko kuch nahi karna"
> - "Results kitne din me milenge?" → "Posts 1st day se, leads 3-5 din me aane lagte hain, conversions 2 weeks me"

**Close:**
> "Interested ho to abhi subscription activate kar du? Payment UPI se ho jayega, 2 min me live."

**Send:**
- Pricing link: `https://leadsgenai.in/pricing`
- UPI details (in WhatsApp)

### Post-Demo Follow-Up (If Not Closed)

**Next Day:**
> "Hi [Name], kal demo kaisa laga? Koi questions the jo main answer kar sakta hu?"

**Day 3:**
> "Just checking - kya decide kiya? Agar setup me help chahiye to main personally kar dunga."

**Day 7:**
> "Last reminder - agar abhi start karte ho to 1st month free me 2 weeks extra consultation included hai. Let me know!"

---

## Part 6: Success Metrics

### Daily Targets
- **Hot Queue reviews:** 10-15 cards/day
- **WhatsApp sent:** 3-5 messages/day
- **Calls made:** 1-2 calls/day
- **Demos scheduled:** 0-1 demos/day (not daily, but ~5/week)

### Weekly Targets
- **Total touches:** 50-75 (WhatsApp + calls)
- **Demos given:** 5-10
- **Conversions:** 1-2 (at 10-20% close rate)

### Monthly Targets (After First Month)
- **New MRR:** ₹10,000-20,000 (5-10 customers at ₹1,999-5,999 each)
- **Total customers:** 5-10 active
- **Churn:** <20% (keep existing customers happy)

### Red Flags (Need Attention)
- **<50 touches/week** → Not enough outreach (increase time)
- **<5 demos/week** → Messaging not compelling (improve copy)
- **<10% close rate** → Demo/pricing issue (improve script/objection handling)
- **>20% churn** → Product/support issue (talk to churned customers)

---

## Summary: Daily 15-Min Blitz

1. **Login:** `https://leadsgenai.in/app/inbox` (admin)
2. **Hot Queue:** Review 10-15 cards
3. **Action:** Send 3-5 WhatsApp (personalized) OR make 1-2 calls
4. **UPI:** Check pending submissions, approve if payment verified
5. **Track:** Count touches, demos, conversions (weekly review)

**Result:** 1-2 new customers per week → ₹2,000-10,000 MRR/month growth

---

**File:** `docs/ops/OWNER_REVENUE_BLITZ.md`  
**Created:** 2026-08-12  
**Purpose:** Daily runbook for owner (coordinator sunny) — 2nd paid customer track

---

**Canary:** 🐦 pelican
