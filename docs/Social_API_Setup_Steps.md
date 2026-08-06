# Social Auto-Posting — API Keys Setup Guide (2026-07-04)

> Yeh guide un 3 platforms ke liye hai jinke bina Postiz/native social_engine me koi
> channel connect nahi ho sakta (confirmed live: sab `${VAR:-}` empty hain VPS pe).
> Har platform ke end me jo key/secret milegi, **woh mujhe bhej do (chat me paste karo)**
> — main VPS `deploy/postiz/.env` + `.env` me wire karke Postiz restart kar dunga,
> connect verify karunga, sab khud.

**Brand info (sab jagah yehi use karo):**
- Naam: **LeadsGenAI**
- Website: `https://leadsgenai.in`
- Category: Marketing agency / Software
- Location: Mumbai, India
- Email: `admin@leadsgenai.in`
- Privacy policy URL (agar maanga jaye): `https://leadsgenai.in/privacy`
- Postiz redirect base: `https://postiz.leadsgenai.in`

---

## 1. Facebook Developer App (unlocks Facebook Page + Instagram dono)

**Time: ~5 min. Review nahi chahiye (dev-mode apni hi Pages pe kaam karta hai).**

1. Apne normal Facebook login se jao: `https://developers.facebook.com/apps`
2. **"Create App"** click karo
3. Use-case me **"Other"** ya **"Business"** select karo → Next
4. App type: **"Business"**
5. App details:
   - App name: `LeadsGenAI`
   - App contact email: `admin@leadsgenai.in`
   - Business Portfolio: agar pucha jaye to naya bana lo ya skip karo
6. App create hote hi **Dashboard** khulega
7. Left sidebar → **"Add Product"** → dono add karo:
   - **Facebook Login for Business**
   - **Instagram Graph API** (yeh Instagram unlock karta hai)
8. Left sidebar → **Settings → Basic**:
   - Yahan **App ID** aur **App Secret** dikhega ("Show" click karke reveal karo)
   - **App Domains**: `postiz.leadsgenai.in`
   - **Privacy Policy URL**: `https://leadsgenai.in/privacy`
   - **Category**: Business
   - Save Changes
9. Left sidebar → **Facebook Login for Business → Settings**:
   - **Valid OAuth Redirect URIs** me daalo: `https://postiz.leadsgenai.in/integrations/social/facebook`
   - Save
10. Top-right toggle **"App Mode"** ko Development me hi rehne do (Live/review baad me, apni hi Page ke liye zaroori nahi)

**Mujhe bhejo:** App ID + App Secret

---

## 2. LinkedIn (Company Page + Developer App)

**Time: ~10 min. Pehle Company Page banana zaroori hai (App usi se link hota hai).**

### 2a. Company Page (agar abhi tak nahi bana — check kiya, "LeadsGenAI" naam se abhi exist nahi karta)
1. Jao: `https://www.linkedin.com/company/setup/new/`
2. Page type: **"Small business"**
3. Details:
   - Name: `LeadsGenAI`
   - LinkedIn public URL: `linkedin.com/company/leadsgenai` (ya jo bhi available ho)
   - Website: `https://leadsgenai.in`
   - Industry: **Marketing Services**
   - Company size: **2-10 employees**
   - Company type: **Privately Held**
   - Logo: `docs/brand/logo.jpg` (already bana hua hai) upload kar do
4. Tagline: `AI marketing team for local Indian businesses — ₹1,999/mo`
5. "Create page" click karo

### 2b. Developer App
1. Jao: `https://www.linkedin.com/developers/apps` → **"Create app"**
2. App name: `LeadsGenAI`
3. LinkedIn Page: yahan wahi Page select karo jo abhi banayi (type karke dropdown se pick karo)
4. App logo upload karo, Legal agreement checkbox tick karo → **Create app**
5. App ke andar **"Products"** tab → **"Share on LinkedIn"** product request karo (self-serve, instant approve hota hai)
6. **"Auth"** tab:
   - Yahan **Client ID** + **Client Secret** milega
   - **Authorized redirect URLs** me add karo: `https://postiz.leadsgenai.in/integrations/social/linkedin`

**Mujhe bhejo:** Client ID + Client Secret

---

## 3. X (Twitter) Developer App

**Time: ~10 min. Free tier kaafi hai (~500 posts/month).**

1. Apne X account se login karke jao: `https://developer.x.com/en/portal/dashboard`
2. Agar pehli baar hai to **"Sign up for Free Account"** — kuch use-case questions honge (bas "building automation for my own business" type answer do)
3. **"Create App"** (ya "Add App" agar project pehle se hai):
   - App name: `LeadsGenAI` (kisi bhi unique naam se — X pe naam globally unique chahiye, agar clash ho to `LeadsGenAIBot` try karo)
4. App ban jaye to **"Keys and tokens"** tab:
   - **API Key** + **API Key Secret** yahi dikhega
5. **App settings → User authentication settings → Set up**:
   - App permissions: **Read and Write**
   - Type of App: **Web App**
   - Callback URI: `https://postiz.leadsgenai.in/integrations/social/x`
   - Website URL: `https://leadsgenai.in`
   - Save

**Mujhe bhejo:** API Key + API Key Secret

---

## 4. Google Business Profile — API (LOWER PRIORITY, alag process)

GBP profile "leadsgenai" already ban chuka hai (Google review me pending tha). Par
**auto-posting ke liye GBP API access** alag cheez hai — Google isko manually approve
karta hai (~60 din, business-verification ke saath), sirf console-click se nahi milta.
**Filhaal skip karo** — jab GBP profile verify ho jaye tab is step ko revisit karenge.

---

## Jab keys aa jayein

Bas mujhe bata do "ho gaya" + keys paste kar do (ya sirf bata do "Facebook ho gaya" ek-ek
karke jaise milein — sab ek saath ka wait nahi karna). Main turant:
1. VPS `deploy/postiz/.env` me `FACEBOOK_APP_ID`/`FACEBOOK_APP_SECRET` (ya jo bhi platform) daalunga
2. `docker compose -f deploy/compose/docker-compose.postiz.yml up -d` (env-only change, safe restart)
3. Postiz "Add Channel" se actual connect karunga (tumhara login chahiye hoga usi waqt bas ek click ke liye)
4. Verify karke confirm karunga ki channel LIVE hai
