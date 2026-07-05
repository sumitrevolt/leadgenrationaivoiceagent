# Project Handoff + Core-Ops SOP Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create master `docs/HANDOFF.md` and apply additive current-state upgrades to 6 core ops SOPs + 3 index/log refreshes, per the approved spec (`docs/superpowers/specs/2026-07-05-project-handoff-sop-upgrade-design.md`).

**Architecture:** Docs-only change on branch `handoff-sop-upgrade-2026-07-05`. HANDOFF.md is pointer-heavy (SKILLS_PARITY anti-duplication); SOP edits are surgical/additive with date-stamps. Verification = marker greps + `prod_check.py` (Trivial tier: steps 1+3 of verify-ship).

**Tech Stack:** Markdown only. Windows venv for prod_check.

## Global Constraints

- Never `git add -A` — explicit paths only (background automation active).
- SOP edits ADDITIVE — no existing gate/rule removed.
- Date-stamp every SOP addition "(2026-07-05)".
- All facts verified this session or sourced from CLAUDE.md/SESSION_LOG.
- Secrets: locations only, never values.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: Create `docs/HANDOFF.md`

**Files:**
- Create: `docs/HANDOFF.md`

**Interfaces:**
- Produces: the master handoff doc that Tasks 2–4 cross-link as `docs/HANDOFF.md`.

- [ ] **Step 1: Write the file** with the complete content below (Hinglish, pointer-heavy):

The document must contain these 10 sections with this exact content skeleton (full prose written at execution, following spec section list; every fact below is session-verified):

```markdown
# 🤝 PROJECT HANDOFF — LeadGen AI (leadsgenai.in)

> Naya AI session ya naya developer? YE doc pehle padho — 15 minute me poora project
> operate karne layak. Ye doc POINT karta hai, duplicate nahi karta (SKILLS_PARITY rule).
> Detail hamesha linked skill/doc me hai. Last full-verify: 2026-07-05.

## 1. Ye project kya hai
- DO alag products (ADR-009): (1) AI Automated Marketing = MAIN (₹1,999 Main / ₹5,999 Advanced+voice-feature),
  (2) AI Voice Calling Agent = standalone (band A ₹4,999 / B ₹9,999 / C ₹19,999 flat monthly).
- LIVE: https://leadsgenai.in (Hostinger VPS Mumbai). Repo: github.com/sumitrevolt/leadgenrationaivoiceagent (main).
- Pricing source-of-truth = app/marketing/packages.py + app/billing/voice_packages.py (numbers KABHI docs me copy mat karo).
- Stack: FastAPI + Celery/Redis + Postgres(PgBouncer) + Qdrant, Docker Compose, ~1030 routes.

## 2. Teen-directory layout (Windows PC)
| Directory | Kya hai | Edit karna? |
|---|---|---|
| Documents\leadgenrationaiagent | ASLI code repo (source of truth) | Haan — yahi kaam karo |
| Documents\leadsgenai-brain | Obsidian notes vault, NIGHTLY BOT-SYNC | Dhyan se — manual additions bot delete kar sakta |
| source\repos | Generic vendored dev-skills master (project-agnostic) | Project-kaam yahan NAHI |

## 3. Live infra map
- VPS 72.61.245.204 (srv1736379, Ubuntu 24.04, Hostinger Docker template), app dir /opt/leadgen.
- Containers (2026-07-05 verified): leadgen_app :8000 · leadgen_worker · leadgen_worker_heavy · leadgen_scheduler (beat)
  · leadgen_redis · redis-cache · leadgen_db (Postgres) · pgbouncer :6432 · qdrant :6333 · leadgen_postiz · leadgen_waha.
- Caddy = host-level reverse proxy (auto-HTTPS) → 127.0.0.1:8000. Port 8000 externally firewalled.
- systemd `leadgen` = installed-but-DISABLED (last-resort rollback only).
- Code (`app/` + `frontend/` + `.claude/skills/`) image me BAKED → change = rebuild. `./data` + `./logs` = bind-mount (no rebuild).

## 4. Source-of-truth hierarchy (kya kahan update hota hai)
1. `CLAUDE.md` — LEAN working memory (har turn load; sirf current-state facts, 1-2 line updates)
2. `docs/SESSION_LOG.md` — dated history (milestones/incidents yahan append)
3. `app/marketing/packages.py` — billing/pricing truth (+ `test_billing_truth_2026.py` saath)
4. `.claude/skills/` — SOPs/playbooks (187 skills; index: SKILLS_PARITY.md — duplicate mat banao, cross-link karo)
5. `docs/runbooks/` — incident runbooks (7)
6. `docs/HANDOFF.md` — ye doc (naya operator entry-point)

## 5. Operate karne ka din (kya khud chalta hai)
- Automation loops: Celery durable scheduler (leadgen_scheduler beat + workers) — ~37 jobs; flags /api/growth/infra/flags.
- Cockpits: /app/office (Operating HQ — map, approvals, Ctrl+K palette) · /app/automation (Mission Control, 28 tabs).
- Approvals draft-safe hain — koi auto-send nahi; human ✓/✕ hi final.
- Background automation IS REPO ME BHI chalti hai (Windows-side) — files edit karti hai AUR checked-out branch pe COMMITS banati hai (§8).

## 6. Deploy (pointer)
- SOP = `.claude/skills/leadgen-ops` (4 gated steps: prod_check → targeted tests → push → SSH rebuild+recreate → 2× health done-gate).
- VPS-level gotchas = `.claude/skills/hostinger-deploy` (DRIFT-CHECK Step 0 zaroori — VPS tree chronically dirty).
- Live-VPS deploy = explicit user-auth, hamesha. Deploy target user ke message se confirm hona chahiye.

## 7. Incident (pointer)
- Pehle 2 minute = `.claude/skills/prod-incident-triage` (detect → py-spy HOST se → recover → root-cause).
- Scenario runbooks = `docs/runbooks/README.md` (queue backlog, scheduler failure, provider outage, billing, duplicate outreach, security, deploy failure).

## 8. Sharp edges (in se HI log jalte hain)
1. **Background automation checked-out branch pe commits banati hai** (2026-07-05 observed) — push/merge se pehle
   `git log origin/main..HEAD` me foreign commits inspect karo. Kabhi `git add -A` mat karo.
2. **Windows = source of truth** — sandbox/Linux mount STALE ho jata hai; "file truncated/syntax error" pehle Windows pe confirm.
3. **Windows OpenSSH broken** — hamesha Git ka ssh: `C:\PROGRA~1\Git\usr\bin\ssh.exe` (key `~\.ssh\id_rsa`).
4. **VPS tree chronically dirty** — blind `reset --hard` ne kaam khoya hai (2026-07-01/02) → hostinger-deploy DRIFT-CHECK pehle.
5. **FastAPI first-route-wins** — naya route add karne se pehle duplicate-route grep.
6. **Stale `.pyc`** — naya page-route deploy ke baad 404 de to container recreate (fresh image me moot, par verify hamesha).
7. **Celery flood** — repeated worker recreate ke baad `redis-cli llen celery` >500-800 = `del celery` (beat re-schedules).
8. **Brain-vault nightly sync** — leadsgenai-brain me manual additions bot ke overwrite se ud sakte hain.
9. **pydantic .env trap** — /opt/leadgen/.env me inline comments ValidationError dete hain.
10. **Compliance gates fail-CLOSED** — TRAI 9am-7pm window / DND / AI-disclosure KABHI disable nahi (CLAUDE.md mandate).

## 9. Access & secrets (sirf LOCATIONS)
- VPS secrets: `/opt/leadgen/.env` (gitignored; inline comments MANA). Add/change ke baad app recreate.
- SSH key: `C:\Users\Ratanshila\.ssh\id_rsa` (VPS root). Admin UI auth: browser localStorage `accessToken`.
- Values is doc me, committed files me, ya CLAUDE.md me KABHI nahi (`scripts/check_secrets.py` gate).

## 10. Current state (2026-07-05)
- Office-enterprise-upgrade LIVE (c2b7328): 6 map bug fixes + dark mode + Ctrl+K palette + toasts + sections.
- free_ai.py provider fix (dead OpenRouter ids + breaker gap) SHIPPED isi deploy me (SESSION_LOG ka "PENDING" resolved).
- Known pending: MCP mount refused (FASTAPI_MCP_TOKEN unset in .env) — Arya alerts karega jab tak set nahi hota.
- Launch-blocked sirf voice cold-calling (DLT); marketing tiers + inbound = live-ready.
```

- [ ] **Step 2: Verify markers**

Run: `grep -c "Sharp edges\|Teen-directory\|Source-of-truth\|leadgen-ops" docs/HANDOFF.md`
Expected: ≥4 (all sections present)

- [ ] **Step 3: Commit**

```bash
git add docs/HANDOFF.md
git commit -m "docs: master project HANDOFF — cold-start operator guide (pointer-heavy, Hinglish)"
```

---

### Task 2: Deploy-trio SOP upgrades (`leadgen-ops`, `verify-ship`, `ship-checklist`)

**Files:**
- Modify: `.claude/skills/leadgen-ops/SKILL.md` (Step 3 gate ~line 22; Step 4 ~line 24; test list ~line 20)
- Modify: `.claude/skills/verify-ship/SKILL.md` (/ship section ~line 43)
- Modify: `.claude/skills/ship-checklist/SKILL.md` (Process step 3 ~line 17)

**Interfaces:**
- Consumes: `docs/HANDOFF.md` path from Task 1 (cross-links).

- [ ] **Step 1: leadgen-ops — 3 additive edits:**

(a) In Step 3 (Git push), append to the gate line:
```
   → **GATE**: push success (remote SHA match) confirm karo. **+ (2026-07-05) Foreign-commit check**: push se pehle `git log origin/main..HEAD --format="%h %s"` — background automation checked-out branch pe apne commits banati hai; unhe pehchano (inspect, intentionally include/exclude) — anjaane me automation ka unreviewed kaam push mat karo.
```

(b) In Step 4, after the ssh block's quoting note, add:
```
   - **(2026-07-05) DRIFT-CHECK pehle**: upar wala one-liner blind `reset --hard` karta hai — VPS tree chronically dirty rehta hai (live hotfixes); pehle `hostinger-deploy` skill ka Step-0 drift-check (`git status --porcelain` + `docker diff leadgen_app`) chalao, drift dikhe to PRESERVE karo.
   - **(2026-07-05) Deploy target = user-confirmed**: host/IP user ke message se confirm hona chahiye (docs se uthaya hua target user ko bata ke haan lo) — permission classifier bhi yahi enforce karta hai.
```

(c) In Step 2 (Tests), append to the targeted-suite sentence:
```
Frontend office map touch hua → `tests\test_office_map_frontend.py` (JS syntax gate + no-removal guard, 2026-07-05) zaroor.
```

- [ ] **Step 2: verify-ship — 1 edit.** In `## /ship`, after "2. Commit (user asked)...", add:
```
2b. (2026-07-05) `git log origin/main..HEAD` — foreign/automation commits inspect karo (background automation branch pe commit karti hai)
```
And in step 4's ssh block, prefix line: `# DRIFT-CHECK pehle (hostinger-deploy Step-0) — VPS tree dirty ho sakta hai`

- [ ] **Step 3: ship-checklist — 1 edit.** In Process step 3, append:
```
(2026-07-05) Push se pehle `git log origin/main..HEAD` — background-automation ke foreign commits inspect karo; `git add -A` KABHI nahi.
```

- [ ] **Step 4: Verify + commit**

Run: `grep -l "2026-07-05" .claude/skills/leadgen-ops/SKILL.md .claude/skills/verify-ship/SKILL.md .claude/skills/ship-checklist/SKILL.md`
Expected: all 3 paths printed.

```bash
git add .claude/skills/leadgen-ops/SKILL.md .claude/skills/verify-ship/SKILL.md .claude/skills/ship-checklist/SKILL.md
git commit -m "docs(sop): deploy-trio upgrade — foreign-commit check, VPS drift-check cross-link, office frontend test, user-confirmed deploy target"
```

---

### Task 3: Infra/ops SOP upgrades (`hostinger-deploy`, `prod-incident-triage`, `fable-operating-manual`)

**Files:**
- Modify: `.claude/skills/hostinger-deploy/SKILL.md` (facts ~line 14)
- Modify: `.claude/skills/prod-incident-triage/SKILL.md` (freeze-class table ~line 20)
- Modify: `.claude/skills/fable-operating-manual/SKILL.md` (§0.5 Evidence ~line 24)

- [ ] **Step 1: hostinger-deploy — facts refresh.** In the live-server facts (Scheduler line), replace the container summary line's tail with current verified list:
```
- Scheduler = **Celery durable (LIVE)**: `leadgen_worker` + `leadgen_worker_heavy` + `leadgen_scheduler` containers (`--profile celery`). (2026-07-05 verified) Full set: app · worker · worker_heavy · scheduler · redis · redis-cache · db · pgbouncer · qdrant · **postiz** (social publisher) · **waha** (WhatsApp HTTP API) + obs containers.
```

- [ ] **Step 2: prod-incident-triage — 1 table row** (after "Stuck/backed-up Celery worker" row):
```
| Office map blank (Simple→Pro) | /app/office Pro-switch pe canvas khali; JS console clean | RESOLVED 2026-07-05 (lazy Phaser boot — `OFFICE.bootGame`); regression dikhe to frontend/office_map.html me bootGame guard + `tests/test_office_map_frontend.py` dekho |
```

- [ ] **Step 3: fable-operating-manual — Evidence pattern add.** In §0.5 phase 5, append:
```
Frontend/page change ka evidence = live-browser verification bhi: `cd frontend && python -m http.server 8123` se statically serve karke claude-in-chrome se drive karo (API-less preview path me bhi map/UI boot verify hota hai — 2026-07-05 office-upgrade pattern).
```

- [ ] **Step 4: Verify + commit**

Run: `grep -l "2026-07-05" .claude/skills/hostinger-deploy/SKILL.md .claude/skills/prod-incident-triage/SKILL.md .claude/skills/fable-operating-manual/SKILL.md`
Expected: all 3 paths.

```bash
git add .claude/skills/hostinger-deploy/SKILL.md .claude/skills/prod-incident-triage/SKILL.md .claude/skills/fable-operating-manual/SKILL.md
git commit -m "docs(sop): infra-trio upgrade — full container list, office-map-blank triage row, live-browser evidence pattern"
```

---

### Task 4: Index/log refreshes + final verify

**Files:**
- Modify: `docs/runbooks/README.md` (standing facts ~line 10)
- Modify: `docs/SESSION_LOG.md` (append entry)
- Modify: `CLAUDE.md` (1 pointer line in header note)

- [ ] **Step 1: runbooks README.** Update Workers standing-fact line to:
```
- **Workers** = `leadgen_worker` + `leadgen_worker_heavy` (Celery) + `leadgen_scheduler` (beat) — `--profile celery`. Sahayak: `leadgen_postiz` (social) + `leadgen_waha` (WhatsApp). (2026-07-05)
```
And after the index table, add: `> Naye operator ke liye entry-point: [docs/HANDOFF.md](../HANDOFF.md)`

- [ ] **Step 2: SESSION_LOG entry.** Append:
```
## 2026-07-05 — Office-enterprise-upgrade SHIPPED + handoff/SOP refresh [Claude Code session]
- **Office upgrade LIVE (c2b7328)**: 6 map bug fixes (unique agent tints, overflow shrink, offline snap-back, unmapped ? badge, ticker-box mobile fix, Simple→Pro blank-map ROOT-CAUSED = Phaser boot before simple-mode class → 0x0 canvas bake; fix = lazy `OFFICE.bootGame`) + dark mode + Ctrl+K palette + toasts + 6 sections + scroll-spy + battery polling pause. New guard: `tests/test_office_map_frontend.py` (15 tests). Deploy: full gated loop, app+worker+worker_heavy+scheduler recreated, 2× health production, celery llen 0.
- **NOTE**: kal ka free_ai.py fix ("VPS deploy PENDING") isi deploy me SHIP ho gaya (origin/main reset).
- **Gotcha DOCUMENTED**: background automation checked-out branch pe COMMITS banati hai (2 commits mid-session observed) — deploy-trio SOPs me foreign-commit check add hua.
- **New**: docs/HANDOFF.md (master cold-start operator guide) + 6 ops-SOP additive upgrades + runbooks README refresh.
```

- [ ] **Step 3: CLAUDE.md pointer.** In the header blockquote (after the SESSION_LOG line), add one line:
```
> Naya session / cold-start? **`docs/HANDOFF.md`** = master handoff (infra map, sharp edges, SOP pointers).
```

- [ ] **Step 4: Final verify (Trivial tier = verify-ship quick)**

Run: `.venv\Scripts\python scripts/prod_check.py` → Expected: ALL CHECKS PASSED.
Run: `grep -c "HANDOFF" CLAUDE.md docs/runbooks/README.md` → Expected: ≥1 each.

- [ ] **Step 5: Commit**

```bash
git add docs/runbooks/README.md docs/SESSION_LOG.md CLAUDE.md
git commit -m "docs: runbooks index + SESSION_LOG 2026-07-05 + CLAUDE.md HANDOFF pointer"
```

---

## Self-Review

- **Spec coverage:** HANDOFF 10 sections → Task 1. 6 SOPs → Tasks 2-3 (deploy-trio + infra-trio). 3 refreshes → Task 4. Non-goals respected (no brain-vault edits, no deploy). ✅
- **Placeholders:** none — full content/anchors in every step. ✅
- **Consistency:** container names match 2026-07-05 verified list everywhere (worker_heavy underscore in container name, worker-heavy hyphen in compose service — ship gotcha already documented in leadgen-ops, not re-stated). ✅
