# Autonomous Infra Design — skills-on-VPS + code-upgrader + always-busy agents (2026-06-11)

## Goal (user brief)
Agents hamesha kaam karte rahein (continuous tasks, self-improvise loop) — sab **VPS pe, Claude pe nahi**.
Claude ki skills ka "plugin" VPS pe ho taki free-LLM agents seekhte rahein. Ek system-agent ho jo zaroorat
padne par **code upgrade** kare (hybrid autonomy: safe files auto, core code human-gated).

## Already-true (rebuild NAHI)
- Scheduler VPS pe: Celery beat (`leadgen_scheduler`) + worker (`leadgen_worker`), `RUN_IN_PROCESS_SCHEDULER=0`.
- Continuous loop: `agents/self_improve.py` (`SELF_IMPROVE_LOOP=1`, 180s self-requeue, 60/day cap, dead-man revive).
- Learning ledger: `platform/skill_library.py` (success-rates + lessons, epsilon-greedy pick).
- 35 project skills `.claude/skills/*/SKILL.md` — repo me committed → **VPS pe pehle se maujood** (sirf Claude padhta tha).

## New components

### 1. Skill pack (`app/platform/skill_pack.py`) — skills → VPS agents
- Loader/retriever over `.claude/skills/*/SKILL.md` + **`data/skills_extra/*.md`** (agent-authored, runtime-live
  kyunki `data/` bind-mounted hai — image rebuild nahi chahiye).
- `find(query,k)` keyword-overlap → `snippet_for(topic)` prompt-injectable text (≤1200 chars).
- `ingest_to_kb()` → KnowledgeBase namespace `skills` (Qdrant semantic recall, voice/chat agents ke liye).
- Wiring (gated `SKILL_PACK=1`): self_improve reflection prompt me relevant skill snippet inject; naya action
  `study_skills` (skill padho → lesson record → skill_library). trainer job me daily `ingest_to_kb()`.
- Mtime-cache, never-raise, flag OFF = zero behaviour change.

### 2. Code upgrader (`app/agents/code_upgrader.py`, persona **Vikram 🛠️**) — hybrid autonomy
**Docker reality**: app code image me baked hai — live file-patch container pe lagta hi nahi. Isliye tiers:
- **Tier-1 AUTO (runtime-live)**: sirf `data/skills_extra/` markdown (size-cap 16KB, `..`/path-escape block,
  markdown-only). Agent naye skills/lessons LIKH sakta hai jo skill_pack turant serve karta — "LLM seekhta rahe".
- **Tier-2 GATED (core code)**: scan (llm_metrics errors + automation_health failing jobs + skill_library worst)
  → free-LLM **patch PROPOSAL** (file, rationale, suggested diff/sketch) → `data/code_patches.jsonl` + email
  alert → admin API approve/reject. Apply HAMESHA normal deploy loop se (git push → CI/rebuild) — auto-apply
  core code KABHI nahi (prod-down lessons).
- Gated `CODE_UPGRADER=1`; watchdog (hourly) job me scan, dedupe per issue/day, never-raise.

### 3. Agents badao + busy rakho
- 2 naye staff (total 12): **Vikram 🛠️ Code Upgrader** · **Guru 📚 Skill Trainer** — dono REAL jobs se wired
  (scan/ingest events → agent_events → /app/team).
- self_improve ACTIONS += `study_skills` (LLM, learning) + `code_scan` (light) — stage-bias me wired
  (outreach_quality/scale me study, scale me scan) → loop ab marketing/leads ke saath self-coding bhi explore karta.

## API (growth.py, admin; /skills/library se alag namespace)
`GET /api/growth/skills/pack` · `POST /skills/pack/ingest` · `POST /skills/pack/author` (Tier-1 write) ·
`POST /upgrader/scan` · `GET /upgrader/patches` · `POST /upgrader/patches/{id}/status` (approve/reject).
Flags registry += `SKILL_PACK`, `CODE_UPGRADER`.

## Trade-offs
- Patch proposals (diff-sketch) vs real auto-apply: deploy-pipeline integrity + container immutability >> speed;
  approve hone ke baad apply 1 Claude/ship session hai.
- Keyword retrieve (skill_pack.find) vs embeddings: zero-dep/zero-latency; semantic recall KB-ingest se milta hai.
- Naye beat entries NAHI — existing trainer/watchdog jobs me hook (worker.py untouched, boot-grace non-issue).

## Production readiness — code-side ab complete; bache USER-ACTION
Razorpay API 401 fix + webhook register · UPI_VPA · DLT/Exotel KYC · R2/B2 offsite creds · Meta/GBP approvals.

## Revisit when
Clients >50 (skill_pack → per-client namespaces), patches >20/week (CI me sandboxed auto-test lane),
multi-VPS (skills_extra → object storage).
