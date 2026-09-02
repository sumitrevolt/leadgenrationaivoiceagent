# Project Handoff + Core-Ops SOP Upgrade — Design

**Date:** 2026-07-05 · **Approved by:** user (chat) · **Scope choice:** "Master handoff + core ops SOPs" (user-selected)

## Goal

Ek naya master `docs/HANDOFF.md` (Hinglish, agent-first, human-readable) jo kisi bhi naye AI session ya developer ko cold-start se poora project operate karne layak bana de — plus 6 core ops SOP skills ka additive, current-state upgrade with aaj ke session-learnings.

## Audience

Dono — AI agent (primary: exact commands, gates, file paths) + insaan (context, business direction). Language: Hinglish, CLAUDE.md jaisa lean style.

## Non-goals

- 187-skill library ka full audit (alag multi-agent task, user ne explicitly defer kiya)
- Headline docs (README/ARCHITECTURE/AUTOMATION) ka sweep (defer)
- Brain-vault (leadsgenai-brain) me koi edit — nightly bot overwrite risk
- Kisi SOP ka rewrite — sirf additive/corrective edits
- VPS deploy — docs/skills image me baked hote hain, next scheduled deploy pe live honge; operator-use ke liye Windows files hi kaafi

## Deliverables

### 1. `docs/HANDOFF.md` (naya, ~350-450 lines)

Pointer-heavy (SKILLS_PARITY anti-duplication rule — skills/runbooks LINK karo, copy nahi). Sections:

1. **Ye project kya hai** — DO products (Marketing main ₹1,999/₹5,999 + Voice standalone band A/B/C), live https://leadsgenai.in, repo github.com/sumitrevolt/leadgenrationaivoiceagent
2. **Teen-directory layout** — (a) `Documents\leadgenrationaiagent` = code (source of truth), (b) `Documents\leadsgenai-brain` = Obsidian vault, bot-synced nightly (manual edits overwrite-risk), (c) `source\repos` = generic vendored skills master (project-agnostic)
3. **Live infra map** — VPS 72.61.245.204 (Hostinger Mumbai, Ubuntu 24.04), `/opt/leadgen`, Docker containers: leadgen_app :8000, worker, worker_heavy, scheduler, redis, redis-cache, db, pgbouncer, qdrant, postiz, waha; Caddy host-proxy; systemd `leadgen` installed-but-DISABLED (rollback)
4. **Source-of-truth hierarchy** — CLAUDE.md (lean working memory, har turn load) → docs/SESSION_LOG.md (dated history) → app/marketing/packages.py (billing truth) → .claude/skills/ (SOPs) → docs/runbooks/ (incidents). Kya kahan update hota hai + token discipline rule
5. **Operate karne ka din** — scheduled automation (team_scheduler, self-improve loops), cockpits: /app/office (Operating HQ), /app/automation (Mission Control), approvals flow (draft-safe, human ✓/✕)
6. **Deploy** — 1-line gate summary + pointer to `.claude/skills/leadgen-ops` (4 gated steps + done-gate)
7. **Incident** — pointer to `prod-incident-triage` skill + docs/runbooks/ index
8. **Sharp edges (gotchas)** — background automation checked-out branch pe COMMITS banati hai (2026-07-05 observed; push se pehle `git log` me foreign commits inspect karo); Windows = source of truth (sandbox mounts stale); Git ka ssh.exe use karo (Windows OpenSSH broken); FastAPI first-route-wins; stale `.pyc` = new-route 404 (container recreate); celery flood after repeated worker recreate (`llen celery` >800 = `del celery`); brain-vault nightly sync manual additions delete kar sakta hai; never `git add -A` is repo me
9. **Access & secrets** — sirf LOCATIONS: `/opt/leadgen/.env` (VPS, gitignored), `~/.ssh/id_rsa` (VPS key), localStorage accessToken (admin UI) — values KABHI is doc me nahi
10. **Current state + pending** — 2026-07-05 tak: office-enterprise-upgrade live (c2b7328), free_ai.py fix SHIPPED (kal ka "PENDING" resolved), MCP mount refused warning (FASTAPI_MCP_TOKEN unset) = known pending

### 2. Core-ops SOP upgrades (6 skills, additive edits)

| Skill | Edit |
|---|---|
| `leadgen-ops` | + Gate-3 me foreign-commit check (`git log origin/main..HEAD` — automation ke commits pehchano); + targeted-test list me `test_office_map_frontend.py`; + deploy-target user-confirm note (host user ke message se aana chahiye); + Step-4 note: office frontend = pure `app` recreate kaafi |
| `ship-checklist` | Current gates se sync (foreign-commit check add) |
| `verify-ship` | `test_office_map_frontend.py` + prod_check route-count (1030, 2026-07-05) sync |
| `hostinger-deploy` | Container list current karo (postiz, waha add agar missing); user-confirm gate note |
| `prod-incident-triage` | + symptom row: "office map blank on Simple→Pro" → RESOLVED root-cause reference (lazy Phaser boot, 2026-07-05) — future regression triage ke liye |
| `fable-operating-manual` | Evidence section me live-browser verification pattern (serve frontend static + preview-mode checks) add |

### 3. Index/log refreshes

- `docs/runbooks/README.md` — index me HANDOFF.md + skills cross-links current karo
- `docs/SESSION_LOG.md` — 2026-07-05 entry: office-upgrade ship + free_ai deploy note correction
- `CLAUDE.md` — 1 line: HANDOFF.md pointer (lean rule follow — sirf ek line)

## Constraints

- Never `git add -A` (background automation) — explicit paths only
- Feature branch pe kaam, merge on green, push user-confirm pe
- SOP edits ADDITIVE — koi existing gate/rule remove nahi
- Har edited skill file me exact date-stamped notes (repo convention: "(2026-07-05)")
- Facts jo HANDOFF me jaayen wo is session me VERIFY hue hon ya CLAUDE.md/SESSION_LOG se aaye hon — andaaza nahi

## Success criteria

- Naya operator HANDOFF.md padh kar: repo dhoondh sake, deploy chala sake (skill follow karke), incident triage start kar sake, gotchas se bach sake
- Sab existing tests green rahen (docs-only change, but `prod_check.py` bhi green — skills parse hoti hain)
- Koi duplication nahi — HANDOFF points, doesn't copy
