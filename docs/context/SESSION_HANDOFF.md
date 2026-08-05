# SESSION_HANDOFF — 2026-08-06 PR Factory #248 fix + deploy

## Production truth
- **Prod `/health` = `084cd990`** before this slice; target tip after merge+deploy.
- `VOICE_LAUNCH_KILL=0` · calling LIVE · memory/OKF/PR_FACTORY flags stay OFF.

## In flight
- Fix #248: Gate A workflow removed `pip install --upgrade pip` (pin contract).
- Rebase onto `origin/main`; ADR number conflict → PR Factory becomes **ADR-163** (main already used ADR-156 for Memory Stack).

## Do NOT
- Enable `PR_FACTORY_ENABLED` / `EXTERNAL_AGENT_*` in production
- Vendor openai/symphony
- Force-merge on red CI
