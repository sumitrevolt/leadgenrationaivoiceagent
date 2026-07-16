# Agent OS + OmniRoute — Admin Runbook (LeadGen AI)

_Last verified against code: 2026-07-16 (ADR-108 + ADR-109)._  
_Hinglish operator guide. Implementation truth = code, not wishes._

Related:
- `docs/ADMIN_OPERATING_GUIDE.md` — daily HQ / Control Center / approvals
- `docs/OMNIROUTE_ADMIN_GUIDE_HINGLISH.md` — local OmniRoute start/check
- `docs/omniroute/ROUTING_POLICY.md` · `PROVIDER_MATRIX.md` · `ROLLBACK.md`
- Code: `app/platform/team.py`, `agent_os_routing.py`, `omniroute_client.py`
- Specs: `agent-os/agents/` (generated — haath se edit mat karo)

---

## 1. Daily Admin Checklist (Agent OS / OmniRoute slice)

1. Login `/app/admin-login` — `● prod` badge dekho.
2. `/health` → `version` = 8-char SHA (kabhi `latest` nahi).
3. `/app/office#reliability` → `celery` / `retry-failed` / `dead` (dead > 0 = attention).
4. `/app/automation#schedule` → jobs alive, last-run ok.
5. OmniRoute **production pe OFF hi rehna chahiye** unless you explicitly built a VPS gateway.
   - Flags: `OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS` dono default OFF.
6. Customer-facing: Jiya pe publish / Deliver Now / dial **bina soch ke mat dabao**.

## 2. Weekly Admin Checklist

1. Agent roster still 31? `agent-os/agents/INDEX.md` vs Office Staff pulse.
2. Provider matrix re-read (`docs/omniroute/PROVIDER_MATRIX.md`) — koi stale model?
3. Own-brand social: `data/social_post_jobs.jsonl` me real `post_id` aaya?
4. Disk / DLQ / Sentry triage (ADMIN guide §2).
5. Specs drift? Agar `team.py` STAFF badla → `python scripts/gen_agent_os_specs.py`.

## 3. Agent Health Checklist

| Check | Where | Healthy |
| --- | --- | --- |
| Staff pulse | `/app/office` · `/app/control-center` L4 | Agents listed, no stuck pulse |
| Feature gates | `/app/automation` flags / env | Unexpected ON = investigate |
| Spec exists | `agent-os/agents/<key>.md` | Regenerated, not hand-edited |
| Privacy | Spec “OmniRoute eligible” | Voice/billing = **no** |
| Disable | Office pause **or** unset agent gate | One agent off ≠ whole system off |

Green process ≠ proven workflow. Publish/call/email ke liye alag evidence chahiye.

## 4. OmniRoute Provider Setup

1. Local only: `scripts/start-leadgen-dev.ps1` + `scripts/omniroute-check.ps1`.
2. Dashboard `http://127.0.0.1:20128` — **admin khud** API key/OAuth enter kare (chat me paste mat).
3. Sanitized test: Groq + Mistral Responses smoke (dekh `VERIFICATION_EVIDENCE.md`).
4. LeadGen `.env` / user env: `OMNIROUTE_API_KEY` (value kabhi commit nahi).
5. VPS pe enable **mat** karo jab tak loopback gateway/tunnel + `OMNIROUTE_BASE_URL` na ho.

## 5. Model Routing Policy

Code registry: `omniroute_client._TASK_ROUTES` + `agent_os_routing.py`.

| Route | Use |
| --- | --- |
| `leadgen.agent_ops` | Staff bulk (eligible agents) |
| `leadgen.coding_primary` / `coding_fast` | Sanitized coding |
| `leadgen.repo_analysis` | Infra/SRE digests |
| `leadgen.test_generation` | Deps/test helpers |

Customer / voice / billing / security → **no OmniRoute task**.

## 6. Adding a New Agent

Follow `agent-os/agents/NEW_AGENT_TEMPLATE.md` (8-step checklist + table).  
Must add `_AGENT_OVERRIDES` in `agent_os_routing.py` before merge.

## 7. Disabling an Agent

1. Prefer: Office HQ pause for that staff member (if wired).
2. Or unset its feature gate (`SOCIAL_ENGINE=0`, `INFRA_HANDLER=0`, …).
3. OmniRoute slice: `OMNIROUTE_AGENTS=0` (saare agent OmniRoute hooks off) ya master `OMNIROUTE_ENABLED=0`.
4. Verify: schedule last-run stops / pulse shows paused — **customer message mat bhejo test ke naam pe**.

## 8. Adding a New Provider

1. Suitability: privacy, rate limit, free-stack, structured output.
2. Admin dashboard me credential (human only).
3. One sanitized request + latency note.
4. `PROVIDER_MATRIX.md` update; route me tabhi add jab verified.
5. OpenCode Free / DuckDuckGo = PII fallback **blocked**.

## 9. Changing a Route

1. Edit `_TASK_ROUTES` and/or `agent_os_routing._AGENT_OVERRIDES`.
2. Update `docs/omniroute/ROUTING_POLICY.md`.
3. Tests: `tests/test_agent_os_routing.py` + `tests/test_omniroute_client.py`.
4. Regenerate specs. Flags OFF default rakho.

## 10. Provider Failure Recovery

- Fail-open: OmniRoute down → free_ai chain chalti hai.
- Circuit / retry: primary → one fallback on 408/429/5xx only (dekh client).
- Admin: logs me `[omniroute_decision] ok=False … skip=…` grep karo.
- Customer impact zero jab flags OFF (prod default).

## 11. Queue and DLQ Recovery

- `/app/office#reliability` — `retry-failed` vs `dead`.
- Celery depth spike + 0 running = stuck worker (ADMIN guide).
- Blind `del celery` sirf known restart-storm playbook pe.

## 12. Scheduler Troubleshooting

- `/app/automation#schedule` + Control Center HEARTBEAT `N/N`.
- Boot-grace: heavy jobs boot window me SKIP (expected).
- `RUN_IN_PROCESS_SCHEDULER=0` prod Celery beat — rollback playbook alag.

## 13. Production Verification

```text
curl.exe https://leadsgenai.in/health
curl.exe https://leadsgenai.in/health/ready
curl.exe https://leadsgenai.in/api/activation/summary
```

Expect: healthy, SHA version, db/redis ok, `blocker_count=0`.

## 14. Safe Deployment

Canonical: `scripts/deploy_vps.sh` with `APP_VERSION=<sha>` (never `:latest`).  
Pre: targeted pytest + `prod_check.py` + `check_secrets.py`.  
User ask ke bina commit/push/deploy mat karo.

## 15. Rollback

| Change | Rollback |
| --- | --- |
| OmniRoute agent hook | `OMNIROUTE_AGENTS` unset |
| All OmniRoute | `OMNIROUTE_ENABLED` unset |
| Routing policy code | revert `agent_os_routing.py` + client |
| Deploy | previous SHA via `deploy_vps.sh` |

Details: `docs/omniroute/ROLLBACK.md`.

## 16. Customer Privacy Rules

- Raw phone/email/transcript/payment → OmniRoute **nahi**.
- `mask_customer_data` + `validate_no_secrets` before any gateway call.
- Privacy classes: INTERNAL_SANITIZED only for approved routes.
- Jiya tenant: view OK; publish/deliver/call = explicit human approval.

## 17. Incident Response

1. Stop customer-facing risk (pause agent / unset gate).
2. Capture SHA + `[omniroute_decision]` / Sentry issue (no secrets in paste).
3. Confirm free_ai still serves (fail-open).
4. Write `memory/incidents.md` after fix.

## 18. Secret Rotation

- OmniRoute API key: dashboard revoke → new key → Windows user env / local `.env` only.
- Prod VPS `.env` touch = owner SSH; agent chat me value **kabhi** nahi.

## 19. Admin Training Guide (short)

| Module | Page | Lesson |
| --- | --- | --- |
| Login | `/app/admin-login` | Password autofill; chat me mat bolo |
| HQ health | `/app/office` | celery + dead counts |
| Control Center | `/app/control-center` | L1 problems, L4 agents |
| Automation | `/app/automation` | schedule + approvals + flags |
| Agent tools | `/app/agent-tools` | Agent OS table + OmniRoute gates (detail) |
| Automation Aaj | `/app/automation` | Agent OS wiring card (summary) |
| Control Center | `/app/control-center` | Agent OS / OmniRoute L1 panel |
| OmniRoute local | `127.0.0.1:20128` | Provider key khud enter |
| Version | `/health` | SHA ≠ latest |
| Emergency | flags / Office pause | Ek agent band, system zinda |

## 20. Architecture and Ownership Map

```text
Admin UI ──> FastAPI app
              ├── team.py STAFF (31 agents) ──> agent-os/agents/*.md (generated)
              ├── agent_os_routing.py (privacy + OmniRoute eligibility)
              ├── free_ai.py (authoritative LLM chain)
              └── omniroute_client.py (INERT default, double-gated bulk hook)
OmniRoute gateway ── local WSL :20128 only (NOT in docker-compose.vps.yml)
Celery/Redis/Postgres/Qdrant ── production automation truth
```

Owner: Founder/admin for credentials + flag flips.  
Engineering: code routes, tests, deploy scripts.

---

## Honest gaps (do not mark “done”)

- OmniRoute status UI LIVE on `/app/agent-tools` + summary on `/app/automation` Aaj + `/app/control-center` L1 (2026-07-16 wiring).
- VPS OmniRoute gateway **missing** → prod agent OmniRoute = blocked by infra (flags OFF = correct).
- Per-call `agent_key` free_ai.chat se abhi pass nahi hota (generic `agent_ops`);  
  policy enforce hoti hai jab caller `try_agent_chat(..., agent_key=)` de.
