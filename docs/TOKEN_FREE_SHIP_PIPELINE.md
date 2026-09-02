# Token-Free Ship Pipeline (commit → merge → deploy without Claude tokens)

The mechanical parts of shipping — running CI, merging green PRs, building the
image, deploying to the VPS, health-gating, rolling back — already run **on
GitHub's runners and the VPS**, not inside a Claude chat. Once set up, an agent's
job ends at "open a PR"; GitHub does the rest. That is where your tokens stop
being spent.

## The flow

1. **Agent opens a PR** (this is the only Claude-token step).
2. **CI runs automatically** — `deploy-vps.yml`'s `gate` job (import smoke +
   `prod_check` + ruff + blocking billing/pricing contract tests + network-free
   pytest). Runs on GitHub, free of chat tokens.
3. **Auto-merge** — apply the `auto-merge` label. `auto-merge.yml` flips GitHub's
   native auto-merge; GitHub merges the PR the instant required checks pass. No
   polling, no `gh` driven from chat.
4. **Auto-deploy** — merge to `main` triggers `deploy-vps.yml` → build image to
   GHCR (`:latest` + `:<sha>`) → hardened SSH deploy via the root-owned
   `leadgen-deploy-release` wrapper → alembic hard-gate → `/health/ready` gate →
   **auto-rollback** on migration or health failure. Gated by repo variable
   `DEPLOY_ENABLED`.

Parallel-agent work is handled naturally: each PR merges itself when green;
GitHub serialises merges to `main`; `concurrency: deploy-vps` serialises deploys.

CI lanes (2026-08-15, DeepSeek Harness layout steal — not a DSH runtime arm):

- PR required checks stay the same three names. Pytest runs as **4 parallel
  shards**; `prod_check + pytest` is an aggregator so the ruleset does not break.
- After merge, `ci.yml` does **not** re-run the full suite on `push` to `main`.
  `deploy-vps` `gate` is the post-merge floor. Set repo variable
  `DEPLOY_RETEST=true` only if you want the 4 shards again before GHCR build.
- `tests.yml` no longer runs on pull_request (duplicate of ci.yml).
- Trivy **image** scan still fail-closed, but a PR that does not touch
  `Dockerfile.lock` / lockfiles skips the 14-minute image rebuild. Main push
  still scans.

Do **not** rename `Lint + syntax + secrets`, `prod_check + pytest`, or
`harness real-redis integration`.

## One-time setup (owner, ~3 minutes)

1. **Settings → General →** enable **"Allow auto-merge"**.
2. **Settings → Branches → add rule for `main`:** require pull request, and
   require the status check **`Gate (import + prod_check + lint)`** (add the CI
   test job too). This is what makes auto-merge safe — nothing merges red.
3. **Settings → Secrets and variables → Actions →** confirm secrets
   `VPS_HOST`, `VPS_DEPLOY_USER`, `VPS_SSH_KEY_DEPLOY` exist (hardened deploy id).
4. When ready to let merges deploy: set repo **variable** `DEPLOY_ENABLED=true`.
   Leaving it unset/false = merges run CI only (no deploy) — a safe default.

## The single toggle you control

- `DEPLOY_ENABLED=false` → PRs merge (if labeled) and CI runs, **but nothing
  deploys**. Use while stabilising.
- `DEPLOY_ENABLED=true` → merges to `main` auto-deploy to production with
  auto-rollback. Flip it on only after the F-1 sequence (reconcile → verify →
  permanent fix → regression) is green.

## Safety invariants (unchanged)

- Owner decides *which* PRs auto-merge (the `auto-merge` label).
- Nothing merges unless required checks pass (branch protection).
- Production deploy stays behind `DEPLOY_ENABLED`; the deploy wrapper
  auto-rolls-back on migration/health failure.
- Calling stays HARD_OFF; no workflow changes voice/telecom flags.

## Trigger a deploy on demand (still token-free)

`gh workflow run deploy-vps.yml --ref main` (one command) — or just push/merge to
`main`. The run executes entirely on GitHub + the VPS.
