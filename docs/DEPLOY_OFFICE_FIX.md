# 🚀 Deploy — Office HQ honesty + paisa-first + UX fix

> **Changed files:** `app/platform/office_hq.py` · `frontend/office_map.html` · `docs/OFFICE_GUIDE.md`
> **Risk:** low — additive logic only, koi naya route/import/migration nahi. Frontend HTML change container rebuild se serve hoga (koi .pyc/route stale-issue nahi).
> Yeh commands **Windows pe** (repo root) chalao — main sandbox se Windows git/ssh execute nahi kar sakta.

---

## Step 1 — VERIFY (green hona zaroori, warna aage mat badho)

```bat
.venv\Scripts\python.exe scripts\prod_check.py
.venv\Scripts\python.exe scripts\check_secrets.py
.venv\Scripts\python.exe -m pytest tests\test_office_hq.py tests\test_office_ask.py -q
```
Ya slash command: `/verify`

- `prod_check.py` = PASS chahiye.
- `check_secrets.py` = clean.
- office tests green (mainne logic already behaviourally test kiya — hot/warm split + mid-funnel risk sahi, existing fixtures bhi pass).

## Step 2 — DIFF dekho (Cursor/parallel edits safety)

```bat
"C:\PROGRA~1\Git\cmd\git.exe" diff -- app/platform/office_hq.py frontend/office_map.html
```
Sirf apne intended changes dikhne chahiye. (Shared files pe koi doosra edit na mix ho.)

## Step 3 — COMMIT (sirf yeh 3 files — `git add -A` mat karo)

```bat
"C:\PROGRA~1\Git\cmd\git.exe" add app/platform/office_hq.py frontend/office_map.html docs/OFFICE_GUIDE.md docs/DEPLOY_OFFICE_FIX.md
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "office HQ: honest brief/banner (hot vs warm, mid-funnel + dead-task risk) + hot-reply money-first #1 action + #1-tile emphasis"
"C:\PROGRA~1\Git\cmd\git.exe" push origin main
```

## Step 4 — DEPLOY (SSH VPS, surgical — app service only)

```bat
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "cd /opt/leadgen && git pull && docker compose -f docker-compose.vps.yml build app && docker compose -f docker-compose.vps.yml up -d --no-deps app"
```
> VPS tree chronically dirty hai — `reset --hard`/blind rebuild KABHI nahi. Yeh sirf `git pull` + `app` rebuild karta.

## Step 5 — VERIFY LIVE (deploy ke ~16s baad)

```bat
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "sleep 16 && curl -s http://localhost:8000/health"
```
- `environment:production` dikhna chahiye.
- Phir browser me `https://leadsgenai.in/app/office` kholo → **hard reload `Ctrl+Shift+R`** (nayा JS/HTML load ho).
- Check: top banner ab `⚠️ 27 dead task(s) · mid-funnel ruka` (healthy nahi), Boss brief `53 warm` (hot nahi), Priority stack me `🔥 hot reply — abhi jawab do` #1 pe.

---

## P4 — Outreach engine fix (ALAG deploy, worker rebuild)

> **Changed files:** `app/platform/auto_outreach.py` · `app/integrations/email_sender.py` · `app/platform/prospector.py`
> **Kya theek hua:**
> - **(A) TimeLimitExceeded fix:** selection me per-candidate blocking DNS MX lookup band → asli MX ab sirf final ≤25 batch pe (`OUTREACH_SELECT_SKIP_MX=1` default).
> - **(C) SMTP timeout:** send ab `timeout=30s` bounded (`EMAIL_SEND_TIMEOUT_S`) — stalled connection ab poora 600s budget nahi khaati.
> - **(B) OOM/SIGKILL fix:** `emailed_at` markers ab bulk likhte hain (har 10 + end me = 3 file-writes vs pehle 25) via naya `prospector.set_prospect_fields_bulk` (`OUTREACH_BULK_MARK=1` default). O(N²) → O(N).
> **Yeh revenue engine hai — Office HQ deploy verify hone ke BAAD alag se karo.**

```bat
:: verify (worker code import + targeted)
.venv\Scripts\python.exe scripts\prod_check.py
.venv\Scripts\python.exe -m pytest tests -k "outreach or email" -q

:: diff + commit (sirf yeh 2 files)
"C:\PROGRA~1\Git\cmd\git.exe" diff -- app/platform/auto_outreach.py app/integrations/email_sender.py app/platform/prospector.py
"C:\PROGRA~1\Git\cmd\git.exe" add app/platform/auto_outreach.py app/integrations/email_sender.py app/platform/prospector.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "outreach: MX defer to send-batch (TimeLimitExceeded) + SMTP 30s timeout + bulk emailed_at mark (OOM fix)"
"C:\PROGRA~1\Git\cmd\git.exe" push origin main
```

Deploy — **worker services rebuild** (app nahi, worker chahiye; service naam bilkul sahi — `worker-heavy` hyphen ke saath, warna poora `up` abort):
```bat
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "cd /opt/leadgen && git pull && docker compose -f docker-compose.vps.yml build worker worker-heavy scheduler && docker compose -f docker-compose.vps.yml up -d --no-deps worker worker-heavy scheduler"
```

Verify (agla hourly outreach run 9am–7pm window me):
- Office HQ → **Reliability Console**: `Dead (exhausted)` count ab **badhna band** hona chahiye (purane 27 historical hain — chaho to `🔁`/purge se saaf karo, warna chhod do).
- Naya `email_outreach` run 600s se pehle clean khatam ho (ab TimeLimitExceeded nahi).

**Rollback flags (code revert bina):** `OUTREACH_SELECT_SKIP_MX=0` (purana per-candidate MX) · `EMAIL_SEND_TIMEOUT_S` badalna. VPS `.env` me set + worker recreate.

### Fix D — TERA config action (code nahi, VPS `.env` me):
Reply-triage OFF hai isliye inbound replies prospects se link nahi hote → funnel me "0 replies" dikhता hai bhale koi aaye. Chalu karne ke liye VPS `.env` me:
```
REPLY_AGENT=1
```
- IMAP creds already hain (`SMTP_USER`/`SMTP_PASSWORD` Hostinger admin@leadsgenai.in reuse hote). Zaroorat pade to `IMAP_HOST=imap.hostinger.com` bhi add karo.
- Set karke worker recreate karo (P4 deploy ke saath ya baad). Phir replies auto-link honge.

### P4 ka baaki (abhi NAHI — bade kaam, alag session):
- **Deliverability (asli 0-reply root):** single mailbox se cold Hinglish mail scraped SMB pe = spam. Warmup + SPF/DKIM/DMARC + multiple mailbox rotation = alag project.
- **Per-task soft time-limit** (~300s dedicated) outreach task ke liye — Fix A ke baad optional defense.

---

## Rollback (agar kuch galat)

```bat
"C:\PROGRA~1\Git\usr\bin\ssh.exe" -i C:\Users\Ratanshila\.ssh\id_rsa root@72.61.245.204 "cd /opt/leadgen && git log --oneline -3"
```
Purane commit pe `git checkout <sha> -- app/platform/office_hq.py frontend/office_map.html` phir rebuild. (Ya poora `git revert <sha>` + push + redeploy.)

---

### Deploy ke baad (mujhe bolna)
Main `memory/decisions.md` me ADR + `CLAUDE.md ## Current State` update kar dunga (session-complete rule). Abhi tak likha nahi — kyunki live tabhi hoga jab yeh deploy green ho.
