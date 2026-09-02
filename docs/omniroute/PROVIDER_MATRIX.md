# OmniRoute provider matrix

Status captured from a fresh authenticated dashboard tab on 2026-07-13. A connection
is not a production routing approval.

| Provider | Auth | State | Models shown | Route decision | Notes |
| --- | --- | --- | ---: | --- | --- |
| Groq | API key | Connected, re-tested | 17 active | Approved, sanitized dev coding/fast only | Re-test had no console error. |
| Gemini | API key | Connected, re-tested | 54 active | Approved, sanitized dev/general only | Re-test had no console error. |
| Mistral | API key | Connected, re-tested | 60 active | Approved, sanitized dev/general only | Re-test had no console error. |
| OpenCode Free | No authentication | Playground smoke passed; REST response was reasoning-only | 8 active | Excluded from API fallback; no customer route | `oc/big-pickle` returned `omni-ok` in the dashboard, but its direct OpenAI-compatible response had empty `content`; PII is fail-closed. |
| DuckDuckGo AI Chat | No authentication | Enabled, but generic smoke rate-limited | 6 active | Excluded pending a successful re-test | `ERR_RATE_LIMIT` on 2026-07-13; do not use as fallback. |
| Kimi Coding | OAuth | Connected | Not independently model-tested | Preserve, disabled from routes | Privacy suitability is insufficient for customer data. |
| Cline | OAuth | Connected | Not independently model-tested | Preserve, disabled from routes | Development-tool connection, not a LeadGen runtime provider. |
| Kiro | OAuth | Connected | Not independently model-tested | Preserve, disabled from routes | Development-tool connection, not a LeadGen runtime provider. |
| Antigravity | OAuth (2 accounts) | Connected | Not independently model-tested | Preserve, disabled from routes | Dashboard labels usage caveats. |
| Devin CLI, GitHub Copilot, Trae | OAuth/IDE | Error | N/A | Preserve, do not route | Error state observed; no repair or credential change attempted. |
| Claude Code, OpenAI Codex, Qwen Code | OAuth | No connection | N/A | Category C | Human sign-in is required before any test. |
| Web-cookie providers | Browser session/cookie | No connection | N/A | Category D excluded | Do not connect, import cookies, or route LeadGen work. |
| Local providers | Local endpoint | No connection | N/A | Category C | Add only after a separately verified local endpoint exists. |

Configured totals shown by the dashboard: 10 provider records of 258, including six
OAuth and three API-key records. The count is not a measure of usable model coverage.

## Fresh runtime re-check — 2026-07-14

The local CLI now reports 13 provider records: 10 active, one unknown, and two error
states. A fresh `GET /v1/models` returned 489 catalog entries. Groq and Mistral passed
sanitized `POST /v1/responses` requests. The catalogued
`gemini/gemini-2.5-flash` model returned upstream `model_not_found` because it is no
longer available to new users; it is excluded from active routes until a different
Gemini model passes the same request test. No credential was viewed, changed, or added.

## Provider admission rule

Add credentialed providers only through the dashboard with the admin entering the
credential. Credential-free providers still need one non-sensitive request, actual
model ID, latency, safe logs, and a bounded fallback before they can be considered for
any dev route. Neither type is a production-routing approval.
