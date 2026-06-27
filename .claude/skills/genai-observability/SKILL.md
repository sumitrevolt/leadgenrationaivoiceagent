---
name: genai-observability
description: LLM/agent tracing via OpenTelemetry GenAI semantic conventions for LeadGen — per-provider/model/token spans, agent + tool + RAG spans, on the existing Tempo/Grafana stack. Use when debugging which provider/model served a call, token/cost attribution, agent-run traces, or wiring ENABLE_OTEL meaningfully. Complements observability-ops (infra-level Prometheus/Loki).
---
# GenAI Observability (OTel semconv)

`observability-ops` = infra-level (HTTP/Prometheus/Loki). **Yeh skill = LLM-semantic layer**: kaun-sa provider/model/kitne tokens har call pe, agent-run + tool + RAG traces. Tumhara **Tempo already raw OTel GenAI traces support karta** — bas `ENABLE_OTEL=1` + ye attributes emit karo. Source: ai-engineering-from-scratch ph14/23 ([[ai-engineering-course-reference]]).

## GenAI semantic-convention attributes (emit karo)
| Attribute | Value (hamare liye) |
|---|---|
| `gen_ai.provider.name` | mistral / groq / cerebras / gemini / nvidia / openrouter (free_ai chain) |
| `gen_ai.request.model` | requested model id (e.g. `mistral-small-latest`) |
| `gen_ai.response.model` | resolved model (fallback pe alag ho sakta) |
| `gen_ai.operation.name` | `chat` / `invoke_agent` / `tool_call` |
| `gen_ai.agent.name` | staff/persona (isha/swara/kavya/…) |
| `gen_ai.data_source.id` | RAG: `kb_main` + niche/client namespace |
| `gen_ai.usage.input_tokens` / `.output_tokens` | token count (cost attribution) |

**Kyun high-value yahan:** 8-provider chain + circuit-breaker pe `gen_ai.provider.name` + `response.model` se turant dikhta kaun-sa provider serve kar raha, kahan fallback ho raha, kis pe latency/429. FinOps: token attributes se real cost-per-niche/per-agent (notional CostTracker se upar).

## Spans (parent→child)
1. `create_agent` — agent construct (coordinator recruit).
2. `invoke_agent` — agent run; kind=`INTERNAL` (in-process coordinator/free_ai), `CLIENT` agar remote.
3. **tool span** — har tool-call (VOICE_TOOLS, agentic tools), agent-span se parent-linked.
4. **model/client span** — raw LLM call (free_ai provider hit).
→ Context propagate karo warna orphan tool-spans.

## Pitfalls (hamare liye CRITICAL)
- **Full prompt/messages span me MAT daalo** — multi-tenant + PII/DPDP + [[ai-engineering-course-reference]] ka untrusted-content concern. `gen_ai.input.messages`/`system_instructions` = opt-in only; warna sirf **reference** (id) store karo, content Loki/external me. (`llm-security` skill se tie.)
- `gen_ai.provider.name` HAMESHA set — warna multi-provider dashboard bekaar.
- Attribute-rename se bachne ko: `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`.

## Wire-in (hamare stack)
- `ENABLE_OTEL=1` (abhi wired-but-off) + `app/observability_otel.py` me free_ai call-site pe span + above attributes.
- Backend: **Tempo** (already chal raha) raw OTel GenAI ingest karta → Grafana me trace-view. Jaeger/OTel-Collector bhi free options.
- Start small: sirf provider-name + model + tokens emit karo (cheap, high-signal); messages opt-in baad me.

## Enterprise gate (trace emit = PII fail-CLOSED)

- **Operating loop:** Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Discover: `ENABLE_OTEL` wired-but-off, Tempo already chal raha, free_ai call-site = jahan span lagana hai.
- **Change-risk tier: Standard** (additive instrumentation) → **High-risk** jab span me message/prompt content jaaye (PII/DPDP/multi-tenant exposure).
- **Fail-CLOSED data gates:**
  - **No content by default** — full prompt/messages span me KABHI nahi: `gen_ai.input.messages`/`system_instructions` = opt-in only; warna sirf reference-id store, content Loki/external. Multi-tenant + PII/DPDP risk (`llm-security` se tie).
  - **Tenant/secret hygiene** — span attributes me other-tenant data ya keys leak na ho; `gen_ai.provider.name` HAMESHA set warna multi-provider dashboard bekaar.
  - **Inert without flag** — `ENABLE_OTEL=1` (default off); off = zero overhead. Attribute-rename guard: `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`.
- **Gotcha (graceful):** full OTel sdk/exporter image me NAHI (sirf `opentelemetry-api`) → `ENABLE_OTEL=1` pe graceful skip-warning, traces nahi aate jab tak otel pkgs `requirements.lock.txt` me add + rebuild na ho.
- **Rollback (NAMED):** instrumentation regression → `ENABLE_OTEL=0` (instant inert) → container recreate; PII-in-span galti = span attr remove + revert SAATH.
- **Evidence to close:** start-small emit (provider-name + model + tokens) Tempo→Grafana trace-view me dikhe; span me NO message-content (PII check); `.venv\Scripts\python.exe scripts\prod_check.py` PASS. Messages opt-in baad me, alag review se.

## Pairs with
`observability-ops` (infra) · `llm-quota-ops` (provider chain) · `llm-security` (PII in traces) · `voice-eval-metrics`.
