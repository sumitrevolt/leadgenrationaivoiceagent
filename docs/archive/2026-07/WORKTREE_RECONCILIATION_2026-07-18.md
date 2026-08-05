# Worktree Reconciliation — 2026-07-18

_Read-only classification + zero-collision hygiene fixes. No reset/clean/checkout/stash/rebase/branch-switch/bulk-move/bulk-delete was run. No parallel-agent work was edited._

## Git state (Windows working copy)
- Branch: `fix/ci-lock-transitives` (tracks `origin/fix/ci-lock-transitives`, in sync)
- Local HEAD: `c4faf9f8b5d9f9d54b87e97d98eebfc478143a0a` (already an ancestor of origin/main — nothing unpushed at risk)
- `origin/main`: `f8a5f6e9994610987bab2def0c48ee36a546553b`
- Modified tracked: **17** · Real untracked (exclude-standard): **18** (was ~100+; the temp sprawl is now ignored)
- Ignored (excluded) total: ~75.6k — dominated by pre-existing patterns (`.claude/worktrees/` full-repo copies, `.venv`, `node_modules`, `data/*`), not by the new rules.

## Workstream map (parallel WIP — Category A, PRESERVED byte-for-byte)
Coherent groups inferred from paths; each should be committed by its owner, not bundled:
- **Customer dashboard / growth:** `app/api/customer_dashboard.py`, `app/api/growth.py`, `frontend/customer_dashboard.html`, `frontend/inbox.html`, `tests/test_customer_marketing_tools.py`
- **Marketing / reply agent:** `app/marketing/content_approval.py`, `app/marketing/gbp_audit.py`, `app/platform/reply_agent.py`
- **Context/memory/docs:** `CLAUDE.md`, `AGENTS.md` (keep byte-identical), `memory/backlog.md`, `memory/incidents.md`, `progress.md`, `docs/SESSION_LOG.md`, `docs/plans/2026-07-18-billing-containment-ops.md`
- **Runtime data (not a code change):** `data/delivery_ledger/jiya-makeover.jsonl`
- **This session's hygiene change (separate):** `.gitignore` (narrowed — see below)

## Artifact classification (A–E)

| Path (representative) | Git status | Category | Owner/workstream | Unique evidence? | Recommended action | Collision risk |
|---|---|---|---|---|---|---|
| app/api/*, app/marketing/*, app/platform/reply_agent.py | modified | A | parallel product | no | preserve; owner commits per workstream | high (don't touch) |
| frontend/customer_dashboard.html, frontend/inbox.html | modified | A | dashboard | no | preserve | high |
| tests/test_customer_marketing_tools.py | modified | A | dashboard | no | preserve | high |
| CLAUDE.md, AGENTS.md, memory/*, progress.md, docs/SESSION_LOG.md | modified | A | context/memory | no | preserve; keep AGENTS.md==CLAUDE.md | high |
| data/delivery_ledger/jiya-makeover.jsonl | modified | A/runtime | runtime | no | leave (runtime data) | med |
| .gitignore | modified | hygiene | THIS session | no | Commit 1 (narrowed rules) | none (0 tracked matches) |
| scripts/_canary_{analyze,omni_check,place_call,verify,remote,run,omni}.{py,sh,bat} | untracked | **B** | voice-QA canary | no (tools) | review → rename to `scripts/canary/` + header doc → track | low |
| scripts/_accept_call_once.py, _parse_accept.py, _summarize_latest_call.py | untracked | B | call helpers | no | review; track if reusable | low |
| scripts/add_pinterest_key.ps1 | untracked | B | setup util | no | track | low |
| .claude/commands/a2z-launch-enterprise-audit.md, .claude/skills/a2z-launch-enterprise-audit/SKILL.md | untracked | B | new skill | no | track (belongs in git) | low |
| .cursorignore | untracked | B/config | tooling config | no | track | low |
| ~97 scripts/_tmp_* (one-off) | ignored | **C** | past debug sessions | no | keep on disk (ignored); sweep to scripts/_debug/ or delete after owner ok | none |
| scripts/_canary_run.log, _canary_run_out.txt, root pytest_*.txt / *_exit.txt | ignored | C | generated output | no | ignored (output) | none |
| docs/archive/2026-07/AI_FIRSTIFY_REPORT_2026-07-18.md, docs/archive/2026-07/WORKTREE_RECONCILIATION_2026-07-18.md, docs/CONTEXT_HYGIENE_POLICY.md | untracked | **D** | this session | yes | track (Commit 2) | none |
| SESSION_HANDOFF.md | untracked | D | session handoff | yes | keep at root (referenced by continuation prompts); optionally move to docs/reports/ | none |
| docs/plans/2026-07-18-commercial-launch-closure.md | untracked | D/A | planning | yes | track with its workstream | low |
| root forensics_billing_dlq.txt, upi_flip_result.txt | ignored (root pattern) | D | raw capture | decision content already in SESSION_HANDOFF/CLAUDE.md | on-disk, reversible; convert to docs/evidence/*.md if tracking wanted | none |
| __pycache__, .venv, node_modules, .claude/worktrees/ | ignored | E | generated | no | leave ignored | none |

## `.gitignore` review (Phase 4 — every proposed rule)

| Rule (as first added) | Tracked matches? | Decision | Why |
|---|---|---|---|
| `scripts/_tmp_*` | 0 | **KEEP** | one-off by naming; matches existing `scripts/_mcp_*` / `scripts/_debug/` convention |
| `scripts/_canary_*` | 0 | **NARROWED → `_canary_*.log` / `_canary_*_out.txt` / `_canary_*.txt`** | blanket hid 8 reusable canary SCRIPTS; now only their OUTPUT is ignored, scripts stay visible/trackable |
| `*_exit.txt` | 0 | **NARROWED → `/*_exit.txt`** | root-scope so nested tracked files can't be shadowed |
| `pytest_*.txt` | 0 | **NARROWED → `/pytest_*.txt`** | root-scope |
| `*_result.txt` | 0 | **NARROWED → `/*_result.txt`** | root-scope |
| `forensics_*.txt` | 0 | **NARROWED → `/forensics_*.txt`** | root-scope |
| `*.bak` | 0 | **KEEP** | backups are never tracked; 0 tracked matches confirmed |
| `*.bak.*` | 0 | **KEEP** | same |
| (new) `artifacts/local/` | n/a | **ADD** | designated ignored runtime scratch dir (directory convention preferred over broad patterns) |

Verification: `git check-ignore scripts/_canary_place_call.py` → not ignored (rc=1); `scripts/_canary_run.log` → ignored (rc=0); `scripts/_tmp_poll_dep.bat` → ignored (rc=0); `git diff --check .gitignore` → clean.

## Secret-scan result
Redacted scan of the reusable-candidate scripts (canary tools + call helpers + add_pinterest_key.ps1) for `sk-`, `api_key`, `secret`, `password`, `bearer`, `PRIVATE KEY`, `+91` phone numbers, provider names → **NO HITS (PASS)**. Safe to track after human review. (Full authoritative gate: run `scripts/check_secrets.py` / `/verify` before committing.)

## Safe changes APPLIED this session (zero-collision)
1. `.gitignore` — narrowed (see table). 0 tracked-file collisions; no reusable tool hidden; no evidence deleted.
2. `docs/CONTEXT_HYGIENE_POLICY.md` — new policy doc (temp-artifact conventions).
3. `docs/archive/2026-07/WORKTREE_RECONCILIATION_2026-07-18.md` — this record.
4. `docs/archive/2026-07/AI_FIRSTIFY_REPORT_2026-07-18.md` — (prior turn) the audit report.

## Changes deliberately NOT applied
- No edit/commit/move/delete of the 17 modified tracked files (parallel WIP — owner's to commit).
- No deletion of the ~97 `_tmp_*` scripts (kept on disk; only ignored) — ownership/reuse not confirmed.
- No promotion of `_canary_*` scripts to `scripts/canary/` yet (needs human review of which are keep-worthy).
- No `git` history operations of any kind.

## Recommended commit sequence (small, reversible; owner executes)
1. **Context hygiene:** `.gitignore` + `docs/CONTEXT_HYGIENE_POLICY.md` (+ optionally this doc + the AI-firstify report).
2. **Parallel product work:** one commit per workstream above, by its owner — do not bundle.
3. **Reusable tooling:** reviewed + renamed canary/call scripts under `scripts/canary/` with header docs.
4. **New skill:** `.claude/skills/a2z-launch-enterprise-audit/` + its command.
5. **Evidence consolidation:** convert root `forensics_*.txt` / `upi_flip_result.txt` to `docs/evidence/*.md` if tracking is desired.

## Exact next action (needs repository owner / parallel agent)
Confirm the 17 modified tracked files belong to the parallel dashboard/marketing workstreams and commit them per-workstream (Commit set 2). Until then the tree stays intentionally dirty — do not `git checkout main` / `pull --ff-only` (that would collide with the uncommitted WIP).
