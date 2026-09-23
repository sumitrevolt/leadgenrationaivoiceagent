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

---

## 2026-09-23 M11 first-wave audit + continuous TypeSafe execution (MiniMax-M3 root session)

**Session**: `mvs_e2a03d4d24264fe9950e50e69d88d864` · **Model**: MiniMax-M3 (Mavis orchestrator) · **Owner correction applied**: M00A + P0–P5 from `docs/OWNER_DIRECTIVE_2026-09-22.md`

### Audit snapshot (LOCAL only — VPS_UNREACHABLE_THIS_SESSION)

- Repo HEAD `bbf8b5e6` on `main` (single-canonical-AGENTS.md migration commit). `origin/main` `3698732e`; ahead 1 commit.
- 7 worktrees (`git worktree list`); 3 locked/drained; 3 active code-change (`main`, `feat/smartflo-acceptance-framework`, `codex/typesafe-probe-semantics`) — at M06 ≤3 cap.
- Uncommitted local: `M command_center/data/messages.jsonl`, `M skill-observations/log.md`, `?? command_center/scripts/pilot_sep22_2000_dispatch.py` — per §2.5 R7 NEVER bulk-add.
- Python launcher broken at `AppData\Local\Programs\Python\Python311\python.exe` (0x80070002); `C:\Users\Ratanshila\.local\bin\python3.exe` works.
- Env vars loaded (NAMES only): `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN` (user-scope); `TYPESAFE_API_KEY` (process-scope).

### TypeSafe 4-slot KeyManager — actual state (P2 evidence, single probe)

- `credential_state()` reports `state=PRESENT`, `enabled=True`, `pool_size=4`, `pool_fingerprints=['2e13ca55f7f8','d6607c44af49','c01eb8b3f8fa','570c70192ca5']`, `model=jev-latest`, `source=env:TYPESAFE_API_KEY`.
- All 4 fingerprints load via `app/platform/key_manager.py` (Fernet-encrypted vault, TS_A..TS_D slots). Vault-backed slot presence verified; **independent per-key live API call NOT executed this session — must not claim "four live keys verified"** until each is probed (P2 correction).
- Earlier "hidden key in `.env.production.local`" framing in this session's draft audit was **incorrect** — that path is `_load_all_keys()` source #6, not an orphan. Correction captured here.

### Canonical governance migration (M05) — VERIFIED COMPLETE on local

- `AGENTS.md` = 15,635 bytes (lean canonical, §0 target ≤12 KB).
- `CLAUDE.md` = 944 bytes (3-line redirect stub).
- `docs/OWNER_DIRECTIVE_2026-09-22.md` = 126,429 bytes; SHA-256 = `803A4683B94F6B8CF41DCCB5CB6DA461B3DEF108C43794585D256F78A5CAB6EA` — byte-equivalent with the Downloads-supplied master copy.
- 54 `CLAUDE.md` references in repo — 47 docstring/comment, 1 active loader (`scripts/project_context.py` reads CLAUDE.md as a fallback), 6 `scripts/run_ship*.ps1` (info-only), 1 OKF 404 test. M05 says complete removal may not be compatible — accept per AGENTS.md §6 migration note.

### ChatGPT/Claude worker reassignment (M01) — PARTIAL

- `scripts/claude_proxy.py` (14.8 KB) + `scripts/start-claude-omniroute.ps1` (6.8 KB) = client-compat alias layer (loopback `:22000`), `claude-omni-* ⇒ leadgen-* ⇒ OmniRoute ⇒ MiniMax-primary upstream`. Not a paid-Claude dependency.
- `app/dev_control/external_agents/runner/claude_exec.py` (9.1 KB) + `cursor_exec.py` (12.4 KB) = subprocess CLI runners for dev-mission code review, wired into `runner/loop.py`. **Default OFF** — `runner_enabled()` requires BOTH `orchestrator_enabled()` AND `EXTERNAL_AGENT_RUNNER=1`; neither set → OFF. M01-compliant by default.
- `app/voice_agent/free_ai.py` SDK chain (AGENTS.md §2.4 flags it) — NOT source-audited this session. Parked.

### Action executed (TypeSafe multi-pass evidence trail)

1. **Stage 1 — intake** (`tsi-bb1382102f4b`, model `jev-1.13.0`, latency 4.7s, ok=true). Question: highest-leverage reversible authorized next step given audit. Answer: `refresh_agents_md_section1` P=0.60 (runner-up `voice_agent_sdk_audit` 0.26, `test_subset_preflight` 0.13, `memory_observations_write` 0.01). Execution_risk score 1.66/4 (low-moderate, conf 0.27).
2. **Stage 2 — pre-edit QA** (`tsi-d31bd993210a`, latency 30.8s, ok=true). Q: minimal correct refresh? A: `yes_minimal` P=0.97 (conf 0.96). drift_surfaced=0.72. broke_anything=0.14. STRONG GREEN.
3. **Edit applied** — single-line replacement in `AGENTS.md` §1 (1 file, 1 insertion, 1 deletion). Per §6 commit/push NOT executed; awaiting owner instruction. Stale-token repo-wide grep = 0 hits.
4. **Stage 3 — post-edit QA** (`tsi-07e8363af4d1`, latency 14.6s, ok=true). drift_reduced=0.63, anything_broken=0.17, needs_revision=`no_revision` P=0.43 (conf 0.24; model split between no_revision 0.43 / needs_more_facts 0.28 / needs_rephrase 0.24). Decision: do not bloat §1 (its design = minimal pointer); route rich facts here instead.

### Known gaps / UNKNOWN this session

- VPS production (`srv1736379`, port 8000 = Docker `leadgen_app`, `/health.version` SHA, schedulers, WAHA, email, SmartFlo runtime) — UNKNOWN; no SSH/auth path from this Windows host.
- Per-key live API health for all 4 TypeSafe slots — pool presence verified, individual liveness NOT probed (P2 correction).
- `task_ledger` admin revenue routes / paid-customer count — NOT probed.
- Telegram dual-bot (LOCAL vs VPS) `getUpdates` ownership — NOT probed.
- Test suite green status — NOT run this turn.
- `app/voice_agent/free_ai.py` SDK chain — NOT source-audited.

### Next authorized execution candidates (parked — autonomous on owner green-light)

- Voice-agent SDK source audit (F7 closure, M01 verification).
- Per-slot TypeSafe liveness probe (4× `typesafe_status.py --probe` with key-rotation).
- Test subset preflight (migration-coverage tests) for M15 acceptance evidence.
- Owner instruction requested for: (a) commit/push of the AGENTS.md §1 refresh, (b) VPS SSH access for production-side M11 step, (c) commit/push of this observations.md entry.
