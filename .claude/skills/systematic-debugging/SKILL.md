---
name: systematic-debugging
description: Bug/test-fail/prod-error pe ROOT CAUSE pehle, fix baad me — reproduce→isolate→hypothesize→verify protocol + LeadGen-specific triage (stale .pyc, event-loop starve, sandbox-stale, check_route.py). Use when user says "bug hai", "500 aa raha", "test fail", "site down", "kaam nahi kar raha", "production error", ya koi bhi unexpected behavior.
---

# Systematic Debugging (root cause pehle, fix baad me)

**Iron rule: BINA root-cause investigation ke koi fix nahi.** Random patch = naya bug + waste. 3 fix fail ho gaye = architecture question karo, 4th guess mat maro.

## 4-phase protocol

1. **REPRODUCE** — error message/stack POORA padho (line numbers, file paths). Reliably trigger kar sakte ho? Nahi → pehle aur evidence collect karo, guess mat karo. Recent changes dekho: `git log --oneline -10` + last deploy.
2. **ISOLATE (layer-by-layer)** — multi-component system me har boundary pe data check karo: request → Caddy → uvicorn → route → engine → DB/Redis/LLM. Project tools niche table me. Working example dhundo (same codebase me similar route jo chalta hai) aur diff karo — "ye matter nahi karta" assume mat karo.
3. **HYPOTHESIZE + verify minimally** — EK hypothesis likho ("X root cause hai kyunki Y"), SMALLEST change se test karo, ek variable at a time. Fail → NAYA hypothesis, purane fix ke upar aur fix mat chadhao.
4. **FIX + lock** — pehle failing test likho (`tests/` me, repro = simplest), fir root-cause fix, fir `scripts\run_tests.bat` + **pytest_run.log Read karo**. Symptom-fix = failure.

## Project triage table (pehle yahan dekho — ye sab HO CHUKE hain)

| Symptom | Likely root cause | Tool/Fix |
|---|---|---|
| Naya route 404 par openapi me hai | Stale `.pyc` — restart ne purana bytecode serve kiya | HARD RELOAD: `systemctl stop` / `docker compose stop app` → `pkill -9 -f uvicorn` → `__pycache__` rm → start |
| Health 000, dono workers hang | **Event-loop starve** — public endpoint me SYNC KB/ML/SDK (kb.retrieve, fastembed first-load, sync google SDK) | `await asyncio.wait_for(asyncio.to_thread(fn), timeout=10-25)`; smoke me LLM-endpoint ke DAURAN health 6x poll |
| Route locally hai, prod me nahi | Deploy/import fail ya shadow (duplicate route — first-route-wins) | `scripts/check_route.py` (in-process ASGI test, server bypass) + `grep '@router' app/api/<file>.py` |
| Boot ke turant baad site down | Heavy job boot pe fire (qa/trainer window) — scheduler boot-grace dekho | `docker logs leadgen_app --tail 200` / `journalctl -u leadgen` + `TEAM_AUTOMATION=0` recover |
| Windows pe edit dikh raha, sandbox/test me nahi | **Sandbox mount STALE** — Windows side = source of truth | Verify Windows pe hi (bat chala ke log Read) |
| LLM features chup-chaap fallback | Provider 429/quota (circuit-breaker cooldown) | `GET /api/growth/infra/llm` (llm_metrics) + `data/llm_calls.jsonl` |

## Evidence commands
- Logs: `docker logs leadgen_app --tail 200` (VPS) · `journalctl -u leadgen -n 200` (legacy systemd path)
- In-process route test: `python scripts/check_route.py <path>` — Caddy/network ko bypass karke app se seedha poochta hai
- Health layers: `/health` (app) → `/health/ready` (db+redis) → `docker ps` (unhealthy containers) → `/api/growth/infra/automation-health`

## Red flags — STOP, Phase 1 pe wapas
"Quick fix abhi, investigate baad me" · "shayad X hai, change karke dekhte" · ek saath multiple changes · fix #3 ke baad fix #4 · "samajh nahi aa raha par ye chal sakta hai". **Ye sab = guessing.** 3+ fail = architecture/pattern hi galat hai — user se discuss karo.

Fix verify hone ke baad: failing-test commit karo taaki regression lock ho (dekho sibling skill `tdd-contract-first`). Deploy triage = `leadgen-ops` skill.

Adapted from obra/superpowers `systematic-debugging` (via VoltAgent/awesome-agent-skills).
