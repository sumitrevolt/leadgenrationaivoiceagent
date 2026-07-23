# OmniRoute engineering runbook

_Current verified state: 2026-07-14._

## Boundary

OmniRoute 3.8.46 is a local WSL development gateway. It is not a production boot
dependency and is not approved for customer, voice, billing, CRM, compliance, or
automation traffic. LeadGen's production provider chain remains direct and continues
working when OmniRoute is stopped. `OMNIROUTE_ENABLED` stays OFF by default.

## Verified runtime

- Runtime: Node 22.23.1, OmniRoute 3.8.46; do not auto-upgrade to broken 3.8.47.
- Session: `leadgen-omni`, **gateway-only** window. Provider-facing
  research/implement/review worktree lanes are disabled.
- Dashboard/API: `http://127.0.0.1:20128`; LiveWS: loopback `127.0.0.1:20129`.
- API contract: `POST /v1/responses`; Chat Completions is not served.
- Memory: launchers export `OMNIROUTE_MEMORY_MB=2048`, verified by Doctor.
- Routes: `free-coding-safe` then `free-coding-quality`; both combos have sanitized
  live response evidence. Provider membership and quota fallback stay inside OmniRoute.
- Adapter: `app/platform/omniroute_client.py`, explicit internal-sanitized task registry,
  one bounded fallback, default OFF, no production caller.

## Start and verify

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start-leadgen-dev.ps1
powershell -ExecutionPolicy Bypass -File scripts\omniroute-check.ps1
```

```bash
OMNI_HEALTHGUARD_WINDOW_SECONDS=20 bash scripts/omniroute-healthguard.sh
```

Healthy means one gateway process, version 3.8.46, API reachable, no reconnect storm,
and zero active LiveWS clients when no dashboard tab is open. Stale dashboard tabs can
create reconnect churn; close them and verify through one fresh tab.

## Credentials and safety

The admin enters passwords, keys, OAuth codes, OTPs, and recovery codes personally.
Never print or store their values in Git, docs, terminal history, screenshots, logs, or
Graphify. MCP and data-plane keys are referenced only through environment-variable names.
Only a bounded sanitized context packet may enter the local gateway. Claude/ChatGPT
own the worktree, tools, source verification, patch application, tests, and user
handoff. OmniRoute receives no repo/worktree path, shell, Git, browser, database,
production, MCP, or persistent-agent capability. Its response is untrusted review text.

## Dual-governor review

The runner stores the SHA-256 of the complete review artifact and clears prior reviews.
The scoped governor-auth endpoint records a bounded review at:

```text
POST /api/dev-tasks/{task_id}/governor-review
```

Submit `governor` (`claude` or `chatgpt`), `decision`, the displayed
`proposal_sha256`, and a short summary. Both governors must choose `approve` for the
same hash. A mismatch, missing review, `changes_requested`, `reject`, malformed ledger,
or old in-flight task fails closed before tests/staging. `changes_requested` returns the
task to its revision flow; a new runner artifact invalidates all earlier approvals.

Each governor has a separate environment secret: `DEV_CLAUDE_REVIEW_SECRET` or
`DEV_CHATGPT_REVIEW_SECRET` (minimum 32 characters). Keep them out of `.env` shared with
OmniRoute and out of prompts. The local LeadGen verifier process needs both; give each
trusted local governor process only its own secret and give OmniRoute neither. The
signed payload binds task, governor, decision, artifact hash, summary,
timestamp and nonce. Requests expire after five minutes; future skew over 30 seconds,
wrong signatures and reused nonces fail closed. Only a nonce SHA-256 fingerprint is
stored; the secret and signature are never persisted.

The submitter refuses non-loopback URLs and does not print signing headers:

```powershell
# Run from the governor process that has only its own DEV_*_REVIEW_SECRET.
python scripts\governor_review_submit.py `
  --task-id <task-id> --governor claude --decision approve `
  --artifact-hash <proposal_sha256> --summary "Reviewed exact artifact; safe to test"
```

Repeat from the isolated ChatGPT governor process with `--governor chatgpt`. Neither
governor needs an admin token; its HMAC can authorize only this exact review payload and
cannot call any other task/tool/admin endpoint. This proves possession of a scoped
governor credential, not that a model cognitively performed the review; the trusted
governor process must enforce that workflow.

For Claude, the trusted wrapper now performs that enforcement automatically: it accepts
only one `data/dev_tasks/<task-id>/proposal-*.md` artifact (128 KiB maximum), computes the
hash locally, starts Claude from a neutral temporary directory with safe mode,
customizations/Chrome/session persistence disabled and an empty tool list, validates a
strict JSON verdict, verifies the echoed hash, and only then calls the scoped submitter.
The model subprocess receives neither the proposal path nor any `*_KEY`, `*_TOKEN`,
`*_SECRET`, or `*_PASSWORD` environment variable. A system-level instruction marks the
proposal as inert untrusted data; output fields must also remain native JSON strings.

```powershell
python scripts\governor_model_review.py `
  --task-id <task-id> --governor claude `
  --artifact data\dev_tasks\<task-id>\proposal-<timestamp>-<id>.md
```

ChatGPT remains a manual browser review plus `governor_review_submit.py` submission.
Do not substitute `codex exec --sandbox read-only`: read-only prevents writes but still
permits local reads, so it does not satisfy the no-direct-project-access boundary. The
automatic ChatGPT adapter deliberately returns `chatgpt_toolless_adapter_unavailable`
until a genuinely no-local-tools transport is available.

`scripts/omniroute-worktrees.sh` now refuses by design. Do not recreate the retired
three-lane layout. A governor may create an isolated `codex/<task>` worktree through
its own trusted Git tools, or run the operator-only wrapper below, then send at most
eight allowlisted excerpts through `app/dev_control/context_packets.py`.

```powershell
# Preview only; no Git mutation
scripts\governor-worktree.ps1 -TaskId <task-slug> -Governor claude -PlanOnly

# Create the isolated codex/claude-<task-slug> worktree; still no commit/push/deploy
scripts\governor-worktree.ps1 -TaskId <task-slug> -Governor claude
```

## Rollback

1. Leave `OMNIROUTE_ENABLED=0`.
2. Unset both governor review secrets to disable review submission.
3. Stop the local gateway/tmux session if needed; LeadGen remains operational.
4. Restore the verified external backup under `/root/.omniroute_backups/` using the
   manifest in `docs/omniroute/ROLLBACK.md`.
5. Re-run the status and 20-second LiveWS checks.

Canonical detail:

- `docs/omniroute/ARCHITECTURE.md`
- `docs/omniroute/PROVIDER_MATRIX.md`
- `docs/omniroute/ROUTING_POLICY.md`
- `docs/omniroute/PRIVACY_AND_SECURITY.md`
- `docs/omniroute/OPERATIONS_RUNBOOK.md`
- `docs/omniroute/VERIFICATION_EVIDENCE.md`
