# Deployment Credential Hardening (2026-07-21)

> **STATUS (2026-07-21): COMPLETED — hardened path PRODUCTION-PROVEN.** This
> path was first exercised in production by deploy run `29834863683`, releasing
> `7ce4d97` (`7ce4d979120da42cca9348320aae36640a2fdb27`) from previous prod
> `0ff5d06` (rollback not used). The old GitHub Actions secrets `GHCR_PAT`,
> `VPS_USER`, `VPS_SSH_KEY` have since been retired; `VPS_HOST`, `VPS_DEPLOY_USER`,
> `VPS_SSH_KEY_DEPLOY` are retained. The emergency root key remains outside GitHub
> for operator recovery. The pre-completion status lines below (e.g. "Production
> remains `0ff5d06`") describe the state at the time this hardening PR was written
> and are preserved as historical record. See `PRODUCTION_DEPLOYMENT_RECORD_7ce4d97.md`.

Removes the two long-lived risks in the VPS deploy path proven during the
`0ff5d06` production deploy:

1. `GHCR_PAT` populated from a broad GitHub CLI/session token.
2. Shared `root` SSH access used directly by CI.

## New posture

| Concern | Before | After |
| --- | --- | --- |
| SSH identity | `root` + shared `~/.ssh/id_rsa` | dedicated `leadgen-deploy` user + dedicated `ed25519` key |
| Privilege | full root shell | one scoped sudo rule to a validated wrapper; **no docker group** |
| Registry auth | `GHCR_PAT` (broad token) | **none** — GHCR package is public, anonymous pull by exact SHA |
| Deploy surface | inline SSH script as root | root-owned `/usr/local/sbin/leadgen-deploy-release <40-hex-sha>` |

## Architecture

```
GitHub Actions
  -> dedicated ed25519 deploy key (secret VPS_SSH_KEY_DEPLOY)
  -> leadgen-deploy user (no docker group, no interactive pty)
  -> sudo (scoped, NOPASSWD, single command)
  -> root-owned wrapper  /usr/local/sbin/leadgen-deploy-release
  -> validated: exact 40-hex SHA, fixed repo/compose/dir, anonymous pull,
     celery profile up, hard-gated alembic, /health/ready gate, auto-rollback
```

Canonical wrapper source: `scripts/vps/leadgen-deploy-release`.

## VPS provisioning (already applied on the production host)

- `leadgen-deploy` user created, **not** in the `docker` group.
- `~leadgen-deploy/.ssh/authorized_keys`: the dedicated public key with
  `no-pty,no-port-forwarding,no-x11-forwarding,no-agent-forwarding`.
- Wrapper installed `root:root 0755` at `/usr/local/sbin/leadgen-deploy-release`.
- `/etc/sudoers.d/leadgen-deploy`:
  `leadgen-deploy ALL=(root) NOPASSWD: /usr/local/sbin/leadgen-deploy-release *`
  (validated with `visudo -cf`). The wrapper — not the sudo glob — is the real
  boundary: it rejects extra arguments and any non-`[0-9a-f]{40}` input.
- `/var/log/leadgen-deploy.log` for an audit trail.

## GitHub secrets

Added (new path): `VPS_DEPLOY_USER=leadgen-deploy`, `VPS_SSH_KEY_DEPLOY`.
Retained for rollback until the new path has a proven production run:
`VPS_HOST`, `VPS_USER` (root), `VPS_SSH_KEY` (id_rsa), `GHCR_PAT`.

## Registry authentication decision

The GHCR package `ghcr.io/sumitrevolt/leadgenrationaivoiceagent` is **public**;
anonymous manifest access for the exact deployed SHA returns HTTP 200 from the
VPS. The hardened path therefore removes the registry login step entirely
(Option A — no registry secret). If the package is ever made private, switch to
Option B: pass the workflow's ephemeral `${{ github.token }}` with
`permissions: { packages: read }` via stdin to `docker login` — still no
persistent PAT.

## Security tests (proven non-destructively)

Authenticating as `leadgen-deploy` with the dedicated key:

- `whoami` = `leadgen-deploy`; groups = `leadgen-deploy` only (no docker).
- `sudo -n -l` lists only the wrapper.
- direct `docker ps` denied; `sudo /bin/bash` denied; `sudo /bin/cat <compose>` denied.
- wrapper rejects (exit 2): `latest`, short SHA, `a;id` (metachar), uppercase SHA, extra argument.
- wrapper accepts a valid 40-hex SHA and, with `DRY_RUN=1`, stops before any change.

## Secret transition (do not skip steps)

1. New secrets added (`VPS_DEPLOY_USER`, `VPS_SSH_KEY_DEPLOY`). ✅
2. Old secrets retained as emergency rollback. ✅
3. Merge this PR after review. ⛔ not in this loop
4. Run one real production deploy through the new path (operator-gated). ⛔ not in this loop
5. Only after that succeeds: retire `GHCR_PAT`, remove the root deploy key from
   GitHub, keep the root key OFF GitHub for emergency recovery only.

## Not changed here

No product code, no application version change, no redeploy, no rollback.
Production remains `0ff5d06`. `DEPLOY_ENABLED` stays unset. `PR #67` untouched.

## Wrapper safety hardening (adversarial-review outcome)

The wrapper (`scripts/vps/leadgen-deploy-release`, installed byte-identically at
`/usr/local/sbin/leadgen-deploy-release`) additionally:

- **Single-flight lock**: `flock -n` on `/run/leadgen-deploy.lock`; a second
  invocation (manual or CI) while a deploy holds the lock exits `3` — GitHub
  workflow concurrency alone is insufficient, so the lock lives in the wrapper.
- **Environment hardening**: fixed `PATH`, and unsets caller-controlled
  `DOCKER_HOST`, `COMPOSE_FILE`, `COMPOSE_PROJECT_NAME`, `COMPOSE_PROFILES`,
  `DOCKER_CONFIG`, `BASH_ENV`, `ENV`, `PYTHONPATH`, `LD_PRELOAD`,
  `LD_LIBRARY_PATH`. sudo `env_reset` + `secure_path` already strip these; this
  is defense in depth (and covers direct root invocation).
- **Input contract**: exactly one arg; leading-dash rejected; length must be 40;
  lowercase-hex only. Every use of the validated SHA is quoted; no `eval`, no
  indirect execution. Fixed image repo / compose file / dir / celery profile /
  health endpoint. Rollback uses the captured immutable previous image, never a
  floating tag; DB path is upgrade-only (no blind downgrade).

Repo source and the installed executable are kept byte-identical
(`sha256 = 6aa336d5…`); CI must not merge a workflow whose wrapper source
differs from the installed file.

Note: `shellcheck` is not installed on the host or VPS; `bash -n` passes and the
runtime input/lock matrix is proven (all malicious inputs exit 2, concurrent
invocation exits 3).
