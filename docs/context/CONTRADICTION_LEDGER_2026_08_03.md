# Contradiction Ledger — Wave 0/1 (2026-08-03)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | STALE | FIXED-LOCAL | OWNER-ACTION-REQUIRED

## Git / production baseline (revalidated this session)

| Fact | Evidence | Label |
|------|----------|-------|
| `origin/main` | `303b061f9212b1eb44be9ba2fdb026cf5a670b3a` | GIT_VERIFIED |
| Prod `/health.version` | `303b061f` healthy production | PRODUCTION-PROVEN |
| Primary checkout | `cursor/docs-ops-truth-buzz-freeai` @ `fc859bf` — **untouched** | GIT_VERIFIED |
| Implementation worktree | `C:\Users\Ratanshila\Documents\leadgen-wt-blueprint-2026-08-03` @ branch `cursor/master-blueprint-world-class-2026-08-03` from `origin/main` | GIT_VERIFIED |
| Open PRs | none | GIT_VERIFIED |
| `fc859bf` PR | none (docs-only branch local) | GIT_VERIFIED |
| `opencode.jsonc` | untracked on primary — preserved | GIT_VERIFIED |

## Source inventories (worktree @ 303b061f + local P0 patches)

| Item | Count | Label |
|------|------:|-------|
| Blueprint nodes/edges/flows/orphans | 59 / 56 / 11 / 0 | CODE-PRESENT (validate_graph) |
| Workforce | 31 | CODE-PRESENT |
| `AUTOMATION_FLAGS` | 328 (was 327 + `PLATFORM_DIAL_LIMIT`) | CODE-PRESENT (mixed types — not all booleans) |
| `JOB_META` | 43 | CODE-PRESENT |

## Contradictions

### C1 — `/health/ready` llm.provider=gemini vs free-AI primary
- **Observed:** live ready JSON `llm.provider=gemini` while ops truth + free_ai chain = Groq→Cerebras→Mistral when `GEMINI_PRIMARY=false`.
- **Root cause:** `_check_llm_config` returned gemini whenever `GEMINI_API_KEY` set.
- **Fix (this worktree):** report first configured hop of `free_ai.describe().llm_chain` + `providers` list.
- **Status:** FIXED-LOCAL (tests green). Prod still shows old label until deploy.
- **Label:** TEST-PROVEN (local) · PRODUCTION-PROVEN defect still live until deploy.

### C2 — `agent_runtime.runtime_status().calling_badge` hard-coded "Calling HARD OFF"
- **Observed:** Owner OS already uses `calling_posture()` (LIVE when dial on); runtime status still lied.
- **Fix:** reuse `owner_os.calling_posture().badge`.
- **Also:** `frozen_transfer_status` note no longer claims platform_dial HARD OFF (Agent Runtime RED ≠ campaign).
- **Status:** FIXED-LOCAL.

### C3 — Docs count drift
- Fixed locally: `ARCHITECTURE_BLUEPRINT.md` defers to `validate_graph`; `AGENT_REGISTRY.md` no longer hardcodes 24 jobs; `TRUTH_MATRIX.md` points at Pranav-only production-proof; `AUTOMATION_MAX_READINESS_MATRIX.md` superseded banner + dial/WA/autopilot rows corrected.
- Drift tests: `tests/test_docs_inventory_drift.py`.
- **Status:** FIXED-LOCAL.

### C4 — Flag registry semantics weak
- 327 entries mix booleans, limits, URLs, secrets.
- **Fix (local):** `app/platform/automation_flag_manifest.py` + `/api/growth/infra/flags` now returns `kind`/`lifecycle`/`boolean_on_count` (no mass enable).
- **Status:** FIXED-LOCAL (scaffold); full evidence overlays still incomplete for unclassified majority.

### C5 — ADR-148 records-only vs ADR-149 runner
| Layer | State | Evidence |
|-------|-------|----------|
| ADR-148 orchestrator | CODE-PRESENT · flag `EXTERNAL_AGENT_ORCHESTRATOR` default OFF | `app/dev_control/external_agents/` · memory ADR-148 |
| ADR-149 runner | CODE-PRESENT on tree · ADR status refreshed | `docs/adr/ADR-149-external-agent-runner.md` · `runner/` dual-gate |
| Prod flags | CONFIGURED-INERT / OFF | runbook: both flags required; prod must stay OFF |
| Semantics | Orchestrator alone = records/missions; runner = unattended CLI canary (Windows/local) | `runner/flags.py` requires BOTH |
- **Status:** DOCUMENTED — no prod flip; no second control plane.

## Safety invariants preserved (do not flip)

- Cold/bulk WhatsApp OFF
- Post-call interested WA = separate owner-armed path
- UPI auto-activation manual
- Free AI only — no paid providers added
- Swara/Ananya Agent Runtime RED blocked even if dial campaign live
- No `.env` / deploy / commit without owner ask

## Active workstreams (max 3)

1. **WS-BP1** P0 truth honesty (health LLM + calling badge) — IN PROGRESS / local green
2. **WS-R1** Autopilot refill — ARMED LIVE (prod; observe only)
3. **WS-R3** Estique pay-truth — OWNER (no fabricate)
