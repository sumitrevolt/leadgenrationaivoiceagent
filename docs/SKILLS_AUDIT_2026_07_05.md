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

## Mirror drift (.claude vs .agents) — DECISION NEEDED (fix nahi kiya)

- `SKILLS_PARITY.md` rule: **`.claude/skills` = PRIMARY**.
- `.agents/skills` me 52 shared files PURANE hain (aaj ke SOP upgrades + ye audit-fixes bhi sirf `.claude` me hain), 12 skills `.claude`-only (enterprise-hardening set kabhi mirror nahi hua), 23 `.agents`-only (generic vendored — intentional).
- **Recommendation**: ya to ek sync-script banao (`.claude` → `.agents` one-way, `.agents`-only 23 ko chhod ke), ya `.agents` ke shared copies ko delete karke Dockerfile me sirf `.claude` COPY rakho (runtime `skill_pack.py` dono padhta hai — duplication ka koi faida nahi). Alag task.

## Out of scope (is pass me nahi — silent skip nahi hai)

- `data/skills_extra/` ke 181 flat files (content-review nahi hua; format-wise skill_pack inhe padhta hai).
- `.agents/skills` ke 23 generic vendored skills (project-facts nahi rakhte — staleness risk low).
- Brain-vault (`leadsgenai-brain/Skills/`) — nightly-bot territory.
