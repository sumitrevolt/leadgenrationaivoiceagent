---
name: supply-chain-security
description: Dependency + build supply-chain hygiene — requirements.lock.txt discipline, pip-audit CVE scan, Docker base-image updates, typosquat guard, GitHub Actions pinning, unattended-upgrades. Use jab naya package add ho, CVE news aaye, quarterly dependency hygiene chale, ya lock refresh (vps_freeze) ho.
---

# Supply-Chain Security (har `pip install` = kisi stranger ka code prod me)

> Enterprise audit skill. House build = deterministic: `Dockerfile.lock` installs `requirements.lock.txt` via `--no-deps` (py3.12) — yeh already strong base hai. Yeh skill = uske upar CVE/typosquat/base-image layer. Pehle `context-first`.

## Repo truth
- **Lock discipline**: `requirements.lock.txt` = live-venv freeze (`scripts/vps_freeze.sh` → commit). `--no-deps` = transitive surprise nahi. ML assets image-baked (fastembed, silero) = runtime-download attack surface band.
- **Host**: fail2ban + unattended-upgrades ACTIVE (OS patch auto). Docker containers = MANUAL rebuild se hi base-image patch aata — yeh gap hai, schedule chahiye.
- **CI gate-only** (`deploy-vps.yml` DEPLOY_ENABLED unset) — CI compromise se auto-deploy NAHI ho sakta = accidental strong control, aise hi rakho.

## Quarterly hygiene loop
1. **CVE scan**: sandbox me `pip install pip-audit --break-system-packages` → `pip-audit -r requirements.lock.txt` → CRITICAL/HIGH triage (exploitable in OUR usage? internet-facing path?).
2. **Base image**: `docker inspect leadgen_app | grep -i created` — 90d+ purana = rebuild (`docker compose build --pull app`) for base-layer patches. Same for postgres/redis images (`docker images` dates); Caddy = HOST-level (container nahi) — OS packages/unattended-upgrades se patch hota (2026-07-05).
3. **Upgrade batch**: sirf CVE-driven ya need-driven bumps (blanket "sab latest" = free-stack breakage; e.g. `edge-tts>=7.2.0` pin ka 403 lesson). Bump → local test → `vps_freeze.sh` → lock commit → deploy loop.
4. **Actions pinning**: `.github/workflows/*.yml` me third-party actions SHA-pinned ya at least major-version — `@main` floating = supply-chain hole.
5. **npm side** (agar frontend build ho): lockfile committed + `npm audit` — same triage.

## New-package gate (add karne se PEHLE)
- Naam DOUBLE-check (typosquat: `requests` vs `reqeusts`) — PyPI page kholo, download count + repo link verify.
- Maintenance pulse: last release <18mo, issues responsive? Abandoned = fork-risk.
- License compatible (MIT/BSD/Apache ok; AGPL = sochh ke, SaaS obligation).
- Kya existing dep se kaam ho jata? (dependency count khud ek liability hai.)
- Install → `vps_freeze.sh` → lock diff REVIEW karo (kya transitive aya) → commit.

## Incident path (malicious/CVE-critical dep mila)
1. Blast radius: kab se lock me hai, kya us path pe secrets/PII flow hota?
2. Pin-downgrade ya remove → emergency deploy loop → secrets-rotation trigger (agar exfil possible tha).
3. Evidence SESSION_LOG + guard (is skill me pattern add).

## Output
pip-audit report triaged · base-image age table · pinned-actions status · lock diff reviewed · fixes shipped.

## Related repo skills
`secrets-rotation` (leak response) · `verify-ship` (deploy) · `model-asset-bake` (ML assets) · `security-review` (code-level) · `dr-restore-drill` (rebuild determinism).
