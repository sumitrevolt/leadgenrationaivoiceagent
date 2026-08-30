# WSL REMOVAL — 2026-08-26 (OmniRoute/dev lane → Docker)

**Question:** Remove the WSL dependency from the LeadGen local dev lane by moving the OmniRoute gateway (+ optional Redis broker) to Docker, and make the Hermes Desktop app bring the gateway up on open.

**Verdict:** WSL is **not** required for the core product / revenue / deploy lane (unchanged from `docs/evidence/WSL_DEPENDENCY_20260812.md`). This change removes WSL from the **optional OmniRoute + dev-Redis** lane by running both as Docker containers, and adds a Hermes Desktop launch wrapper that ensures the gateway is up when the app opens.

---

## 1. What changed

| Component | Before (WSL) | After (Docker) |
|---|---|---|
| OmniRoute gateway runtime | WSL Ubuntu-24.04 + tmux + nvm Node 22 | `leadgen_omniroute` container (Node 22, `omniroute@3.8.46`) |
| OmniRoute config/OAuth | WSL `/root/.omniroute/` | named volume `omniroute_data` → `/root/.omniroute` |
| Redis broker (dev) | WSL `redis-server` | `leadgen_redis` container (`redis:7-alpine`, loopback 6379) |
| Gateway supervision | tmux session `leadgen-omni` | `docker compose up -d --build` (`restart: unless-stopped`) |
| Gateway health check | `wsl.exe -d Ubuntu-24.04 -- ... omniroute --version` | container state + `GET /v1/models` (HTTP readiness) |
| Hermes Desktop launch | — | `scripts/start-hermes-omniroute.ps1` → ensures gateway up, then launches Hermes |

**New Docker assets:**
- `deploy/compose/Dockerfile.omniroute` — `node:22-slim`, `npm i -g omniroute@3.8.46` (pinned; 3.8.47 has a known `ERR_MODULE_NOT_FOUND` bug), `OMNIROUTE_MEMORY_MB=4096`, exposes 20128/20129.
- `deploy/compose/docker-compose.omniroute.yml` — `leadgen-omniroute`, loopback `127.0.0.1:20128/20129`, volume `omniroute_data`, `restart: unless-stopped`.

**Rewritten launchers (WSL removed):**
- `scripts/start-omniroute.ps1` — Docker idempotent start + bounded health wait; graceful-degrade to `free_ai.py` fallback on failure.
- `scripts/omniroute-check.ps1` — container state + `/v1/models` readiness (no WSL/nvm path).
- `scripts/start-leadgen-dev.ps1` + `scripts/_leadgen_dev_up.sh` — Docker bring-up (Redis + OmniRoute), no WSL base64-pipe.
- `scripts/omniroute-tmux.sh`, `scripts/omniroute_ensure_running.sh`, `scripts/omniroute-healthguard.sh`, `scripts/omniroute_debug_capture.sh` — Docker-based (tmux/WSL-nvm path removed).
- `scripts/start-hermes-omniroute.ps1` (new) — "Open Hermes → gateway also comes up".

**Contract tests updated** (pin the Docker design): `tests/test_omniroute_scripts.py`, `tests/test_omniroute_governance.py`.

## 1b. Memory (RAM) fix

The old WSL runtime carried a hard-coded heap (`2048 -> 4096` after a 2026-08-23 prod
incident — `heapUsed=1681MB / limit=2096MB -> HTTP 503`, heap ~half of box RAM). Because the
gateway now runs in Docker on the local machine, that fixed 4096 is fragile: too low on a big
machine (503) and too high on a busy/small machine (RAM exhaustion / Docker starvation).

**Fix — adaptive, configurable, bounded:**
- `start-omniroute.ps1` now auto-sizes `OMNIROUTE_MEMORY_MB` to ~half of host RAM, clamped
  `[1024, 4096]`, and sets `OMNIROUTE_MEM_LIMIT_MB` (hard container backstop = heap * 2, well
  above Node's ~heap*1.3-1.5 RSS) so a runaway gateway cannot starve Docker Desktop and GC
  pressure is never an OOM tripwire. It respects an explicit `OMNIROUTE_MEMORY_MB` override.
- `deploy/compose/docker-compose.omniroute.yml` interpolates both with proven defaults
  (`OMNIROUTE_MEMORY_MB:-4096`, `OMNIROUTE_MEM_LIMIT_MB:-8192m`) + a `mem_limit`.
- `.env.example` documents both (guidance: ~half of box RAM, clamp [1024, 4096]).
- `_leadgen_dev_up.sh` does the same adaptive sizing for bash/git-bash users.

## 2. Why this is safe

- **Production stack untouched.** OmniRoute is absent from `docker-compose.vps.yml`, `deploy/legacy`, and the VPS `.env` (ADR-111). This is dev/loopback-only.
- **Security model preserved.** The gateway is bound to `127.0.0.1:20128/20129` only. OmniRoute does not enforce auth on loopback (2026-08-09 smoke), so loopback binding remains the whole boundary — the compose file pins `127.0.0.1`.
- **Graceful degradation.** If the gateway is unreachable, `app/voice_agent/free_ai.py` fallback continues; no revenue/customer path depends on OmniRoute.

## 3. What requires OWNER action (first run)

1. **Build + first start:**
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\start-omniroute.ps1
   ```
   (or `docker compose -f deploy/compose/docker-compose.omniroute.yml up -d --build`).
2. **Re-establish provider/OAuth connections.** The volume `omniroute_data` starts empty. Either seed it from the old WSL `/root/.omniroute`, or re-add provider keys / OAuth in the dashboard at `http://127.0.0.1:20128`.
3. **Run `omniroute doctor`** in the container to confirm the Node 22 / better-sqlite3 ABI is healthy:
   ```powershell
   docker compose -f deploy/compose/docker-compose.omniroute.yml exec omniroute omniroute doctor
   ```

## 4. Rollback

`docker compose -f deploy/compose/docker-compose.omniroute.yml down`, unset the local OmniRoute endpoint, and return the coding tool to its previous config. The old WSL launchers were rewritten, so if a hard WSL rollback is ever required, restore from `git` history — but note a full WSL-return is **not** recommended (the WSL instance holds no state this lane needs any more; the volume does).

## 5. Verification status

- `docker compose -f deploy/compose/docker-compose.omniroute.yml config --quiet` → **EXIT=0** (compose valid).
- PowerShell parse (AST) of all 4 rewritten/new `.ps1` → **OK**.
- WSL-removal marker assertions (30 checks across all rewritten scripts/compose/Dockerfile) → **PASS**.
- Full pytest could **not** be executed in this session: the sandbox denies pytest's tmpdir machinery `os.listdir()` on the basetemp directory (environment-only; every test errors at session setup regardless of change). Contract markers were verified via direct file-content assertions instead.

## 6. Note (no mutation of prod / no commit-performed)

Read-only inspection + file writes only. No WSL distro, Docker engine, scheduled task, or OS setting was changed. No `.env`, secrets, or production config touched. Nothing committed/pushed/deployed.

**Canary:** 🐦 pelican
