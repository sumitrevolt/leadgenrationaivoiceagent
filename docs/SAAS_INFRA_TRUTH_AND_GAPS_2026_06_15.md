# SaaS Infra — SOURCE OF TRUTH + Remaining Gaps (2026-06-15)

> **Ye doc 2 prior gap-analyses ko RECONCILE karta hai** aur unme jo dedup-errors the
> woh theek karta hai. Agar dobara "SaaS infra gap dhoondo" karna ho — **pehle ye padho**,
> 4th repeat se bacho.
>
> Reconciles: `Infra_BestStack_GapAnalysis_2026-06.md` (G1–G8) + `Infra_Upgrade_Activation_Runbook.md`
> + `SAAS_INFRA_GAP_ADDITIVE_2026_06_15.md`. Method: dono docs + ACTUAL repo grep/code-read
> (`.github/workflows`, `app/`, `docker-compose.*`, `evals/`) + 2 fresh repo-grounded research
> agents (top SaaS boilerplates + candidate validation).

---

## TL;DR (billionaire-lens, brutally honest)

1. **Tera INFRA layer SATURATED hai. Genuine infra gap = lagbhag ZERO.** Top SaaS blueprints jo
   recommend karte (CI/CD+health-gate+rollback, Trivy CVE+SBOM, SOPS secrets, full Prom/Grafana/
   Loki/Tempo obs + exporters + celery-exporter + Flower, durable Celery + event-sourced process-
   engine, Qdrant RAG, LLM-observability + promptfoo eval CI, semantic cache, plan-tier rate-limit,
   k6 load + chaos, Ansible rebuild, offsite backup, Cloudflare edge) — **sab pehle se code me hai**
   (kuch active, kuch gated-dormant). Iss layer pe aur token/paisa MAT jala.
2. **Asli remaining value 2 cheezein hain — NAYA infra nahi:**
   (a) **ACTIVATION** — bahut saari powerful cheezein OFF padi hain sirf tere account/creds/DNS ke
   intezaar me (Cloudflare, offsite R2/B2, PostHog, LLM-obs, Razorpay live keys). Ye build-karne ka
   nahi, switch-on karne ka kaam hai — aur yahi highest ROI hai.
   (b) **APP/SaaS layer white-space** (infra nahi) — boilerplate-repo research me yahi nikla:
   **MFA/2FA, magic-link + OAuth-social login, "login as customer" impersonation, customer-facing
   webhooks.** Ye genuinely absent + free + zyadatar no-creds hain.
3. **Iss session me 1 genuine INFRA gap SHIP hua** (niche §A) — baaki sab ya activation hai ya app-layer.

---

## §A — IS SESSION ME SHIPPED (genuine, creds-free, working)

### ✅ External off-VPS uptime watchdog — `.github/workflows/uptime.yml`
- **Kyun genuine gap tha:** saara monitoring (Gatus, Uptime-Kuma, Prometheus, Alertmanager,
  self-hosted ntfy) **VPS ke ANDAR** chalta hai. VPS hi mar jaaye (3 prod-downs ka exact scenario)
  to ye sab bhi mar jaate — bahar se KOI alert nahi. Dono research agents ne isे **#1 ROI gap**
  confirm kiya ("monitor your monitoring from outside the host" = 2026 reliability best-practice).
- **Kya karta:** GitHub ke infra (VPS se independent) pe har ~10 min `leadsgenai.in/health` ko
  BAHAR se ping → 200 + `environment:production` check → 3x retry (flap-safe) → fail pe GitHub
  khud repo-owner ko email karta (off-VPS channel jo VPS-down me bhi kaam karta). Optional: public
  `ntfy.sh` topic push (repo variable `NTFY_TOPIC` set karo). **Push hote hi live, zero creds.**
- **Proven:** probe-logic live site pe test ki — `http_code=200`, `"environment":"production"` matched.
- **Belt-and-suspenders (2-min, recommended):** GitHub cron ~5-15min jitter leta. Iske SAATH ek
  **UptimeRobot free** (50 monitors, 5-min, true off-host, email/push) `/health` pe laga de —
  research agent ne ise sabse reliable-free option bola. Dono milke proper external coverage.

---

## §B — DEDUP CORRECTIONS (prior docs me galat tha)

| Prior claim | Reality (verified) |
|---|---|
| `SAAS_INFRA_GAP_ADDITIVE` #1: "promptfoo → koi match nahi, DeepEval+Promptfoo add karo" | **GALAT.** `evals/promptfooconfig.yaml` + `.github/workflows/llm-eval.yml` **pehle se hain** (commit 87ad474). Eval CI advisory-live hai. DeepEval add karna = duplicate-ish; bas promptfoo asserts bharo. |
| `SAAS_INFRA_GAP_ADDITIVE` Tier-3: "OTel tracing idle, activate" | OTel app-tracing **wired** (`app/observability_otel.py` + `requirements-otel.txt`); LLM-obs bhi `free_ai.py` + `structured.py` me wired (`observability_llm.py`). Bas `ENABLE_OTEL=1`/`ENABLE_LLM_OBS=1`. |
| Both docs treated semantic-cache as "to build" | **Ban chuka** — `app/cache/semantic_cache.py` + tests + `/metrics` + chatbot-wired (`SEMANTIC_CACHE` flag, OFF default). |

---

## §C — APP/SaaS-layer white-space (repo-grounded; 3 ab SHIPPED)

Repo-grounded research (open-saas, BoxyHQ, ixartz, supastarter, makerkit) — ye **infra docs me kabhi
nahi aaya** kyunki ye auth/account layer hai. Status (sab verified-absent the; 3 is session me ban gaye):

| Item | Top repos | Status | Flag (OFF default) |
|---|---|---|---|
| **"Login as customer" impersonation** | ixartz, makerkit, supastarter | ✅ **SHIPPED** — super_admin-only, 30-min token, har start/stop AuditLog, `/app/impersonate` UI, XSS-safe | `IMPERSONATION=1` |
| **Magic-link login** | open-saas, supastarter, makerkit | ✅ **SHIPPED** — single-use (redis NX) 15-min, no email-enumeration (body+timing), Hostinger SMTP, login.html UI | `MAGIC_LINK=1` |
| **LLM cost/budget governance** | AI-infra 2026 | ✅ **SHIPPED** — per-scope daily call+token caps + emergency hard-kill, free_ai wired, /metrics, fail-open | `LLM_BUDGET_GUARD=1` / `LLM_BUDGET_HARD_KILL=1` |
| **MFA / 2FA (TOTP)** | supastarter, makerkit, BoxyHQ | ⚠️ **PARTIAL** — admin login me already hai (`ADMIN_TOTP_SECRET` + `app/utils/totp.py`). Customer-side 2FA baaki | `ADMIN_TOTP_SECRET` |
| **Customer-facing webhooks** ("subscribe to events") | BoxyHQ (Svix), open-saas | ⏳ **TODO** — sellable feature; tere outbox/idempotency primitives reuse | — |

**Shipped (is session) — verify:** 28/28 pytest green · py_compile + import OK · 5-finding adversarial
security review (0 false-positive) — sab fix. Sab flag OFF default = prod untouched jab tak enable na ho.
**Baaki:** customer-side 2FA + customer-facing webhooks (jab zaroorat ho).

---

## §D — ACTIVATION CHECKLIST (sabse zyada ROI — code ready, sirf switch ON)

Ye "gaps" nahi — ye **ready-but-OFF** hai. Yahi asli leverage hai:

1. **Razorpay live keys** (🚨 P0 — pehla paid customer se pehle MUST) — `.env` me asli `rzp_live_...`.
2. **Cloudflare free edge** (`docker-compose.edge.yml`) — origin-IP hide + WAF + CDN + DDoS. CF account + tunnel token. **Single biggest free security+perf win.**
3. **Offsite backup** — R2/B2 (10GB free) bucket → `RCLONE_REMOTE` set. `pg_backup.sh` already wired.
4. **LLM observability** — `ENABLE_LLM_OBS=1` (+ Langfuse cloud-free keys ya OTel→Tempo). Code wired.
5. **PostHog** — product-analytics + session-replay + flags (cloud-free key). Code wired.
6. **UptimeRobot** — §A belt-and-suspenders (2-min signup).

---

## §E — Validated SKIP (dobara mat suggest karna — research-confirmed)

- **cosign image signing + SLSA provenance** — Trivy CVE + SBOM already; single-VPS pe koi
  signature-VERIFY karne wala downstream nahi (no k8s admission controller) → ceremony without verifier.
  Revisit only at k8s/multi-node/enterprise.
- **DBOS Transact** — event-sourced `process_engine.py` + durable Celery already covers durability;
  migration-cost > marginal gain. Redundant.
- **Temporal/Windmill/Inngest, Coolify/Dokploy/Kamal, Renovate, pgBackRest/Barman, new auth stack
  (Keycloak/Authentik), self-host PostHog/Langfuse (ClickHouse/Kafka = VPS marega), SAML SSO+SCIM,
  i18n, dedicated feature-flag service** — sab duplicate ya over-engineering for solo single-VPS India SaaS.

---

## Sources (fresh repo-grounded research, 2026)
- Top SaaS boilerplates: [wasp-lang/open-saas](https://github.com/wasp-lang/open-saas) · [boxyhq/saas-starter-kit](https://github.com/boxyhq/saas-starter-kit) · [ixartz/SaaS-Boilerplate](https://github.com/ixartz/SaaS-Boilerplate) · [makerkit](https://makerkit.dev/nextjs-saas-starter-kit) · [supastarter](https://supastarter.dev/)
- "Monitoring the monitor" (off-host watchdog): https://dohost.us/index.php/2026/04/25/monitoring-the-monitor-who-watches-the-watchmen/
- cosign keyless GHA: https://www.qcecuring.com/blog/sigstore-cosign-keyless-github-actions
- DBOS Transact: https://www.dbos.dev/dbos-transact
- Runtime AI governance 2026: https://accuknox.com/blog/runtime-ai-governance-security-platforms-llm-systems-2026
