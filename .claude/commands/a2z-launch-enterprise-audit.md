---
description: LeadGen A-to-Z Launch & Enterprise Audit — execute end-to-end (Discover → Verify → Fix safe local gaps → Test → Browser proof → Final verdict). Scores Marketing + standalone Voice separately; returns Business Launch / Production / Enterprise (/120) verdicts. NOT audit-only.
---
# /a2z-launch-enterprise-audit — full launch + enterprise certification

Ye audit pe rukta NAHI — safe local fixes + tests + real browser proof + verdict tak jaata hai.

## Steps
1. Read `.claude/skills/context-first/SKILL.md` FIRST (mandatory pre-flight).
2. Read **full** `.claude/skills/a2z-launch-enterprise-audit/SKILL.md` — that is the canonical master prompt.
3. Execute its **Phase A→F** flow with stop rules + evidence gates:
   Discover → Verify (exact repo scripts + separate live proofs) → Fix verified local P0–P2 (minimal additive + regression test, dirty-tree preserved) → Test → Browser proof (`/app/admin`,`/app/automation`,`/app/control-center`,`/app/office`) → Score & Verdict.
4. Produce the **7-part Final Deliverable** + Loop Engineer 9-field block, in Hinglish Roman.

## Hard rules (never weaken)
- `platform_dial` = 3-layer HARD OFF · TRAI/DND/AI-disclosure/DPDP gates INTACT · free AI-stack only · Old Explorer fallback stays functional.
- Dirty tree me parallel user changes ho sakte — clean/reset/`git add -A` KABHI nahi.
- **FORBIDDEN without explicit user approval:** commit · push · prod deploy · `.env`/secret edit · destructive migration · external/customer actions.
- Deploy approved to hi: ONLY `scripts/deploy_vps.sh`, pinned SHA, 5-service skew check, `/health.version` match, post-deploy browser smoke.

## Live probe
```powershell
curl.exe -fsS https://leadsgenai.in/health
curl.exe -fsS https://leadsgenai.in/api/activation/summary
```

`$ARGUMENTS`: `quick` = Discover+Verify+Score only (no fixes/browser) · `full` = all phases (default).
