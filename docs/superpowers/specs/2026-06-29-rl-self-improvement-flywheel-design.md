# RL Self-Improvement Flywheel — Phase 0 Design

**Date:** 2026-06-29
**Status:** Design (awaiting user review → writing-plans)
**Scope decided:** Phase 0 only (reward pipes + dev-time Claude reward-capture + read-only observability). Phases 1–2 documented but NOT built — they auto-graduate when data accrues.
**Author:** Claude (Principal RL/Architecture lens)

---

## 1. Problem & Goal

User ask: "Add reinforcement learning to the architecture (for Claude and for the project) so it self-improves."

**Honest finding (evidence-gated).** The platform already has ~80% of RL-shaped scaffolding (epsilon-greedy `skill_library`, `eval_gate` baseline regression, `trajectory` replay, 16-arm `channel_experiments` bandit, `compute_outcome_value` reward, Reflexion/AgentVerse coordinator). It is mostly **dormant** (flags OFF) and **shallow** (fixed ε=0.3, reward not consolidated, trajectory only feeds reflection).

**The blocker is data, not architecture.** Local reward/trajectory fuel counted 2026-06-29:

| File | Rows |
|---|---|
| `data/skill_uses.jsonl` | MISSING |
| `data/call_qualifications.jsonl` | MISSING (voice outcomes = 0) |
| `data/lead_usage.jsonl` | MISSING (revenue = 0) |
| `data/call_transcripts/` | 0 files (no real calls; Vobiz/DLT blocked) |
| `data/agent_trajectories.jsonl` | 1 |
| `data/eval_history.jsonl` | 16 |
| `data/channel_outcomes.jsonl` | 42 |
| `data/self_improve_runs.jsonl` | MISSING (loop never ran) |

This is a **cold start**. Contextual bandits, Thompson sampling, and offline policy evaluation are data-hungry; building them now = engine with no fuel. Therefore Phase 0 builds the **reward-capture flywheel** so data accumulates correctly, keeps the existing safe ε-greedy untouched, and defers the policy engine behind a sample-count graduation gate.

**Goal of Phase 0:** Stand up the data + observability spine of a closed reward loop, with **zero behavior change** (logging-only, flag-gated, fail-open), so that (a) every existing outcome becomes a versioned scalar reward, (b) Claude's own dev-session outcomes become a reward signal feeding existing memory/skill machinery, and (c) an admin can see reward trends + "graduation status."

**Non-goals (Phase 0):** No PPO/gradient RL. No online policy changes. No Thompson/contextual/OPE (Phase 1–2). No new model training. No change to any decision logic in voice/outreach/funnel paths.

---

## 2. Design Principles (project-native)

- **Additive only** — new `app/agents/rl/` package + one hook + one read-only API + one UI tab. No rewrite of `skill_library`, `eval_gate`, `channel_experiments`, `self_improve`.
- **Flag-gated, default OFF** — master `RL_ENGINE=1` (registered in `app/api/automation_flags.py` + `.env.example`). Unset = fully inert.
- **Fail-open / never-raise** — reward emission is fire-and-forget at existing outcome points; any error is swallowed (matches `customer_webhooks.fire_emit`, `eval_gate` INERT-when-unset patterns).
- **eval_gate stays the gate, reward stays the optimizer** — two distinct mechanisms. `eval_gate` answers "don't ship worse"; the reward log answers "find better." Phase 0 does not couple them beyond writing both logs.
- **Idempotent** — reward rows keyed on a `ref` (call_sid / lead_ref / task_id); duplicate refs within a window are dropped (mirror `lead_usage._ref_already_recorded`).
- **Free-stack, pure-python** — no new dependencies. Beta posteriors / counts computed from existing JSONL.

---

## 3. Architecture

```
            ┌──────────────── SHARED SPINE (Phase 0) ────────────────┐
            │  app/agents/rl/reward.py  →  data/rl_rewards.jsonl     │
            │     (versioned scalar reward per outcome event)        │
            │  app/api/rl.py            →  read-only admin endpoints │
            │  frontend/automation.html →  "RL Flywheel" tab         │
            └───────────────┬────────────────────────┬───────────────┘
                            │                        │
         LOOP A (runtime, data-gated)        LOOP B (Claude dev-time)
         emit reward at existing             .claude/hooks/reward_capture.py
         outcome hooks (logging only)        → data/claude_feedback.jsonl
         NO policy change in Phase 0         → consumed by /learn + /retro
```

### 3.1 Component: `app/agents/rl/reward.py` (NEW)

Single source of truth for "what is a good outcome." Pure functions + one append-only writer.

**Reward functions** (each returns a float, documented range, with a `reward_version` constant so reweighting is traceable):

- `voice_reward(call: dict) -> float` — consolidates `conversation_quality` (0–100→0–1), terminal `outcome` enum (appointment/qualified high, dnd/not_interested low), `qa_checks` violation penalties, latency penalty. Range `[0,1]`.
- `outreach_reward(event: dict) -> float` — reply intent (interested/booked high, unsubscribe negative), opt-out penalty. Range `[-1,1]`.
- `funnel_reward(run: dict) -> float` — thin wrapper over existing `self_improve.compute_outcome_value` (reuse, do not reimplement).
- `dev_reward(record: dict) -> float` — for Loop B: weighted blend of verify pass, review-finding count (inverse), tests pass, user_correction (strong negative), deploy health. Range `[-1,1]`.

**Writer:**

- `record_reward(domain: str, arm: str, reward: float, *, ref: str, context: dict | None = None) -> None`
  - Appends one line to `data/rl_rewards.jsonl`:
    `{ "ts", "domain", "arm", "reward", "reward_version", "ref", "context": {...} }`
  - `domain` ∈ {voice, outreach, funnel, dev}. `arm` = the decision lever (niche/channel/action/skill). `context` = cheap state features for future contextual bandit (niche, funnel_stage, lead_band, hour_bucket).
  - Idempotent on `ref` (tail-scan last N, mirror `lead_usage`). Auto-trim to last ~10k rows (mirror `skill_library`).
  - Never raises; INERT if `RL_ENGINE` unset.

**Readers (for API/observability + future policy):**

- `recent(domain: str | None, n: int) -> list[dict]`
- `arm_stats(domain: str) -> dict` — per-arm count, mean reward, Beta(α,β) from successes/failures (success = reward ≥ `RL_SUCCESS_THRESHOLD`, default 0.5), Laplace mean.
- `graduation_status() -> dict` — per-domain total samples, and `samples_until_graduation` against `RL_GRADUATION_N` (default 200). This is the "is there enough fuel yet" readout that Phase 1 will gate on.

### 3.2 Loop A wiring — emit reward at EXISTING outcome points (logging only)

Additive one-liners (guarded by `RL_ENGINE`) at the points the audit already identified. **No decision logic changes.**

- **Voice:** in `app/telephony/post_call_hooks.py` after `auto_qualify_and_downstream()` / `emit_call_report()` → `reward.record_reward("voice", niche, reward.voice_reward(call), ref=call_id, context={...})`.
- **Outreach:** in `app/marketing/channel_experiments.record_outcome()` and/or `app/platform/reply_agent.py` after intent classification → `reward.record_reward("outreach", channel, reward.outreach_reward(event), ref=...)`.
- **Funnel/self-improve:** in `app/agents/self_improve.py run_once()` where `outcome_value` is already computed → also `reward.record_reward("funnel", action, outcome_value, ref=run_id)`.

Each call sits inside the existing try/except (or its own `try: ... except Exception: pass`). If `RL_ENGINE` is unset, `record_reward` returns immediately.

**Phase 0 explicitly does NOT touch** `skill_library.pick_action()` or `channel_experiments.pick_channels()` selection logic. The bandit keeps running exactly as today.

### 3.3 Loop B wiring — Claude dev-time reward capture (NEW, additive)

- **New hook `.claude/hooks/reward_capture.py`** registered as a **Stop** hook in `.claude/settings.json` (alongside existing PreToolUse hooks). On session stop it reads cheap signals available to it (last verify/test result if a marker file was written by `/verify`, presence of a deploy health line, etc.) and appends a structured record to `data/claude_feedback.jsonl`:
  `{ "ts", "task", "verify_pass", "review_findings", "tests_pass", "user_correction", "deploy_health", "reward" }` where `reward = reward.dev_reward(record)`.
  - Fail-open (`|| true`, internal try/except, exit 0). Never blocks the session.
  - Best-effort signal capture: Phase 0 captures what is cheaply available; richer signals can be added incrementally. A `user_correction` flag can also be set by the `/learn` command when the user flags a mistake.
- **Consumption (no new tier):** extend the existing `/learn` and `/retro` commands to read `data/claude_feedback.jsonl` — promote high-`dev_reward` patterns into `memory/` (feedback type) + skill snippets, and propose guardrails (skill_reminder / guard entries) for low-reward anti-patterns. This reuses the machinery that already exists; it does NOT add a competing dashboard.

### 3.4 Component: `app/api/rl.py` (NEW, read-only, admin-gated)

Mirror `app/api/eval_gate.py` exactly (router prefix `/api/rl`, `require_admin`, `require_super_admin` for any reset):

- `GET /api/rl/summary` → `reward.graduation_status()` + per-domain row counts + reward_version.
- `GET /api/rl/arms?domain=voice` → `reward.arm_stats(domain)` (count, mean, Beta α/β, Laplace) for sparkline/trend.
- `GET /api/rl/recent?domain=&n=` → recent reward rows.
- `GET /api/rl/dev` → recent `claude_feedback.jsonl` rollup (Loop B visibility).
- (optional) `POST /api/rl/reset` super-admin only — archive/clear a domain's reward log.

Register router in `app/main.py` (additive include; run `duplicate-route-guard` grep first — prefix `/api/rl` must be unique).

### 3.5 Component: `frontend/automation.html` — "RL Flywheel" tab (NEW)

One new tab in Mission Control: graduation status bars per domain (samples vs `RL_GRADUATION_N`), per-arm mean-reward table, reward-trend sparkline, and Loop B dev-reward summary. Pure read from the new endpoints. Follows existing tab pattern in `automation.html`.

---

## 4. Data Flow

1. An outcome happens (call completes / reply classified / self-improve action finishes / Claude session stops).
2. The existing code path, if `RL_ENGINE=1`, fires `reward.record_reward(...)` (Loop A) or the Stop hook writes `claude_feedback.jsonl` (Loop B). Both fail-open.
3. `data/rl_rewards.jsonl` and `data/claude_feedback.jsonl` accumulate, idempotent + auto-trimmed.
4. Admin views trends + graduation status via `/api/rl/*` and the automation tab.
5. `/learn` + `/retro` consume `claude_feedback.jsonl` to reinforce Claude's memory/skills.
6. **Future (Phase 1, auto):** when `graduation_status()` shows a domain ≥ `RL_GRADUATION_N`, `policy.py` switches that domain's arm from fixed ε-greedy to Thompson sampling. Phase 2 adds context conditioning + OPE-gated promotion. Neither is built now.

---

## 5. Error Handling & Safety

- Every emission path wrapped so an exception cannot break a call, an email, a loop tick, or a Claude session.
- `RL_ENGINE` unset ⇒ `record_reward` and the Stop hook are no-ops (zero behavior change — verifiable by diffing reward-log row counts before/after with flag off).
- Idempotency on `ref` prevents double-counting (retries, webhook redelivery).
- Auto-trim bounds disk (~10k rows/file).
- No secrets, no network, no LLM in the hot path of reward emission (LLM only optionally in `/learn` consumption, off the hot path).
- Rollback: unset `RL_ENGINE`; delete the two JSONL files if desired. No schema migration, no container rebuild required for data-only paths.

---

## 6. Testing

- `tests/test_rl_reward.py` — pure-function tests for `voice_reward` / `outreach_reward` / `dev_reward` (boundary inputs, monotonicity: better outcome ⇒ higher reward), idempotency on `ref`, INERT-when-flag-off, auto-trim, `graduation_status` math.
- One failure-path test: `record_reward` with malformed input does not raise.
- `app/api/rl.py` smoke: endpoints return 401/403 unauthenticated (wired + admin-gated, not 404).
- `prod_check.py` green (route registration, no duplicate `/api/rl` prefix, frontend onclick/fetch wired).

---

## 7. Flags & Env

| Flag | Default | Effect |
|---|---|---|
| `RL_ENGINE` | OFF | Master switch. Unset = no reward emission, no hook write, endpoints return empty. |
| `RL_SUCCESS_THRESHOLD` | 0.5 | reward ≥ threshold counts as a "success" for Beta/Laplace stats. |
| `RL_GRADUATION_N` | 200 | per-domain samples before Phase-1 policy graduation (future). |

Registered in `app/api/automation_flags.py` (AUTOMATION_FLAGS), surfaced at `GET /api/growth/infra/flags`, documented in `.env.example`.

---

## 8. Phase 1–2 (documented, NOT built now)

- **Phase 1 (auto-graduate at `RL_GRADUATION_N`):** `app/agents/rl/policy.py` wraps `skill_library.pick_action` + `channel_experiments.pick_channels`; per-arm switch fixed ε-greedy → Thompson sampling (Beta posteriors from `rl_rewards.jsonl`) + decaying ε. Inert until a domain has enough samples.
- **Phase 2:** context-conditioned arm selection (niche/funnel-stage/lead-band/hour) + `ope.py` offline policy evaluation (replay logged rewards to score a candidate policy before promotion, gated by `eval_gate`) + optional fine-tune dataset export (reuse `trajectory.export_dataset`).

These are deferred precisely because the cold-start data does not yet justify them; the Phase 0 spine is what makes them trivially activatable later.

---

## 9. GTM Tradeoff (eyes-open, one line)

The project's own internal council has repeatedly concluded "stop building features → focus GTM" (platform feature-complete, infra saturated, real lever = GTM). An RL subsystem is more feature-build. Phase 0 is the deliberately minimal, cheap, compounding version (data pipes only) chosen so this does not compete with GTM; the heavier engine stays deferred until real customer/call data exists.

---

## 10. Files Touched (Phase 0)

**New:** `app/agents/rl/__init__.py`, `app/agents/rl/reward.py`, `app/api/rl.py`, `.claude/hooks/reward_capture.py`, `tests/test_rl_reward.py`, `tests/test_rl_dev_hook.py`, this spec.
**Edited (additive, guarded):** `app/telephony/post_call_hooks.py`, `app/marketing/channel_experiments.py`, `app/agents/self_improve.py`, `app/main.py` (router include), `app/api/automation_flags.py`, `.env.example`, `.claude/settings.json` (Stop hook — **gitignored, machine-local only**), `frontend/automation.html` (one tab), `.claude/commands/verify.md` (marker), `.claude/commands/learn.md` + `.claude/skills/retro/SKILL.md` (consume dev reward log).

---

## 11. Known limitations / before flipping `RL_ENGINE=1` (advisor review)

These are intentionally NOT fixed in Phase 0 (everything is inert while `RL_ENGINE=0`). Address before activation:

1. **Voice reward needs TWO flags.** The voice emit lives inside `auto_qualify_and_downstream`, which early-returns when `AUTO_QUALIFY_CALLS` is off (`post_call_hooks.py`). So the `voice` domain only fills when BOTH `RL_ENGINE=1` AND `AUTO_QUALIFY_CALLS=1`. Defensible (that's where the qualification dict `q` is born) but must be known — otherwise the voice domain looks mysteriously empty.
2. **Loop B marker is stale-prone.** The Stop hook attaches whatever `data/.claude_last_verify.json` last held to *every* session end, even sessions that never ran `/verify` → misattributed / all-`None` dev rows (dev_reward ≈ 0 noise). Fix before trusting dev-reward data: have the hook ignore a marker older than the session (timestamp check) or clear it after read.
3. **Phase 0 makes nothing self-improve yet.** It is data-intake only. Self-improvement (policy change) activates at Phase 1, per-domain, when `graduation_status` ≥ `RL_GRADUATION_N`. The accurate status line is: *"flywheel data-intake is live and inert; self-improvement activates when data graduates."*
4. **Activation regression gate.** Before any `RL_ENGINE=1` on prod, re-run the edited-module suites: `pytest tests/ -k "channel_experiment or self_improve or post_call or telephony"` (59 green as of 2026-06-29).
