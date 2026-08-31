# Task Observer Log

## 2026-08-18 Production automation audit
- Tool sequence: health/Redis queue probes -> source read of scheduler/calling/voice_launch -> surgical hotfix deploy -> worker log verification -> billing failure falsification -> tests/prod_check/secrets.
- Context cue: platform_dial relies on voice session counters; scheduler queueing a Celery campaign without create_voice_session can silently reuse a stale full session and stop at session_limit_reached.
- Unwritten convention: Product-1 marketing client ids are not always SQL FK ids; BillingRecord must normalize to SQL clients.id before insert.
- Error pattern: bulk selection loops over thousands of prospects must never call per-row full-file rewrite helpers; collect marks and flush bulk.
- Skill opportunity: create a repo-specific production-hotfix skill/checklist covering env flag audit, Redis session counters, surgical-vs-canonical deploy drift, and mandatory post-hotfix image deploy follow-up.

## 2026-08-31 Desktop multi-app sync and OmniRoute model proxy audit
- Context cue: WorkBuddy AI loads custom providers from `~/.workbuddy-ai/models.json` rather than `settings.json`; registering models requires the custom model schema array in `models.json`.
- Error pattern: Hermes Desktop and agent runtime require syncing `AppData\Local\hermes\provider_models_cache.json`, `auth.json`, and `config.yaml` to ensure provider and combo selection in GUI dropdowns.
- Architecture pattern: `scripts/claude_proxy.py` (port 22000) mediates Anthropic / Claude Desktop / WorkBuddy / Hermes requests, advertising `claude-omni-*` aliases and rewriting to `leadgen-*` combos for upstream OmniRoute gateway (:20128).
- Cross-platform file locking: SQLite databases on WSL Linux filesystem must be seeded via `wsl.exe python3` to avoid Windows 9P UNC network file-lock collisions.
