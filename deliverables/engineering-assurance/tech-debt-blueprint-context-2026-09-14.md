# Tech-Debt / Blueprint Context — Revenue Sprint Master Blueprint

**Date:** 2026-09-14 · **Author:** Docu (Technical Writer · Engineering Assurance Team)
**Baseline:** git HEAD `20e4180b` · prod `/health.version` `95245ce8`
**Task:** #5 — "Update the master blueprint for the 7-day ₹5,00,000 sprint"
**Evidence labels:** `PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`

---

## 1. Which file is the master blueprint — and why

**Winner: `7_DAY_REVENUE_PLAN.md`** (repo root, previously 9,643 B → now the authoritative revenue-sprint
blueprint). It was **updated in place**; the filename was **kept** so existing links
(`docs/REVENUE_SPRINT_AUTOPILOT.md`, `progress.md`) do not break.

**Why this file:**
1. It is **the** 7-day revenue plan — the owner asked for a *7-day ₹5L* blueprint, and this is the day-by-day
   plan for exactly that.
2. `docs/REVENUE_SPRINT_AUTOPILOT.md` (which already carried the ₹5L goal) explicitly defers to it as
   *"`7_DAY_REVENUE_PLAN.md` — day-by-day plan"*, i.e. the autopilot already treats it as the plan.
3. It is root-level and discoverable; its satellites (`DAY_0_REVENUE_BASELINE.md`, `REVENUE_BLOCKERS.md`)
   are clearly subordinate inputs.
4. It was **stale** (₹9,995 target, 2026-08-22) — the correct thing to do was update it, not add a 6th doc.

### ⚠️ SSOT violation found (report it, don't hide it)

The repo has **no single "master blueprint"** — the phrase is overloaded across **three** domains:

| "Blueprint"-like doc | Domain | Status | Disposition |
|---|---|---|---|
| `7_DAY_REVENUE_PLAN.md` | Revenue sprint | was STALE | **→ WINNER (updated in place)** |
| `docs/ARCHITECTURE_BLUEPRINT.md` (+ code `app/platform/blueprint_graph.py`) | Architecture | self-declared `STALE` narrative; count authority = code | **left alone** — different domain; explicitly disambiguated in the winner's banner |
| `docs/context/ADMIN_CLI_5_31_MASTER_PLAN_2026-09-11.md` | Admin CLI / 31-agent build | `PLAN` (awaiting owner) | **left alone** — not a revenue doc |

**Recommendation to the owner:** keep the naming split explicit — **"Master Blueprint" = the architecture
graph** (`blueprint_graph.py`); **"Revenue Sprint Master Blueprint" = `7_DAY_REVENUE_PLAN.md`**. Never let one
name mean two SSOTs. (See `docs/AGENT_WORK_RULES.md` R12 — a deliberate design must not be "fixed" into a
duplicate.)

### Evidence labels used to decide (verified this session)

- `data/invoices.jsonl` is **prod-resident, absent from the local tree** — only `data/revenue_attribution.jsonl`
  is local, and it is **not money** (`amount_inr` = 0 on 25/27 rows).
- `app/platform/team.py` `STAFF` = **31 keys** (parsed) — `CODE-PRESENT`.
- `AGENTS.md` and `CLAUDE.md` are **byte-identical** (md5 `7f7bbc4b…`, 37,371 B each).
- `app/api/automation_flags.py` exists; the brief's `app/platform/automation_flags.py` **does not**.
- `app/platform/coordination_hub_auth.py:23` `_KNOWN_TOOLS` omits `openclaw`/`workbuddy`/`codex`.

---

## 2. What I changed (the winner, `7_DAY_REVENUE_PLAN.md`)

Full rewrite in place, restructured so the most useful information leads:

| Section | Content added / corrected |
|---|---|
| **Authority banner** | Declares the SSOT, lists superseded docs, disambiguates from the architecture "Master Blueprint". |
| **§0 TL;DR** | Honest verdict up front: ₹5L **not reachable on current rails**; ceiling ≈ ₹10k–₹25k. |
| **§1 Baseline** | ₹5,997 collected FY 2026-27 / 16 invoices / 13 voided / no invoice since Aug 24. **Corrected** the stale ₹7,997 / ₹3,998 figures and the retired "sole source of truth" claim. Noted `data/revenue_attribution.jsonl` is **not money** and the ledger is prod-resident. |
| **§2 Target + arithmetic** | Units required (251/84/51/mixed 102); funnel volume (85,000 contacts) vs rail capacity (875/week) ⇒ **97× gap**; realistic ceiling ₹10k–₹25k; every rate labelled **ASSUMPTION**. |
| **§2e OmniRoute/combo** | Filled from Archi's verified numbers (ADR-190; 14-vs-12 email-key defect; `generate()` 2-hop; OmniRoute = ₹0 revenue). Was left explicitly PENDING until his input arrived — not fabricated. |
| **§3 Owner gates** | The **two** gates (Smartflo DID→VOICE destination; UPI via `/app/inbox`). Telegram flagged **not** a blocker. **Corrected** the owner's "inbound calls are arriving" as **falsified**. |
| **§4 SSOT map** | One truth per domain + the competing duplicates that must die (task/runtime/roster/config/combo/money/alerts). |
| **§5 Automation** | 31-agent verdict (defined ✅ / armed 🟡 / **proven-executing ❌**); `dev_workers` 0 rows; `_IDEMPOTENCY` process-local; `_KNOWN_TOOLS` gap. |
| **§6 Token burn** | Cause (duplicate 37 KB file, 940 KB append-only logs, stale handoffs) + **policy** (2-file truth rule, archive, ≤16 KB/turn budget). |
| **§7 Compliance spine** | TRAI DND / consent / DPDP / opt-out / tenant isolation; fail-CLOSED; DND re-hardened 2026-09-14T10:48Z — **do not re-raise**. |
| **§8 Day-by-day** | Re-based on the two gates; no day may begin with a §7 violation. |
| **§9 Principles** | Evidence-first, gates-first, token budget, owner-gated actions. |

---

## 3. Competing docs marked superseded-as-authority (kept, not deleted)

| Doc | Banner added | Why |
|---|---|---|
| `DAY_0_REVENUE_BASELINE.md` | ✅ | Overstated figures (₹7,997 / ₹3,998) now STALE; self-declared SSOT retired. |
| `REVENUE_BLOCKERS.md` | ✅ | Predates the "only 2 owner gates block revenue" finding; Telegram wrongly implied as blocker. |
| `docs/REVENUE_SPRINT_AUTOPILOT.md` | ✅ | Kept as the engine doc; no longer the blueprint authority. |
| `automation-fix-overview.md` | ✅ | Historical log; its "ISSUE-237 removed" claim is **FALSE** (step still at `tests.yml:67-75`). |

No files were deleted. No commit / push / deploy was performed.

---

## 3b. Doc-truth correction applied — `AGENTS.md` / `CLAUDE.md` branch-protection claim

**Flagged by Archi (task #2, ADR-192); verified independently by me.**

- **Claim (was):** `AGENTS.md:137` / `CLAUDE.md:137` — *"GitHub main = PR-only (branch protection +
  `no-commit-to-branch` hook; direct push refused)."*
- **Falsified by the platform API** (`PRODUCTION-PROVEN`):
  `gh api repos/sumitrevolt/leadgenrationaivoiceagent/branches/main/protection` → **HTTP 404 "Branch not
  protected"**; `gh api …/rulesets` → **`[]`**. Zero required status checks, zero rulesets.
- **Net effect:** the `no-commit-to-branch` hook is a **local** control only; **every CI gate is advisory**
  at the platform level — a red check does not by itself block a merge.
- **Correction applied** (identically in both files, preserving the `tests/test_1000_engineers_skill.py:67`
  byte-identity invariant — both now `cbce2e00…`, 37,825 B, `AGENTS.md == CLAUDE.md` → `True`): reworded to
  *"PR-only by convention + local `no-commit-to-branch` hook … platform-level branch protection is NOT
  configured (404); all CI checks are advisory until an admin adds a required check/ruleset."*
- **Why this is the canonical example for `doc_truth_guard.py`:** a doc asserting a platform control that
  the API reports as absent. The guard should fail the build when a doc claims a platform control the API
  does not confirm.

### 3b.1 Two further stale "hot facts" corrected in the same files (2026-09-14)

Found by team-lead; re-verified by me before editing.

- **Stale prod SHA.** `AGENTS.md:137` / `CLAUDE.md:137` read *"Prod `/health`=`0b848b34`"* (probe
  2026-09-10) while prod is now **`95245ce8`** (`PRODUCTION-PROVEN`, Rex probe **2026-09-14T14:11Z**).
  Corrected; `0b848b34` now appears **once**, only inside the labelled correction note (5→1). The stale
  SHAs `d0183bf1` and `79291e2b` are **gone** (0 occurrences each).
- **Stale lineage warning.** The 🔴 LINEAGE WARNING (2026-09-10) was computed against commits that are no
  longer HEAD/prod. **Re-verified independently (`git`, 2026-09-14):**
  - Deployed = `95245ce8` (= `origin/main` tip) · local HEAD = `20e4180b`
  - `git merge-base --is-ancestor 95245ce8 20e4180b` → **exit 1 (NOT an ancestor)**
  - merge-base = `071dc31b` · prod-only = **2** (`95245ce8` branch-consolidation docs + `9f128925` WAHA
    inbound check) · local-only = **1** (`20e4180b`)
  - **Verdict: still DIVERGED** — the warning's *conclusion* holds, but its *inputs* were stale. Corrected
    with the real result and marked "supersedes the 2026-09-10 version". The safe rule is unchanged:
    **base migration/deploy branches on `95245ce8` (= `origin/main`), not local HEAD.**

**Post-edit state:** both files `c03888a1…`, **37,962 B**, `AGENTS.md == CLAUDE.md` → `True`. The mirror
test's other invariants (`thousand-engineers` present in both) still hold. This is the same failure mode as
the branch-protection lie — a scary-looking claim nobody re-checked — now closed.

---

## 4. Residual doc-debt (for the owner / follow-up)

| Priority | Item | Why |
|---|---|---|
| P1 | **Collapse `CLAUDE.md` to a 1-line pointer to `AGENTS.md`** — must **retire `tests/test_1000_engineers_skill.py:67`** (byte-mirror assertion) in the *same* change, and **keep its startup-protocol coverage** (assert the startup-protocol section exists in `AGENTS.md` **and** that `CLAUDE.md` points at it). **Keep the `CLAUDE.md` filename** — Claude Code reads it by name; a pointer preserves that contract, a deletion does not | halves the per-turn context tax; test-enforced coupling makes it a 2-file change, not 1 |
| P1 | **Create `docs/context/STATE.md` (≤8 KB)** as the single per-turn context file | the 2-file truth rule has no home yet |
| P1 | **Archive `progress.md` (524 KB) + `docs/SESSION_LOG.md` (416 KB)** to dated files | ~235k tokens of append-only history |
| P2 | **Generate `docs/AGENT_REGISTRY.md` from `team.py`** | doc says 19 agents, code has 31 — a lying SSOT |
| P2 | **Refresh `SESSION_HANDOFF.md` / `ACTIVE_WORK.md`** to real HEAD/prod SHAs | both STALE (`33189b70`/`0b848b34`, `658fc20a`) |
| P2 | **`doc_truth_guard.py` CI check** | fail the build when a doc contradicts a code SSOT |
