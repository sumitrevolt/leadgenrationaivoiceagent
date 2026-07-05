# 🤝 PROJECT HANDOFF — LeadGen AI (leadsgenai.in)

> Naya AI session ya naya developer? **YE doc pehle padho** — 15 minute me poora project
> operate karne layak ho jaoge. Ye doc POINT karta hai, duplicate nahi karta
> (`.claude/skills/SKILLS_PARITY.md` rule) — detail hamesha linked skill/doc me hai.
> Last full-verify: **2026-07-05** (live deploy + container list + route count is din verify hue).

## 1. Ye project kya hai

- **DO alag products** (ADR-009 — `docs/ADR_2026_06_11_Product_Split_Pricing.md`):
  1. **AI Automated Marketing** = MAIN product (chhote local businesses) — Main ₹1,999/mo · Advanced ₹5,999/mo (voice = sirf ek FEATURE isme).
  2. **AI Voice Calling Agent** = ALAG standalone product — flat monthly per niche-band: A ₹4,999 / B ₹9,999 / C ₹19,999.
  - ⚠️ "Marketing + voice bundle" USP framing GALAT hai — do alag products bolo.
- **LIVE**: https://leadsgenai.in (Hostinger VPS, Mumbai). Repo: `github.com/sumitrevolt/leadgenrationaivoiceagent` (branch `main`).
- **Pricing source-of-truth = code**: `app/marketing/packages.py` + `app/marketing/voice_packages.py` — numbers docs me KABHI copy mat karo; change = `test_billing_truth_2026.py` saath green.
- Stack: FastAPI (~1030 routes) + Celery/Redis + Postgres(PgBouncer) + Qdrant, Docker Compose (`docker-compose.vps.yml`). Sab FREE LLM/STT/TTS stack (user decision — koi paid AI nahi).

## 2. Teen-directory layout (Windows PC — confuse mat hona)

| Directory | Kya hai | Edit karna? |
|---|---|---|
| `Documents\leadgenrationaiagent` | **ASLI code repo** (source of truth) | Haan — saara project-kaam yahi |
| `Documents\leadsgenai-brain` | Obsidian notes vault, **NIGHTLY BOT-SYNC** (doosri machine se push) | Dhyan se — manual additions agla sync DELETE kar sakta hai; pehle `git fetch` |
| `source\repos` | Generic vendored dev-skills master (`npx skills`, project-agnostic) | Project-kaam yahan NAHI; iska `skills-lock.json` project pe mat thopo |

## 3. Live infra map

- **VPS**: `72.61.245.204` (hostname `srv1736379`, Ubuntu 24.04, Hostinger Docker template). App dir: `/opt/leadgen`.
- **Containers** (2026-07-05 live-verified): `leadgen_app` :8000 · `leadgen_worker` · `leadgen_worker_heavy` · `leadgen_scheduler` (Celery beat) · `leadgen_redis` · `redis-cache` · `leadgen_db` (Postgres) · `pgbouncer` :6432 · `qdrant` :6333 · `leadgen_postiz` (social publisher) · `leadgen_waha` (WhatsApp HTTP API) + observability set.
- **Caddy** = host-level reverse proxy (auto-HTTPS) → 127.0.0.1:8000. Port 8000 **externally firewalled** — bahar se hamesha domain se.
- systemd `leadgen` = installed-but-**DISABLED** (sirf last-resort rollback).
- **Code (`app/` + `frontend/` + `.claude/skills/`) Docker image me BAKED** → koi bhi code/skill change = rebuild + recreate. Sirf `./data` + `./logs` bind-mount hain (data-only change = no rebuild).

## 4. Source-of-truth hierarchy (kya kahan update hota hai)

1. `CLAUDE.md` — LEAN working memory (har turn load hoti hai; sirf current-state facts, 1-2 line updates — build logs NAHI)
2. `docs/SESSION_LOG.md` — dated history (milestones/incidents yahan append karo)
3. `app/marketing/packages.py` — billing/pricing truth
4. `.claude/skills/` — 187 SOPs/playbooks (governance: `SKILLS_PARITY.md` — naya skill banane se pehle existing dhoondo, cross-link karo, duplicate mat banao)
5. `docs/runbooks/` — 7 incident runbooks (index: `docs/runbooks/README.md`)
6. `docs/HANDOFF.md` — ye doc (naye operator ka entry-point; bade infra/process change pe isko bhi 1-line update karo)

## 5. Operate karne ka din (kya khud chalta hai)

- **Automation**: Celery durable scheduler (beat + workers) — ~37 scheduled jobs; flags `/api/growth/infra/flags`; health `/api/growth/infra/automation-health` (admin).
- **Cockpits**: `/app/office` (Operating HQ — live agent map, approvals, Ctrl+K palette, dark mode) · `/app/automation` (Mission Control, 28 tabs, Schedule tab = job control).
- **Approvals draft-safe** hain — koi auto-send nahi; human ✓/✕ hi final. Boss-review sirf recommendation deta hai.
- ⚠️ **Background automation IS WINDOWS REPO ME BHI chalti hai** — files edit karti hai AUR checked-out branch pe COMMITS banati hai (§8.1).

## 6. Deploy (pointer — copy nahi)

- **SOP** = `.claude/skills/leadgen-ops` — 4 gated steps: `prod_check.py` → targeted tests → push → SSH rebuild+recreate → done-gate (2× `/health` = `environment:production`).
- **VPS-level gotchas** = `.claude/skills/hostinger-deploy` — khaas **DRIFT-CHECK Step 0** (VPS tree chronically dirty; blind `reset --hard` ne kaam khoya hai).
- Quick-reference = `.claude/skills/verify-ship` (/verify + /ship) · tiering = `.claude/skills/ship-checklist`.
- **Live-VPS deploy = explicit user-auth, HAMESHA.** Deploy target (host/IP) user ke message se confirmed hona chahiye.

## 7. Incident (pointer)

- **Pehle 2 minute** = `.claude/skills/prod-incident-triage` — detect → py-spy **HOST se** (restart se PEHLE, evidence capture) → recover → root-cause.
- **Scenario runbooks** = `docs/runbooks/README.md` — queue backlog, scheduler failure, provider outage, billing, duplicate outreach, security, deploy failure.
- Golden rule: recover pehle, root-cause zaroor baad me — symptom-only fix = repeat incident.

## 8. Sharp edges (in SE HI log jalte hain — har naya operator padhe)

1. **Background automation checked-out branch pe commits banati hai** (2026-07-05 observed: feature branch pe mid-session 2 foreign commits) — push/merge se pehle `git log origin/main..HEAD --format="%h %s"` se foreign commits inspect karo. **KABHI `git add -A` mat karo** is repo me.
2. **Windows = source of truth** — sandbox/Linux mount file-edits ke baad STALE; "file truncated/syntax error" jaisa koi bhi conclusion Windows Read/venv pe confirm kiye bina mat do.
3. **Windows OpenSSH broken hai is PC pe** — hamesha Git ka ssh: `C:\PROGRA~1\Git\usr\bin\ssh.exe` (key `C:\Users\Ratanshila\.ssh\id_rsa`).
4. **VPS tree chronically dirty** — deploy se pehle `hostinger-deploy` ka DRIFT-CHECK (`git status --porcelain` + `docker diff leadgen_app`); drift dikhe to PRESERVE pehle.
5. **FastAPI first-route-wins** — naya route se pehle duplicate-route grep (`@router`/`@app` — godfile-split ke baad routes kai files me hain).
6. **Stale `.pyc`** — naya page-route 404 de to container recreate (fresh image me moot, par curl-verify hamesha).
7. **Celery flood** — repeated worker recreate ke baad `redis-cli llen celery`; >500-800 = `del celery` (beat re-schedules, safe).
8. **Brain-vault nightly sync** — `leadsgenai-brain` me manual additions bot overwrite kar sakta hai; pehle `git fetch`, aur bot-source allowlist ke bina naye folders mat banao.
9. **pydantic `.env` trap** — `/opt/leadgen/.env` me inline comments (`KEY=val # note`) ValidationError dete hain → app boot-crash.
10. **Compliance gates fail-CLOSED** — TRAI 9am–7pm calling window / DND scrub / AI-disclosure / DPDP KABHI disable nahi (CLAUDE.md user-mandate; conversation me DLT-paperwork recurring topic mat banao, par gates INTACT).

## 9. Access & secrets (sirf LOCATIONS — values kahin nahi)

- **VPS secrets**: `/opt/leadgen/.env` (gitignored; inline comments MANA — §8.9). Add/change ke baad app container recreate + `docker logs leadgen_app -n 10` me "Application startup complete".
- **SSH key**: `C:\Users\Ratanshila\.ssh\id_rsa` (VPS root; passphrase-free). Admin UI auth: browser localStorage `accessToken`.
- Values is doc me, committed files me, `.bat` me, ya CLAUDE.md me **KABHI nahi** — `scripts/check_secrets.py` verify-gate hai.

## 10. Current state (2026-07-05)

- **Office-enterprise-upgrade LIVE** (`c2b7328`): 6 map bug fixes (unique agent tints, overflow shrink, offline snap-back, unmapped "?" badge, ticker-box mobile fix, Simple→Pro blank-map root-fix = lazy Phaser boot) + dark mode + Ctrl+K palette + toast alerts + 6 sections + scroll-spy + battery-friendly polling. Guard: `tests/test_office_map_frontend.py`.
- **free_ai.py provider fix** (dead OpenRouter free-model ids + circuit-breaker gap) isi deploy me SHIP hua — SESSION_LOG 2026-07-05 ka "VPS deploy PENDING" resolved.
- **Known pending**: MCP mount refused (`FASTAPI_MCP_TOKEN` `.env` me unset) — Arya (MCP-Engineer agent) alert karta rahega jab tak set na ho.
- **Launch status**: marketing tiers + inbound callbacks = live-ready (DLT nahi chahiye); sirf voice cold-calling DLT pe blocked.
