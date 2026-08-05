# CLAUDE_HANDOFF_RECOVERED — Cursor takeover 2026-08-01T15:35Z

Evidence revalidated from git / GitHub / docker / files — Claude chat claims treated as leads only.

## Exact branch and full SHA (at takeover)

| Item | Value | Evidence |
|---|---|---|
| Owned worktree | `.claude/worktrees/hyperframes-video-rendering-d233cb` | `git worktree list` |
| Branch | `claude/hyperframes-video-rendering-d233cb` | clean, tracks origin |
| Local HEAD | `844dc992256705722f5d13b48be9b9cff55487f2` | `git rev-parse HEAD` |
| Remote branch | `844dc992256705722f5d13b48be9b9cff55487f2` | equals local |
| PR #204 head | `844dc992256705722f5d13b48be9b9cff55487f2` | `gh pr view 204` |
| `origin/main` | `b6ed6f8df2e3af6a6e8d1347313c976de1009d95` | after `git fetch` |
| Divergence | PR behind main by **1** (`b6ed6f8` docs #209); ahead by 15 PR commits | `git rev-list --left-right --count` |
| Frozen proof SHA (INVALIDATED) | `527851008fc05ba0ac5ff02349fb3b0c52177e8d` | PR body; 5 commits after it |
| Main checkout | `b6ed6f8` clean — **not touched** | primary worktree |
| Launch worktree | `claude/leadgen-agent-launch-ready-198969` @ `28c38c3` | PR #210 draft; **2 uncommitted data files preserved** |

## Completed work (revalidated)

- HyperFrames additive provider + 3 templates + enterprise QA + flags default OFF — CODE on PR #204.
- ADR-153 in `memory/decisions.md` — present.
- Frozen-head exact image chain at `5278510` — digests still local: app `sha256:15846575f6df…`, video `sha256:ec3fa7f3c3df…` (INVALIDATED by later commits).
- Images **already rebuilt** at current head `844dc99`: app `sha256:2d9a0c6937c9…`, video `sha256:90f30834f315…` (created ~15:10Z / 15:19Z) — **render/ffprobe/3-template/clean-room proof at this head NOT yet recorded as passed**.
- Blocking CI on PR #204 head `844dc99`: Lint/secrets, prod_check+pytest, harness-redis, tests, Trivy repo, GitGuardian = SUCCESS (2026-08-01T15:05–15:20Z).
- Launch-commander packet `docs/LAUNCH_READINESS_2026-08-01.md` on PR #210 — stale on PR #204 head (said `5278510` DIRTY); lanes §5–7 unfinished.

## Remaining work (first incomplete = this)

1. **PR #204 exact-head proof at a tip that includes latest `origin/main`** — merge `b6ed6f8`, rebuild app→video from full SHA (no `latest`), ancestry+digests, 3-template real provider render (`--network none`), ffprobe/hashes/frames, clean-room approval suites, security suite, record evidence. Jiya real-photo canary stays blocked.
2. Close proven P0 security / tenant / provider / CI / Docker / approval gaps.
3. Agent-OS 31-agent readiness matrix (existing runtime — no second OS).
4. Automation safety (queues/retries/DLQ/budgets/leases/heartbeats/kill switches/Owner OS) with protected defaults.
5. Browser journeys (public/auth/admin/approval/video).
6. One exact RC + launch/rollback packet.

## Active blockers

- Exact-head **content proof incomplete** after merge commit `844dc99` (images exist; render/clean-room evidence missing for that SHA).
- Tip must absorb `origin/main` `b6ed6f8` before calling branch current — that merge **invalidates** any partial `844dc99` image proof → full rebuild required.
- Owner-only: Jiya consented photo assets; Gemini key in VPS bash_history (P1 rotate); WAHA FAILED / Estique password / merge+deploy decisions.
- Protected prod defaults must stay off for customer-impacting sends (mission list); live prod may already have owner-armed autopilot — **this session will not change prod flags**.

## Files Cursor will own (sole writer)

- Entire tree under worktree `hyperframes-video-rendering-d233cb` on branch `claude/hyperframes-video-rendering-d233cb` (PR #204).
- Evidence under `docs/context/` in that worktree for takeover + exact-head proof.
- Downstream: only after #204 proof — launch packet paths on a **separate** Cursor worktree branched from then-current main/PR tip; will not edit launch worktree's dirty `data/*` files.

## Overlap confirmation

- Main checkout: clean, no edits planned.
- Launch worktree: read-only for Cursor; uncommitted `data/delivery_ledger/jiya-makeover.jsonl` + `data/marketing_clients.jsonl` **preserved** (no reset/prune/overwrite).
- PR #208 ci-probe: draft, do-not-merge; leave alone unless needed for CI escape hatch.
- No other writer on PR #204 branch (Claude session exhausted; HF worktree porcelain empty).

## Next action (immediate)

Merge `origin/main` → rebuild exact-head images → hermetic 3-template render + clean-room approval + HyperFrames security pytest → push → update PR #204 body with new frozen SHA.
