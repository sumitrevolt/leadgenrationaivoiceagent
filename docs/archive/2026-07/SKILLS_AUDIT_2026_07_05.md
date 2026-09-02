# Skills Library Audit — 2026-07-05

**Scope:** `.claude/skills/` ke saare 184 SKILL.md (user-requested full audit).
**Method:** Phase 0 = mechanical scan (frontmatter, dead-refs, known stale-patterns, mirror-diff). Phase 1 = 15 parallel audit-agents, har skill POORI padhi gayi, live-verified truth-sheet ke against. Phase 2 = high-severity findings pe adversarial refute-verify (independent agents). ~1.1M subagent tokens, 17 agents.

## Result summary

| Metric | Count |
|---|---|
| Skills audited | 184 |
| Clean (koi issue nahi) | 155 |
| Findings (deduped) | 31 |
| High (confirmed by adversarial verify) | 2/2 |
| Fixes APPLIED (is commit me) | 31 edits across 27 files |
| Findings DISCARDED (galat nikli) | 1 (`saas-pricing-strategy` — neeche dekho) |

## HIGH (dono adversarially confirmed + fixed)

1. **`marketing-feature`** — deploy step kehta tha "push → VPS pull+restart" = **no-op deploy** (code image me BAKED; pull+restart kuch deploy nahi karta, stale code smoke-test hota). Fixed → rebuild+recreate wording.
2. **`run-campaign`** — "real calls only 9am-**9pm**" — **TRAI window 9am-7pm hai (fail-CLOSED)**; skill khud apni line 8 me sahi "9am-7pm" bolta tha. Compliance-relevant contradiction. Fixed.

## MEDIUM applied (16 files) — themes

- **Deploy reality drift (5 skills)**: `spec`, `leadgen-customer-journey-e2e`, `teach-agent-loop`, `careful`, (`marketing-feature` high) — sab systemd/git-pull-era instructions ko Docker image-baked reality pe laya gaya.
- **Full-pytest hang (4 skills)**: `deploy`, `tdd-contract-first`, `verify-ship`, (`ship-checklist` pehle se sahi tha) — `run_tests.bat` full-suite offline HANG hota hai; targeted suites ab default.
- **Container roster (3 skills)**: `leadgen-infra-doctor` (freeswitch tha hi nahi, worker_heavy/qdrant/postiz/waha missing), `load-capacity-testing` (beat alag scheduler container me), `leadgen-observability` (**obs stack DEFINED par NOT RUNNING** — dashboards pe bharosa mat karo bina verify).
- **LLM chain (2)**: `audit-automation`, `leadgen-voice-compliance` — Mistral primary, Gemini late-fallback (Gemini-primary claim galat tha; `VOICE_GEMini_PRIMARY` default OFF code-verified).
- **Pricing paths (2)**: `leadgen-billing-upi`, `leadgen-product-truth` — voice plans ka canonical = `app/marketing/voice_packages.py`.
- **Misc**: `supply-chain-security` (Caddy host-level hai, container nahi), `mcp-engineer` (frontmatter missing thi — ab discoverable).

## LOW applied

- Route-count 761→1030: `api-design`, `backend-rbac`, `feature-change-flow`, `review`.
- 42→39 niches: `automation-flags`. Tier-axis annotate: `pairwise-test-design`.
- Cross-links (drift-prevention, content trim NAHI kiya): `cold-email-craft`→`cold-email`, `cro`→`conversion-optimization`, `review`→`self-code-review`, `test-driven-development`→`tdd-contract-first`.
- `SKILLS_PARITY.md` khud stale tha ("~103 folders" → 184).

## DISCARDED finding + truth-sheet correction

`saas-pricing-strategy` ko flag kiya gaya tha ki wo `app/marketing/voice_packages.py` bolta hai jabki truth-sheet `app/billing/voice_packages.py` kehti thi. **Audit-agent ne git-history + filesystem se prove kiya ki truth-sheet hi galat thi** — `app/billing/voice_packages.py` kabhi exist nahi kiya. Skill sahi tha, edit NAHI hua; `docs/HANDOFF.md` ki wahi galti fix hui (+ `product-split-adr` bhi correct nikla).

## Mirror drift (.claude vs .agents) — ✅ RESOLVED (2026-07-05, same din)

- **Root-cause discovery**: "automation sync-loop" jaisa jo dikh raha tha wo asal me **61 Windows JUNCTIONS** the — `.claude/skills/` ke 61 dirs `.agents/skills/` ko point karte hain (same physical files). Drift sirf REAL duplicate dirs me thi.
- **Reconcile hua**: 76 drifted files `.claude` → `.agents` file-level sync (zero deletions), 9 enterprise-hardening skills (`data-retention-dpdp`, `db-migration-safety`, `dr-restore-drill`, `enterprise-readiness-audit`, `load-capacity-testing`, `secrets-rotation`, `slo-error-budget`, `supply-chain-security`, `tenant-isolation-audit`) pehli baar mirror hue. Post-sync verification: **0 mismatch** (har `.claude` file ka `.agents` counterpart byte-identical).
- **Naya safety rule** (SKILLS_PARITY me): skills trees me KABHI recursive delete nahi — junction ke aar-paar asli content udta hai (aaj `ab-testing` aise hi gaya tha, git-restore hua; incident isi audit me pakda gaya).
- Runtime pe koi risk tha hi nahi: `skill_pack.py` `.claude` PEHLE load karta hai + name-dedupe — stale `.agents` copies hamesha shadowed thin.

---

# Part 2 — `data/skills_extra/` (181 flat files) — same din, dusra pass

**Method:** wahi (14 audit-agents, corrected truth-sheet — voice_packages path fix ke saath, adversarial verify). ~1.25M subagent tokens.

| Metric | Count |
|---|---|
| Files audited | 181 |
| Clean | 150 |
| High | **0** (koi operational-risk staleness nahi — expected: zyada tar generic personas/rules) |
| Findings fixed | 30 (29 frontmatter + 1 dead-reference) |

**Kya mila/fixa:**
- **29 files me frontmatter missing/incomplete** — 13 NEXUS strategy playbooks (`agency-strategy-*`: bina `---` block ke shuru hoti thin) + 10 `ecc-rules-common-*` (koi frontmatter nahi) + 6 `ecc-rules-python-*` (sirf `paths:` tha, `name:`/`description:` nahi). In sab me `skill_pack.py` discovery ke liye name+description add hua. Post-fix verify: **saare 181 valid**.
- **`agency-engineering-senior-developer`** — 4 dead `ai/system/...`/`ai/agents/...` references (kisi aur Laravel/FluxUI template se aaye the; wo files is repo me kabhi nahi thin) — hata diye, note ke saath.
- Project-fact staleness: **zero** — extras me pricing/deploy/container claims the hi nahi (generic content), isliye Part-1 jaisi factual drift yahan nahi mili.

**Deploy note:** `data/` bind-mounted hai — ye fixes VPS pe sirf `git reset` se LIVE ho jate hain, rebuild nahi chahiye.

## Out of scope (poore audit ke baad bhi)

- `.agents/skills` ke 23 generic vendored skills (project-facts nahi rakhte — staleness risk low) + mirror-drift decision (upar).
- Brain-vault (`leadsgenai-brain/Skills/`) — nightly-bot territory.
