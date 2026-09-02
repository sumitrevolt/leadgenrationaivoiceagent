# OmniRoute routing policy

## Current policy

No LeadGen customer runtime route is enabled. The existing direct-provider chain in
`free_ai.py` is authoritative. OmniRoute is available only for local, sanitized
development work after an explicit opt-in and real completion test.

| Task route | Privacy class | Primary | Safe fallback | Current status |
| --- | --- | --- | --- | --- |
| `leadgen.coding_primary` | INTERNAL_SANITIZED | `groq/llama-3.3-70b-versatile` | `mistral/mistral-small-latest` | Adapter + sanitized local completion verified; feature flag remains OFF |
| `leadgen.coding_fast` | INTERNAL_SANITIZED | `groq/llama-3.3-70b-versatile` | `mistral/mistral-small-latest` | Adapter route available only after explicit local opt-in |
| `leadgen.repo_analysis` | INTERNAL_SANITIZED | `mistral/mistral-small-latest` with Graphify-bounded context | `groq/llama-3.3-70b-versatile` | Adapter route available only after explicit local opt-in |
| `leadgen.test_generation` | INTERNAL_SANITIZED | `groq/llama-3.3-70b-versatile` | `mistral/mistral-small-latest` | Adapter route available only after explicit local opt-in |
| `leadgen.agent_ops` | INTERNAL_SANITIZED | `groq/llama-3.3-70b-versatile` | `mistral/mistral-small-latest` | ADR-108/109 staff bulk hook; double-gated (`OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS`); per-agent eligibility in `agent_os_routing.py` |
| `leadgen.architecture_review` | SENSITIVE_LOCAL_ONLY | Human-approved senior review | Controlled failure | Not configured |
| `leadgen.security_review` | PROHIBITED_EXTERNAL | Local deterministic review + human | Controlled failure | Not configured |
| `leadgen.customer_report_summary` | CUSTOMER_SANITIZED | No OmniRoute route | Existing approved path | Prohibited pending policy approval |
| `leadgen.log_summary` | INTERNAL_SANITIZED | Sanitized-only local tooling | Controlled failure | Not configured |

## Agent → route map (code)

Source: `app/platform/agent_os_routing.py` (`agent_route_table()`). Specs regenerate via
`scripts/gen_agent_os_specs.py`.

- Voice / transcripts / escalation (`swara`, `ananya`, `riya`, `arjun`, `meera`, `lekha`,
  `raksha`, `tara`): **OmniRoute forbidden** (`omniroute_task=None`).
- Billing / FinOps / security / DBRE / CRM-PII (`nikhil`, `vidya`, `arnav`, `kabir`,
  `priya`, `diya`): **OmniRoute forbidden**.
- Marketing/platform bulk (`zara`, `isha`, `ravi`, `dev`, `manager`, …): eligible for
  `leadgen.agent_ops` (or `repo_analysis` / `coding_primary` / `test_generation` where
  noted) **only when** privacy is `INTERNAL_SANITIZED` and both flags + key are set.
- Decision logs: `[omniroute_decision] …` (no raw prompts/PII).

## Non-negotiable exclusions

OmniRoute must not choose or execute billing/payment, UPI, DND/TRAI, legal,
authentication, tenant-isolation, destructive database, WhatsApp/email bulk-send,
cold-call, or live voice actions. No route may silently fall back to an unapproved,
paid, browser-cookie, or privacy-unclear provider.

OpenCode Free and DuckDuckGo AI Chat are explicitly excluded from API fallbacks:
OpenCode's direct response contract was not suitable for the gateway adapter and
DuckDuckGo returned a rate-limit failure. Both are blocked from receiving PII.

## Retry policy for any future adapter call

Use a per-task timeout and at most two total attempts: primary then one verified
fallback for timeout/transport, 408, 429, or 5xx only. Never retry 401/403,
schema rejection, or a prohibited-privacy request. Log only
route/provider/model/status/latency/token counts/fallback reason; never raw prompts
or completions.
