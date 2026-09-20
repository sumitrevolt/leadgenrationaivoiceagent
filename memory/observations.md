# Task Observations & Learning Journal (LeadGen AI SSOT)

Canonical repository observations and learning notes consolidated from historical journals into `memory/`.

---

## 2026-08-18 Production automation audit
- **Tool sequence**: health/Redis queue probes -> source read of scheduler/calling/voice_launch -> surgical hotfix deploy -> worker log verification -> billing failure falsification -> tests/prod_check/secrets.
- **Context cue**: platform_dial relies on voice session counters; scheduler queueing a Celery campaign without create_voice_session can silently reuse a stale full session and stop at session_limit_reached.
- **Unwritten convention**: Product-1 marketing client ids are not always SQL FK ids; BillingRecord must normalize to SQL clients.id before insert.
- **Error pattern**: bulk selection loops over thousands of prospects must never call per-row full-file rewrite helpers; collect marks and flush bulk.
- **Skill opportunity**: create a repo-specific production-hotfix skill/checklist covering env flag audit, Redis session counters, surgical-vs-canonical deploy drift, and mandatory post-hotfix image deploy follow-up.

---

## 2026-08-31 Desktop multi-app sync and OmniRoute model proxy audit
- **Context cue**: WorkBuddy AI loads custom providers from `~/.workbuddy-ai/models.json` rather than `settings.json`; registering models requires the custom model schema array in `models.json`.
- **Error pattern**: Hermes Desktop and agent runtime require syncing `AppData\Local\hermes\provider_models_cache.json`, `auth.json`, and `config.yaml` to ensure provider and combo selection in GUI dropdowns.
- **Architecture pattern**: `scripts/claude_proxy.py` (port 22000) mediates Anthropic / Claude Desktop / WorkBuddy / Hermes requests, advertising `claude-omni-*` aliases and rewriting to `leadgen-*` combos for upstream OmniRoute gateway (:20128).
- **Cross-platform file locking**: SQLite databases on WSL Linux filesystem must be seeded via `wsl.exe python3` to avoid Windows 9P UNC network file-lock collisions.

---

## 2026-09-11 PILOT Learning Journal — VCS Evidence Sweeps
- **IS-RUN Sep-11 02:32 — VCS Evidence Sweep**:
  - Full VPS SSH evidence: call_loop DEAD 10d (mtime Aug-31, batch211 fail='from number not owned'), DID REVOKED, SIP env len=0, WAHA WORKING on 3111, auto_outreach.py 1959 lines grep=0 sendText.
  - Identified root cause: scheduler beat wiring stub (commit 94439e74 body), NOT field bug.
  - PIVOT to WAHA-only revenue rail identified.
- **IS-RUN Sep-11 06:30 — VCS Evidence Sweep #2**:
  - 26 WA sends = 0 genuine replies. WoodenStreet bot class-1 spam rejector.
  - hot-queue date-lock bug confirmed. Jiya UPI window expired.
  - 7 GHANTIs dispatched, 0 ACK within 30-min.
- **IS-RUN Sep-11 08:30 — VCS Evidence Sweep #3**:
  - Re-verified ALL evidence via live SSH @08:28 IST.
  - Discovered: whatsapp_automation NOT scheduled in hourly loop (0 _run_job call sites).
  - Pitch v2 PIVOT: no UPI in first msg → human handoff → UPI close (response to WoodenStreet spam-reject pattern).
  - 8 fresh GHANTIs dispatched with HARD 30-min deadlines, evidence-first acceptance.

---

## 2026-09-17 PILOT cron session (05:15 IST)
- **Lesson 1:** task PLAT-002 14h me evidence-collection par stall raha — pehle jab 4h+ no-ACK mila, turant supersede karna chahiye tha naki 24h baad. Root cause: jab platform ka task BLOCKED ho aur uska root cause sabse critical bottleneck hai, to use aur specific actionable task me replace karna bhi kaafi nahi — usko P0 priority + crisp deadline + expected evidence dena mandatory hai.
- **Lesson 2:** bots ke ACK time track karo — agar 5h+ bina evidence, no-progress, no-ACK hai, to escalate owner ko bina owner-direct blast bot ko reassign karo. PLAT-001 BLOCKED thi 4h+, fir bhi usme hi kaam chalta raha jabki PLAT-002 me swap karna tha.
- **Lesson 3:** VOBIZ credits checking (vobiz_monitor.log) = single point of truth hai for call-loop health. Har 5 min isko check karo — bus 20 entries mat dekho, monotonically banta hua balance=no_creds pattern mat dekho. Admin UI me indicator daalwao if possible.
