# Competitor Infra/Automation Research → Humara Upgrade Plan (2026-06-10)

## Competitors ka infra (deep web research)

### Smartlead / Instantly (cold email at scale — 5-7M mailboxes)
- **Adaptive sending queue**: naye leads na ho to follow-ups prioritize; follow-up queue khali to naye — volume CONSISTENT rehta (deliverability ke liye).
- **Sender-health rotation**: har mailbox ka health score; girte hi volume healthy mailbox pe shift.
- **Dedicated isolation**: per-customer isolated clusters; real-time blacklist monitoring; failover 99.98% uptime.
- **HUMARE LIYE**: adaptive queue pattern auto_outreach me partially hai (followups + daily run). Sender-health = single sender abhi (admin@leadsgenai.in) — future: 2nd domain warm-up. Blacklist monitor = free MXToolbox check cron (future).

### Vapi / Retell (voice AI — secondary humare liye)
- Sub-800ms latency pipeline, multi-provider STT/LLM/TTS (humara free_ai chain SAME pattern), WebSocket streaming, multi-region edge.
- **HUMARE LIYE**: already aligned (provider chain + circuit breaker + pre-synth greeting cache). Exotel websocket streaming pending (account product).

### Predis / AdBanao (AI content)
- Prompt → full content pipeline (ideas+caption+hashtags+schedule), brand assets reuse, Linux VPS isolation patterns.
- **HUMARE LIYE**: complete-post/variations/scheduler already match. Unka edge = video/reels render (heavy GPU, paid) — skip.

### 2026 SaaS infra best practices
- **Dedicated background workers** (web process kabhi heavy job na chalaye) — Celery/RQ, retry, DLQ.
- Event-driven triggers > fixed windows; idempotent jobs; IaC; multi-tenant isolation at DB layer.
- **HUMARA SABSE BADA GAP YAHI THA**: in-process scheduler web process me heavy jobs chalata tha — issi se 2026-06-10 ka prod-down bug hua (qa job ne HTTP block kiya; boot-grace patch lagaya tha). Fix = dedicated Celery worker+beat (code READY tha, dormant).

## Implemented is session me (UPGRADE)
1. **Celery durable scheduler switch (web/worker separation)**:
   - `worker.py`: legacy Cloud-Run/Vertex beat entries **gated `ENABLE_LEGACY_BEAT=1`** (default sirf `staff-*` jobs — warna brain-training/vertex/process_queue surprise-fire hote).
   - `docker-compose.vps.yml` worker+scheduler: in-network URLs HARDCODE (pgbouncer:6432/redis:6379 — .env ke 127.0.0.1 container me galat), root user (data mount), log rotation, pgbouncer dep, beat schedule file /tmp.
   - VPS switch: `WEB_CONCURRENCY=2` + `RUN_IN_PROCESS_SCHEDULER=0` + `--profile celery` → web sirf HTTP (kabhi block nahi), jobs durable worker me (retry+DLQ `dlq:failed_tasks`).
   - **Rollback**: .env me `RUN_IN_PROCESS_SCHEDULER=1` + `WEB_CONCURRENCY=1`, `docker stop leadgen_worker leadgen_scheduler`, app recreate.
2. Earlier sessions se already best-in-class (compare table): PgBouncer pooling ✓, Redis rate-limit/cache ✓, Prometheus+Grafana+Alertmanager(email)+Loki+Tempo+Uptime ✓, nightly pg_dump + restore-drill cron ✓, fail2ban+unattended-upgrades ✓, CI auto-deploy workflow (gated) ✓, staging compose ✓.

## Pending (creds/paisa chahiye — user action)
- Cloudflare free (WAF/CDN/Tunnel) — account. Offsite backups R2/B2 — creds. 2nd VPS HA — spend. Email 2nd domain warm-up — domain kharido. Blacklist monitoring cron — free, agla batch.
