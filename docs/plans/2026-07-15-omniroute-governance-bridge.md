# OmniRoute governed engineering bridge

## Goal and approach

Keep Claude/ChatGPT as the only engineering governors while OmniRoute remains an
untrusted, text-only inference sidecar. Reuse the existing context-packet,
OmniRoute client, DevTask runner, and local launchers; remove provider-facing
worktree lanes, enforce a bounded fail-closed packet contract, and keep every
output review-only.

## Risk and rollback

**High-risk** because this touches an external-LLM boundary and the dormant
engineering automation runner. The feature stays default-OFF and needs the
existing `DEV_ORCHESTRATOR`, `DEV_WORKER_ENABLED`, and `OMNIROUTE_ENABLED` gates.
Rollback: set those flags OFF; revert this isolated branch if needed. No DB
migration, production route, customer path, commit, push, or deploy is included.

Security review: external text is untrusted data, never control flow. Secrets,
PII, unsafe paths, oversized packets, and non-governor worktree ownership fail
closed. Provider output cannot run tools, apply patches, commit, push, or deploy.

## File ownership map

| Owner | Files | Responsibility |
| --- | --- | --- |
| Main governor | `tests/test_omniroute_governance.py` | Contract-first security and launcher tests |
| Main governor | `app/dev_control/context_packets.py` | Bounded allowlisted redacted packet |
| Main governor | `app/dev_control/governed_omniroute.py` | Text-only proposal bridge |
| Main governor | `app/dev_control/runner.py` | Use governed packet/bridge, retain review-only artifact |
| Main governor | `app/platform/omniroute_client.py` | Route through verified safe/quality combos |
| Main governor | `scripts/omniroute-worktrees.sh`, `scripts/omniroute-tmux.sh`, `scripts/_leadgen_dev_up.sh`, `scripts/start-leadgen-dev.ps1` | Gateway-only launcher; no provider worktree panes |
| Main governor | `docs/OMNIROUTE_ENGINEERING_RUNBOOK.md`, `docs/omniroute/ARCHITECTURE.md`, `docs/omniroute/PRIVACY_AND_SECURITY.md` | Operator boundary and rollback |

## Tasks

1. RED: add tests proving packets reject absolute/traversal/sensitive paths,
   more than eight excerpts, oversize packets even with justification, and carry
   fixed no-tool/untrusted-data rules. Prove the current implementation fails.
2. RED: add bridge tests proving all three flags are required, only the sanitized
   packet text reaches the transport, and returned text is always marked
   `applied=False`/`review_required=True`.
3. RED: add launcher contracts proving no research/implement/review shell lanes
   or automatic OmniRoute worktrees remain; prove current scripts fail.
4. GREEN: minimally harden `context_packets.py`, add the governed bridge, wire
   `runner.py`, and update the route models to `free-coding-safe` then
   `free-coding-quality`.
5. GREEN: convert local launchers to one gateway window and make the legacy
   OmniRoute worktree script refuse with the governor-owned workflow message.
6. Verify: targeted tests, relevant existing regressions, `prod_check.py`,
   `check_secrets.py`, shell syntax, PowerShell parse, and `git diff --check`.

## Wiring

No new public route or scheduler entry. Existing admin auth and flags remain the
only entry. The runner may create only a review proposal artifact; it cannot
apply it. Worktrees are created and owned outside OmniRoute by Claude/ChatGPT;
the local OmniRoute tmux session contains only the gateway process.

## Self-review checklist

- Every external prompt is a packet built by the bounded sanitizer.
- No raw repo read or worktree path is available to OmniRoute.
- No provider output can trigger a side effect.
- OFF flags leave current application behavior unchanged.
- Existing direct production LLM chain remains untouched.
