# Infra Best-Stack Gap Analysis — June 2026

> **Scope:** Top SaaS infra blueprints (web) ko scan karke, is repo ke ACTUAL stack se compare — sirf **genuinely additive** cheezein (duplicate nahi). Stance: **free-first, premium flagged**. Single-VPS resource-budget aware.
> **Method:** 12 web searches (SaaS reference architectures + self-host deploy + Langfuse/PostHog/Infisical/LiteLLM/pgBackup/Trivy/Cloudflare/eval) + direct repo inventory (`.github/workflows`, `pre-commit`, backup scripts, `requirements*`, `app/`). Sources niche.

---

## TL;DR (billionaire-lens)

1. **Tera stack already top-decile hai.** Jo "top SaaS infra" blueprints recommend karte hain — CI/CD, container+dep CVE scan (Trivy), SBOM, Dependabot, Alembic migrations, pre-commit (bandit/detect-secrets/hadolint/terraform), Postgres backup + restore-drill + wired offsite, OTel→Tempo, Prometheus/Grafana/Loki/Alertmanager, Celery durable scheduler + event-sourced process engine, Qdrant RAG, Sentry — **ye sab pehle se hai.** In par dobara paisa/token mat jalao.
2. **Sirf ~6 genuine gaps bache** — aur woh "basic infra" me nahi, **sophisticated layer** me: LLM-specific observability/eval, edge/WAF, web product-analytics+session-replay, runtime-secret encryption, VPS-rebuild-as-code, aur (optional) semantic LLM cache.
3. **Key architectural insight:** Tera bottleneck = **single VPS pe 13 container already**. Heavy analytics (PostHog, Langfuse) self-host = ClickHouse/Kafka, 16GB RAM → VPS marr jayega. **Billionaire move = unke generous FREE CLOUD tiers use karo, self-host sirf light/stateless cheezein.** Apna core VPS protect karo.

---

## 1) Tu jo ALREADY rakhta hai (DON'T re-buy / re-build)

| SaaS-infra pillar | Best-practice tool | Tere paas | Verdict |
|---|---|---|---|
| CI quality gate | GitHub Actions | `ci.yml`, `tests.yml` (lint+secret+pytest, targeted suites) | ✅ Have |
| Deploy automation | Kamal/Coolify/GH Actions | `deploy-vps.yml` (DEPLOY_ENABLED-gated) + manual fast-path | ✅ Have |
| Container + dep CVE scan | Trivy/Grype | `security-scan.yml` (Trivy fs vuln + misconfig + secret + image) | ✅ Have (added Jun-15) |
| SBOM | Syft/Trivy | CycloneDX `sbom.cdx.json` in CI | ✅ Have |
| Dep auto-update | Renovate/Dependabot | `dependabot.yml` (pip+actions+docker, grouped) | ✅ Have |
| DB migrations | Alembic/Flyway | `alembic.ini` + `alembic/versions` | ✅ Have |
| Pre-commit guardrails | — | black/isort/ruff/bandit/detect-secrets/hadolint/**terraform** | ✅ Have |
| DB backup + PITR-ish | pgBackRest/Barman | `pg_backup.sh` (pg_dump+gzip, 30d, **rclone→R2/B2 wired**) + `pg_restore_drill.sh` | ✅ Have (offsite dormant) |
| Error tracking | Sentry | `requirements-otel.txt` / Sentry FastAPI integration | ✅ Have |
| Metrics/logs/traces | Prom/Grafana/Loki/Tempo | full obs stack (6 containers) + OTel wired | ✅ Have |
| Workflow orchestration | Temporal/Windmill | Celery (worker+beat, DLQ) + `process_engine.py` (event-sourced, human gates) | ✅ Have — **Temporal/Windmill = duplicate, mat add karo** |
| Vector/RAG | Pinecone/Qdrant | Qdrant + agentic_rag + graph_rag | ✅ Have |
| Self-host PaaS | Coolify/Dokploy | Docker + Caddy + compose (6 files) | ✅ Have — Coolify/Dokploy = overkill duplicate |
| Server-side funnels/experiments | — | `app/analytics/dashboard.py` (ConversionFunnel), `channel_experiments.py` (bandit) | ✅ Have (server-side) |

**pgBackRest note:** April 2026 me unmaintained ho gaya — tera pg_dump+rclone approach actually better choice hai. Barman sirf multi-server enterprise pe zaroori; tujhe nahi.

---

## 2) Genuine GAPS — prioritized additive upgrades

### TIER 1 — high ROI, free/near-free, low risk

#### G1. LLM-specific observability + eval + prompt-versioning  ⭐ #1 GAP
- **Gap:** `requirements-otel.txt` sirf **generic FastAPI/ASGI tracing** (HTTP requests → Tempo) hai. `free_ai.py` me per-call **prompt/completion/tokens/latency/provider/quality-score** capture **kahin nahi** (line 71: "no per-call cost" — sahi, par observability cost ke baare me nahi, **quality+debug+regression** ke baare me hai). Poora product LLM-driven hai → ye sabse bada blind-spot.
- **Add:** **Langfuse** (LLM tracing + prompt management + eval datasets + scores). **Cloud Hobby = FREE (50k units/mo)** — self-host MAT karo (ClickHouse+Redis+MinIO heavy). Alternative ultra-light: **Arize Phoenix** (OTel-native, ek container) ya seedha **OTel GenAI semconv** spans tere existing Tempo me.
- **Why additive:** provider-fallback chain me kaunsa provider degrade ho raha, kaunsa prompt slow/looping, RAG-answer quality drift — abhi invisible. Ye dikhega.
- **Resource:** VPS pe ~0 (cloud) ya 1 light container (Phoenix). **Premium flag:** Langfuse Core $29/mo agar 50k/mo cross ho.
- **Pair:** `agent_tester.py` (tera free scorecard) → Langfuse datasets me feed = regression tracking over time.

#### G2. Edge security + CDN — Cloudflare (FREE)  ⭐
- **Gap:** Origin IP `72.61.245.204` **publicly exposed**, Caddy seedha internet-facing. No WAF, no DDoS shield, no CDN/cache, no bot-mgmt.
- **Add:** **Cloudflare Free plan** + **Cloudflare Tunnel** (`cloudflared`). Unmetered L3/L4 DDoS mitigation, CDN/cache static assets, hide origin IP (sirf outbound tunnel — VPS pe port khulne ki zaroorat nahi), basic WAF + bot rules. **100% free.**
- **Why additive:** ek hi move me security + perf + origin-hiding. `/audit` (#1 lead magnet) static-heavy → CDN cache = fast. DDoS pe VPS nahi girega.
- **Resource:** VPS pe ~0 (edge). 5MB `cloudflared`.
- **Premium flag:** Cloudflare **Pro $25/mo** = full managed WAF rulesets + image optimization (jab traffic bade tab).
- **Risk:** DNS proxy ON karna live-routing touch karta — maintenance-window me, tunnel test karke. (Isliye main ne auto-implement nahi kiya — tere account+DNS chahiye.)

#### G3. Web product-analytics + session-replay + feature-flags — PostHog Cloud (FREE)
- **Gap:** `analytics/dashboard.py` = **server-side call/lead funnels** (achha hai). Par **web/product analytics** (page-level events, **session replay**, frontend autocapture, A/B feature-flags SDK, visual web-funnels for `/audit`→`/start` signup) nahi hai.
- **Add:** **PostHog Cloud free tier** — 1M events/mo + 5k session recordings + 1M feature-flag requests + surveys, sab free. **Self-host MAT karo** (7+ services, ClickHouse+Kafka+Zookeeper, 16GB RAM — tera VPS marr jayega).
- **Why additive:** `/audit`, `/demo`, `/pricing`, `/start` pe **session replay = gold** (dekho log kahan drop karte). Feature-flags = safe rollout + A/B without redeploy.
- **Resource:** VPS pe 0 (cloud). Frontend me ek `<script>` snippet.
- **Premium flag:** 1M events ke baad usage-based (sasta); 10M/mo tak bhi cloud self-host se sasta padta.

### TIER 2 — DR / security hardening, low overhead

#### G4. Runtime secret encryption — SOPS + age  ✅ ALREADY IN REPO (correction)
- **Repo-audit update:** Ye gap **nahi** nikla — `.sops.yaml` + `scripts/sops_setup.sh` / `sops_encrypt_env.sh` / `sops_decrypt_env.sh` + `app/utils/secrets.py` **pehle se hain**. SOPS+age implemented hai; bas real `age` public key placeholder hai (dormant).
- **Action:** sirf activate — `bash scripts/sops_setup.sh` → public key `.sops.yaml` me → `bash scripts/sops_encrypt_env.sh` → `.env.sops` commit. Naya kuch banane ki zaroorat nahi.
- **Premium flag (only at scale):** **Infisical** (MIT, self-host free OSS) — agar UI + auto-rotation + dynamic + per-client secrets chahiye (white-label). Cloud Pro $18/identity/mo. Abhi SOPS kaafi.

#### G5. VPS-rebuild-as-code — Ansible playbook (FREE)
- **Gap:** pre-commit me terraform hooks hain par **koi `.tf` file nahi** = IaC aspirational, actual nahi. VPS **manually provisioned**. VPS marr gaya → poora 13-container stack haath se rebuild = ghante + error-prone. **Single-VPS = single point of failure**, aur rebuild-recipe code me nahi.
- **Add:** **Ansible playbook** (ya ek hardened `bootstrap.sh`) jo fresh Ubuntu pe: docker+compose install → repo clone → `.env` (SOPS-decrypt) → `docker compose -f docker-compose.vps.yml up` → Caddy/cloudflared → cron (backup/selfheal). Tere existing compose files se 80% ban jayega.
- **Why additive:** real DR — naya VPS 15-min me wapas. Migration/2nd-region bhi trivial ho jata.
- **Resource:** 0 runtime (laptop/CI se chalti). **Terraform nahi chahiye** single-VPS pe (over-engineering); Ansible/bash kaafi.

#### G6. Activate dormant offsite backup (FREE 10GB)
- **Gap:** `pg_backup.sh` me **rclone→R2/B2 offsite already wired** hai, bas `RCLONE_REMOTE` unset = sirf email-offsite (18MB cap) active. Ye CLAUDE.md me "R2/B2 creds — user paperwork" blocker hai.
- **Add:** **Backblaze B2** (10GB free) ya **Cloudflare R2** (10GB free, zero egress) bucket banao → `rclone config` → `RCLONE_REMOTE=r2:leadgen-backups` set → recreate. **10-min unblock, naya code nahi.**
- **Why additive:** abhi true offsite sirf email (chhota). Real object-storage offsite = proper DR.

### TIER 3 — optional / AI-automation leverage

#### G7. LiteLLM proxy + semantic cache (optional consolidation)
- **Gap/overlap:** `free_ai.py` ka homegrown multi-provider chain + circuit-breaker **kaam kar raha** — ye duplicate-risk hai, isliye TIER-3. LiteLLM additive **sirf agar** ye chahiye:
  - **Semantic cache (Redis)** → repeated/similar prompts cache → **Groq-TPD-exhaust gotcha directly kam** + latency down. (Tera #1 AI pain-point address karta.)
  - **Per-tenant virtual keys + budgets** → white-label multi-tenant LLM quota.
  - OpenAI-compatible single endpoint (client code simplify).
- **Recommendation:** abhi mat switch — `free_ai.py` fallback logic rakho. LiteLLM ko **sirf semantic-cache layer** ke roop me aazma (1 container, Postgres+Redis tere paas hai). Agar TPD pain bada ho to high-value.

#### G8. Declarative LLM/RAG eval in CI — promptfoo / Ragas (FREE)
- **Gap:** `agent_tester.py` (Python scorecard) hai, par CI me **automated prompt/agent regression gate** nahi (security-scan.yml ki tarah advisory ho sakta).
- **Add:** **promptfoo** (YAML asserts + red-teaming, CLI, GitHub-hosted runner pe — VPS 0) ya **Ragas** (RAG-specific metrics: faithfulness, context-precision). Advisory (non-blocking) workflow, exactly tere `security-scan.yml` pattern me.
- **Why additive:** prompt change → quality regression CI me pakda jaye (abhi manual).

---

## 3) Explicitly NOT recommended (duplicate — paisa/token bachao)

| Tool | Kyun NAHI |
|---|---|
| **Temporal / Windmill / Inngest** | Celery durable + `process_engine.py` (event-sourced, human gates) = already covered. Temporal heavy, Windmill UI-nice par duplicate. |
| **Coolify / Dokploy / Kamal** | Docker+Caddy+compose+GH-Actions deploy already hai. Kamal marginal; switch ka ROI ~0. |
| **Renovate** | Dependabot already (pip+actions+docker). Renovate = marginal upgrade, switch worth nahi. |
| **pgBackRest / Barman** | pg_dump+rclone better for single-VPS; pgBackRest unmaintained (Apr-2026). |
| **Resend / Postal** | Hostinger SMTP + warmup + bounce-pause already. |
| **New auth (Keycloak/Authentik)** | Homegrown RBAC + customer/admin login working — replace = high-risk duplicate. |
| **Self-host PostHog / Langfuse** | ClickHouse/Kafka heavy — single VPS marega. Cloud free-tier use karo. |

---

## 4) Engineer-agents — NEW agent mat banao, EXISTING extend karo

Tere paas already: **Vikram (code_upgrader, propose-only)**, **Hermes (infra_handler)**, **Kavya (health)**, **ops-watchdog**, **Arjun (QA)**. Naya SRE-agent = duplicate. Instead in signals ko existing agents me **add** karo (free-stack, propose-only pattern):

- **Vikram (code_upgrader):** naya signal = **LLM-eval regression** (Langfuse/promptfoo se) → prompt/patch proposal `data/code_patches.jsonl` + email. Aur **Trivy CRITICAL CVE** → dep-bump proposal.
- **Kavya/ops-watchdog:** naye health-checks = **offsite-backup staleness** (last R2/B2 push > 36h → alert), **TLS cert expiry**, **Cloudflare origin-health**, **Langfuse error-rate spike per provider**.
- **Arjun (QA):** nightly run me **Ragas RAG-faithfulness** score add → KB drift pakdo.

Ye sab tere `staff_for_product()` + `agent_events` + ntfy-push me fit ho jata — **naya infra nahi, naye sensors.**

---

## 5) Phased rollout (suggested)

- **Week-1 (free, high ROI):** G6 (offsite creds, 10min) → G2 (Cloudflare free + Tunnel, maintenance-window) → G1 (Langfuse cloud-free, instrument `free_ai.py` 1-decorator).
- **Month-1:** G3 (PostHog cloud-free snippet on public pages) → G4 (SOPS+age encrypt `.env`) → G5 (Ansible/bootstrap rebuild playbook).
- **Opportunistic:** G8 (promptfoo advisory CI) → G7 (LiteLLM semantic-cache, only if Groq-TPD pain bada) → extend Vikram/Kavya sensors (§4).

---

## 6) Is session me IMPLEMENTED (zero prod-risk)

- **`app/observability_llm.py`** — gated LLM-observability module (G1 ka foundation). **Off by default** (`ENABLE_LLM_OBS=1` se ON). Auto-detect backend: Langfuse (keys set ho to) → OTel GenAI spans (Tempo) → warna no-op. **Never-raise** (tera FAIL-OPEN philosophy). `free_ai.py` ko touch nahi kiya (hot-path safe) — wiring snippet niche.

```python
# free_ai.py me (jab ready ho), provider-call ke around:
from app.observability_llm import llm_span
with llm_span("chat", model=model, provider=provider) as span:
    resp = await _call_provider(...)
    span.record(prompt_tokens=pt, completion_tokens=ct, latency_ms=ms, ok=True)
```

Enable karne ke liye: `pip install langfuse` + `.env` me `ENABLE_LLM_OBS=1` + `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` (cloud-free se). Bina inke = graceful no-op, koi risk nahi.

**Baaki gaps (G2/G3/G4/G5/G6/G7/G8)** runbook-ready hain par tere accounts/creds/DNS/prompt-interfaces chahiye — bol de to step-by-step apply kar dunga.

---

## Sources
- [MakerKit — Best SaaS Stack 2026](https://makerkit.dev/blog/saas/saas-stack-2026) · [supastarter — Best SaaS Stack 2026](https://supastarter.dev/blog/best-saas-stack) · [SapientPro — SaaS Architecture Best Practices 2026](https://sapient.pro/blog/saas-architecture-best-practices)
- [awesome-opensource-boilerplates (GitHub)](https://github.com/EinGuterWaran/awesome-opensource-boilerplates) · [ixartz/SaaS-Boilerplate](https://github.com/ixartz/SaaS-Boilerplate)
- [Self-Hosted Deploy Tools Compared — Coolify/Dokploy/Kamal/Dokku/Haloy (DEV)](https://dev.to/ameistad/self-hosted-deployment-tools-compared-coolify-dokploy-kamal-dokku-and-haloy-2npd) · [bitdoze — Coolify vs Dokploy vs Kamal](https://www.bitdoze.com/coolify-vs-dokploy-vs-kamal-2/)
- [Langfuse self-hosting docs](https://langfuse.com/self-hosting) · [langfuse/langfuse (GitHub)](https://github.com/langfuse/langfuse) · [Langfuse v3 self-host guide](https://jangwook.net/en/blog/en/langfuse-self-hosted-llm-tracing-setup-guide-2026/)
- [PostHog self-host docs](https://posthog.com/docs/self-host) · [PostHog (GitHub)](https://github.com/PostHog/posthog) · [PostHog self-hosted honest take (Cotera)](https://cotera.co/articles/posthog-self-hosted-guide)
- [Infisical — Best Secrets Mgmt Tools 2026](https://infisical.com/blog/best-secret-management-tools) · [GitGuardian — Top Secrets Mgmt Tools 2026](https://blog.gitguardian.com/top-secrets-management-tools/) · [Infisical vs Doppler (Flywheel)](https://wetheflywheel.com/en/comparisons/infisical-vs-doppler/)
- [LiteLLM docs](https://docs.litellm.ai/docs/) · [AI Gateway Setup 2026 — LiteLLM/Portkey/Kong (Spheron)](https://www.spheron.network/blog/ai-gateway-litellm-portkey-kong-gpu-cloud/)
- [pgBackRest unmaintained — PG backup tools compared 2026 (DEV)](https://dev.to/kunal_d6a8fea2309e1571ee7/pgbackrest-is-no-longer-maintained-3-postgresql-backup-tools-compared-for-production-2026-4p1c) · [Bytebase — Top OSS Postgres Backup 2026](https://www.bytebase.com/blog/top-open-source-postgres-backup-solution/) · [Restic + Backblaze B2 quickstart](https://help.backblaze.com/hc/en-us/articles/4403944998811-Quickstart-Guide-for-Restic-and-Backblaze-B2-Cloud-Storage) · [Cloudflare R2 vs B2 vs Wasabi vs S3 (Onidel)](https://onidel.com/blog/cloudflare-r2-vs-backblaze-b2)
- [Trivy complete guide 2026 (Dashen)](https://dashen-tech.com/en/dev-tools/trivy-security-scanner-guide/) · [Best OSS secret-scanning tools 2026 (AppSecSanta)](https://appsecsanta.com/sca-tools/best-open-source-secret-scanning-tools) · [trivy-action supply-chain compromise Mar-2026 (CrowdStrike)](https://www.crowdstrike.com/en-us/blog/from-scanner-to-stealer-inside-the-trivy-action-supply-chain-compromise/)
- [Windmill vs Temporal 2026 (OpenAlternative)](https://openalternative.co/compare/temporal/vs/windmill) · [AI Workflow Orchestration Tools 2026 (DigitalApplied)](https://www.digitalapplied.com/blog/ai-workflow-orchestration-tools-2026-comparison)
- [Cloudflare Tunnel docs](https://developers.cloudflare.com/tunnel/) · [Protect your origin server (Cloudflare)](https://developers.cloudflare.com/fundamentals/security/protect-your-origin-server/) · [Cloudflare Free plan limits 2026](https://eastondev.com/blog/en/posts/dev/20251201-cloudflare-pricing-compare/)
- [Promptfoo vs DeepEval vs RAGAS 2026 (genai.qa)](https://genai.qa/blog/promptfoo-vs-deepeval-vs-ragas/) · [LLM Eval Frameworks — RAGAS/DeepEval/PromptFoo/Langfuse 2026 (helpmetest)](https://helpmetest.com/blog/llm-evaluation-frameworks/)
