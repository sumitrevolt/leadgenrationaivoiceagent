# Task Observer Log

## 2026-08-18 Production automation audit
- Tool sequence: health/Redis queue probes -> source read of scheduler/calling/voice_launch -> surgical hotfix deploy -> worker log verification -> billing failure falsification -> tests/prod_check/secrets.
- Context cue: platform_dial relies on voice session counters; scheduler queueing a Celery campaign without create_voice_session can silently reuse a stale full session and stop at session_limit_reached.
- Unwritten convention: Product-1 marketing client ids are not always SQL FK ids; BillingRecord must normalize to SQL clients.id before insert.
- Error pattern: bulk selection loops over thousands of prospects must never call per-row full-file rewrite helpers; collect marks and flush bulk.
- Skill opportunity: create a repo-specific production-hotfix skill/checklist covering env flag audit, Redis session counters, surgical-vs-canonical deploy drift, and mandatory post-hotfix image deploy follow-up.
