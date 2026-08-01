# Claude web-research recovery — 2026-08-01

**Status:** Recovered by Cursor after Claude session died.
**Source:** Launch-commander workflow `wf_11388add-232` `journal.jsonl` (individual agents completed; aggregator returned empty `lanes:[]`).
**Machine-readable:** `CLAUDE_WEB_RESEARCH_2026-08-01.json` (9 lanes).

> Workflow shell claimed all research lanes "missing". That was **aggregator failure**, not empty research. Full findings exist in journal `type:result` records.

## Lane scoreboard

| Lane | Verdict | Top action |
|---|---|---|
| PR #204 adversarial (HyperFrames) | GREEN | Keep flags OFF until exact-head canary PASS |
| HyperFrames upstream/web | AMBER | `--no-sandbox` hardcoded upstream; network_disabled is policy-only; pin Chrome via HF upgrades |
| Free AI provider chain | AMBER → **code fix applied this packet** | Groq Llama 8B/70B shut down **2026-08-16**; dead Qwen3-32B + Kimi K2 already in chain |
| Frontend funnel | AMBER → **pricing honesty fix applied** | ₹5,999 mislabeled as voice-only; dead Compare CTA; no yearly toggle |
| Celery + GHA security | AMBER → **one Celery setting applied** | Pin Actions to commit SHA (owner/CI follow-up); set `worker_cancel_long_running_tasks_on_connection_loss` |
| Security surface | AMBER | AUTO_EMAIL_OUTREACH 25/day is per-RUN not per-day (~275/day if hourly) |
| Agent-OS | AMBER | Dry-run burned live funnel sequencing; `handle_inbound` dead for real email stop |
| Harness C-01..C-15 | AMBER | self_improve fleet kill needs worker restart; dead-man alert in-band |
| Release / deploy | AMBER | `Dockerfile.lock` COPY `data/` can bake customer phone into GHCR — **owner P1** |

## Applied this session (launch worktree / PR #210)

1. Groq model migration to official replacements (`openai/gpt-oss-20b`, `openai/gpt-oss-120b`, `qwen/qwen3.6-27b`); remove already-dead chain entries.
2. `/pricing` billing-truth copy: Combo naming, Compare → `/compare`, monthly/yearly toggle, larger tap targets.
3. Celery `worker_cancel_long_running_tasks_on_connection_loss=True` (acks_late companion).

## Owner / follow-up (not auto-applied)

- Rotate Gemini key from VPS bash_history (security lane P1).
- Stop baking `data/` PII into public images (`Dockerfile.lock`).
- Pin GitHub Actions (esp. `appleboy/ssh-action`) to full commit SHAs.
- Cap `AUTO_EMAIL_OUTREACH` true daily (or keep OFF; prefer sales_autopilot path).
- HyperFrames enable gates: container hardening for Chrome `--no-sandbox`; scrub hermetic env secrets before Node; prove Linux canary (PR #204).
- Do **not** enable HyperFrames / WA auto / dial beyond test allowlist without owner go-ahead.

## Primary sources (research agents)

- https://console.groq.com/docs/deprecations
- https://github.com/heygen-com/hyperframes (+ npm `hyperframes@0.7.87`, Apache-2.0)
- Celery 5.x reliability docs (acks_late + cancel-on-connection-loss)
- GitHub Advisory DB (sharp/adm-zip/ws — lockfile clean at pin time)
