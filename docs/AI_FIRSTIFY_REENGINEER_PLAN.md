# AI-Firstify Re-Engineer Plan — leadgenrationaivoiceagent

Companion to docs/AI_FIRSTIFY_AUDIT_2026_06.md (2026-06-14). Fixes are ordered by value/risk. Phase A is safe + reversible (apply now). Phase B is low-risk cleanup. Phase C is production-risky and must go deprecate → verify → delete in small batches via the /ship loop.

Rule of engagement (from project /careful skill): nothing destructive runs without a one-word go-ahead. Every step below is written so it can be run as-is.

---

## Phase A — Context hygiene (SAFE, reversible, do first)

### A1. Trim CLAUDE.md to lean working memory
**Why:** 462 lines today, mostly dated "BATCH ✅ LIVE" entries; line 3 already says keep it lean and send dated history to docs/SESSION_LOG.md.

**Keep in CLAUDE.md (current-state working memory only):**
- Token-discipline header · User Preferences
- Product (current direction) · Paid tiers / pricing (current numbers)
- Live Infra · AI Stack (free chain) · AI Staff roster (one-liner)
- Outbound/Growth (what's working) · Active Blockers / USER-ACTION pending
- Telephony (current state) · Legal (TRAI/DPDP/DLT/GST) · Deploy loop · Critical Env Gotchas
- Skills index (one line) · History pointer to SESSION_LOG

**Move to docs/SESSION_LOG.md (everything dated/historical):**
- Every "## … BATCH ✅ LIVE (date, commit)" / "✅ DEPLOYED" / "PROD-DOWN #n" narrative
- Per-feature build logs and route-count change notes

**Procedure (reversible):**
```bash
cd /opt/leadgen   # or your repo root
cp CLAUDE.md CLAUDE.md.bak                 # backup (rollback: mv CLAUDE.md.bak CLAUDE.md)
# create the lean version (keep sections above), then append the removed dated blocks:
#   cat removed_blocks.md >> docs/SESSION_LOG.md
git add CLAUDE.md docs/SESSION_LOG.md && git commit -m "Trim CLAUDE.md to lean working memory; move dated history to SESSION_LOG"
```
**Target:** ~120–150 lines. **Risk:** low. **Rollback:** restore CLAUDE.md.bak.

### A2. De-clutter the repo root
**Why:** 109 root entries; 28 untracked `*.log`, `leadgen.db`, scattered summaries hurt navigability.
```bash
cd /opt/leadgen
mkdir -p logs backups
git mv ... 2>/dev/null  # (only for TRACKED summary docs)
mv *.log logs/ 2>/dev/null              # untracked debug logs (already gitignored)
mv leadgen.db backups/ 2>/dev/null      # rollback SQLite (already gitignored as *.db)
# move the ~19 summary markdowns into docs/ (keep README.md, CLAUDE.md, CONTRIBUTING.md, SECURITY.md, LICENSE in root):
for f in PHASE5_DELIVERY_SUMMARY.txt PHASE6_COMPLETION_SUMMARY.md PHASE7_*.md PHASE7_*.txt \
         LAUNCH_SUMMARY.txt COPY_PASTE_LAUNCH.md GO_LIVE_CHECKLIST.md DEPLOY_VERIFICATION_CHECKLIST.md \
         COORDINATOR_SKILL_BUILD_SUMMARY.md FEEDBACK_LOOPS_AND_REFLEXION.md TEST_SCENARIOS_LOOP_CLOSURE.md \
         AGENT_LOOP_PROMPT_MASTER.md AGENT_SYSTEM_PROMPTS.md OPERATIONAL_RUNBOOKS.md; do
  git mv "$f" docs/ 2>/dev/null || mv "$f" docs/ 2>/dev/null
done
git add -A && git commit -m "Declutter repo root: logs/, backups/, summaries to docs/"
```
**Risk:** low (logs/db untracked; tracked-doc moves are git mv). Verify app still boots (no code imports those root .md/.txt).

---

## Phase B — Skill + docs hygiene (LOW risk)

### B1. Split oversized skills (progressive disclosure)
Targets (>300 lines): teach-agent-loop (714), coordinator-orchestration (570), orchestrate-goal (415), audit-automation (362). For each: keep a lean SKILL.md (overview + steps + when-to-use) and move deep detail to `references/`.
```bash
ls -d .claude/skills/*/ | while read d; do n=$(wc -l < "$d/SKILL.md" 2>/dev/null); [ "${n:-0}" -gt 300 ] && echo "$n  $d"; done | sort -rn
```

### B2. Skill-set review
68 skills is a lot. List, then mark any superseded/duplicate for retirement (keep the ones actually triggered in real sessions).

### B3. Compose/Dockerfile guide
Add docs/COMPOSE_GUIDE.md: one line per compose file + Dockerfile explaining when each is used (vps / observability / staging / tools / prod / ollama).

---

## Phase C — Scope reduction (HIGH risk, production — staged, confirm each batch)

### C1. Route inventory (read-only, do before any deletion)
```bash
grep -rEn '@(app|router)\.(get|post|put|delete|patch)\(' app/ | sed -E 's/.*"(\/[^"]*)".*/\1/' | sort | uniq -c | sort -rn > docs/_route_inventory.txt
wc -l docs/_route_inventory.txt
```
Group by product/feature; flag: dead (no frontend/scheduler caller), duplicate, demo-only, deprecated-flag.

### C2. Right-size the internal automation layer
Decision needed: which of coordinator / self_improve / code_upgrader / process_engine / staff_supervisor earn their keep vs. what Cowork skills already do. Candidates to retire reduce the Celery-backlog + quota-burn class of incidents.

### C3. Deprecate → verify → delete (small batches)
For each removal batch: gate behind a flag or mark deprecated → `python scripts/prod_check.py` + `scripts/run_tests.bat` (read pytest_run.log) → /ship → check `/health` = production → next batch. Never bulk-delete routes in one commit.

**Target:** 618 → ~400 routes (your own stated goal). **Risk:** HIGH. **Gate:** confirm each batch.

---

## Suggested order
A1 → A2 (today, fast wins) → B1/B3 → C1 inventory → C2 decision → C3 batches.
