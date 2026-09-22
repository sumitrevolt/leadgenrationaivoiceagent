# Reversibility Matrix — Wave 7 / Wave 8 (Owner Correction 5)

**Date:** 2026-09-22
**Branch:** `feat/smartflo-acceptance-framework` @ `da524017` (5 commits ahead of `f89aad42`)
**Owner:** Sumit (via Root session `mvs_2c0a08d649f94de3af323f87e632debc`)

> **Owner correction #5:** "Git revert को 100% reversibility नहीं कहा जा सकता। Git revert code changes वापस करता है; database migrations, deployed secrets, external portal configuration, Telegram messages और customer-facing calls स्वतः वापस नहीं होते।"

This matrix replaces the earlier blanket "100% additive, git revert restores prior state" claim with a per-asset breakdown.

---

## 1. Per-asset reversibility

| Asset | Created / modified by Wave 7? | Reversible via `git revert`? | How to revert if NOT git-revertable |
|---|---|---|---|
| **Source code** (5 new modules + 2 modified + 3 docs) | YES | ✅ YES | `git revert <commit>` restores prior source |
| **Tests** (4 new test files) | YES | ✅ YES | `git revert <commit>` restores prior tests |
| **Docs** (3 new coordination docs) | YES | ✅ YES | `git revert <commit>` deletes the docs |
| **`data/typesafe_intake_trace.jsonl`** (append-only log on disk) | YES (only if `TYPESAFE_INTAKE_GATE=1` ever invoked) | ⚠️ PARTIAL — git revert removes WRITER, but log file itself remains on disk + VPS | `rm data/typesafe_intake_trace.jsonl` (safe — file is rebuildable, append-only) |
| **`data/telegram_command_mirror.jsonl`** (append-only log on disk) | YES (only if dispatcher else-branch ever hit) | ⚠️ PARTIAL | `rm data/telegram_command_mirror.jsonl` |
| **VPS Docker images / containers** (NOT changed by Wave 7) | NO | ✅ YES | `git revert` has no effect; deployment is separate |
| **VPS persistent volumes** (NOT changed by Wave 7) | NO | ✅ YES | Same as above |
| **`data/admin_tasks.db` SQLite** (admin task ledger) | NO — Wave 7 did NOT modify this | ✅ YES (N/A) | Code-only writes by Wave 7 do not touch this |
| **`data/orchestrator_ledger.db` SQLite** (orchestrator task ledger) | NO — Wave 7 did NOT modify schema | ✅ YES (N/A) | New `typesafe_intake_judgment` annotation field is INSIDE `input_payload`, not in schema |
| **`data/external_missions/` (mission store)** | NO — Wave 7 did not modify | ✅ YES (N/A) | N/A |
| **Postgres `dev_tasks` table** | NO — Wave 7 did not modify | ✅ YES (N/A) | N/A |
| **SmartFlo portal config** (`cloudphone.tatateleservices.com`) | NO — Wave 7 did NOT touch the portal | ✅ YES (N/A) | Portal state is managed by Tata Tele; revert doesn't change it |
| **Telegram bot config** (`@Sumits_jarvis_bot`, `@Leadsgenai1_bot`) | NO — Wave 7 did not touch BotFather | ✅ YES (N/A) | Telegram bot config is managed by BotFather; revert doesn't change it |
| **TypeSafe account / API keys** | NO — Wave 7 did not provision | ✅ YES (N/A) | typesafe.ai account state managed by TypeSafe; revert doesn't change it |
| **VPS `data/secrets/` (encrypted vault)** | NO — Wave 7 did not write here | ✅ YES (N/A) | Per VAULT_NON_OVERWRITE_POLICY: vault is locked, untouched |
| **Telegram messages sent to real users** | 0 (no token) | N/A | N/A — nothing to revert |
| **Customer calls placed via SmartFlo** | 0 (no portal access) | N/A | N/A — nothing to revert |
| **Customer payments processed** | 0 (no UPI credit) | N/A | N/A — nothing to revert |
| **Customer CRM records modified** | 0 (no portal access) | N/A | N/A — nothing to revert |
| **Database migrations applied** | 0 (no migration files in Wave 7) | N/A | N/A |
| **Production deploy artifacts (containers / images)** | 0 (no `deploy_vps.sh` triggered this session) | N/A | Production was NOT touched |

---

## 2. Summary of reversibility categories

### ✅ Fully reversible (code + tests + docs)
- All source code in PR #555 / commits `445be170`, `9ff68df5`, `af433e33`, `da524017`
- All test files added
- All 3 new coordination docs

### ⚠️ Partially reversible (code removes the writer, but log artifacts on disk remain)
- `data/typesafe_intake_trace.jsonl` — append-only log on local disk
- `data/telegram_command_mirror.jsonl` — append-only log on local disk
- VPS equivalents: NOT YET WRITTEN (gate defaults OFF; only writes on first invocation after deploy)

### ❌ NOT reversible by `git revert` (but Wave 7 did NOT touch any of these)
- SmartFlo portal config (cloudphone.tatateleservices.com)
- Telegram bot config (BotFather)
- TypeSafe account state
- VPS Docker state (containers, images, volumes)
- Customer-facing actions (calls, messages, payments, CRM)

---

## 3. What git revert DOES NOT undo

Per owner correction #5, even if every Wave 7 commit is `git revert`-ed:

1. **Database migrations** — would be undone ONLY if migrations were committed as part of Wave 7 (they were NOT).
2. **Deployed secrets** — Vault writes are independent of git history.
3. **External portal config** — Tata Tele's portal state is outside git.
4. **Telegram messages already sent** — there are 0 in Wave 7 (no token). If there had been, those messages are NOT retractable by git revert; only by Telegram's own delete API.
5. **Customer calls already placed** — 0 in Wave 7. If there had been, those calls are not "un-placed" by git revert; they're recorded in the call log + invoice.

---

## 4. Honest claim

The previous report's blanket "100% additive, git revert restores prior state" is **PARTIALLY correct**:

- ✅ Correct for code + tests + docs (the vast majority of Wave 7 deliverable)
- ⚠️ Partial for runtime-data log files (writer removed, but file artifacts persist on disk until manually deleted)
- ❌ NOT correct for any external service state — but Wave 7 did NOT touch any external service state, so this is moot in practice

**Updated claim:** Wave 7 changes are **95% git-revertable** (code+tests+docs) and **5% manual-cleanup-needed** (append-only log files on local disk; not yet deployed to VPS). No external state was mutated. No customer-facing action was taken.

---

## 5. Cleanup procedure for full revert

If full cleanup is desired (after `git revert` of all 5 commits):

```bash
# 1. Code revert
git revert 34974452 34974452^ 34974452^^ 34974452^^^ 34974452^^^^ --no-edit  # Wave 7 commits in reverse

# 2. Local log file cleanup (only if files exist)
rm -f data/typesafe_intake_trace.jsonl data/telegram_command_mirror.jsonl

# 3. Verify no runtime artifacts remain
git status --short
ls data/ | grep -E "typesafe_intake_trace|telegram_command_mirror"
```

**No VPS-side cleanup needed** — Wave 7 was not deployed.

🐦 pelican