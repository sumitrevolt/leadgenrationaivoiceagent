# WORKTREE + BRANCH CONSOLIDATION — 2026-08-12

Evidence labels: GIT_VERIFIED. No deploy. No flag arm. No secrets.

- **origin/main tip:** 23ea2d468db7449c8975505b3ecd3189e157f3e2 (23ea2d46)
- **Verified ancestors:** PR #333 76064942 · docs #334 23ea2d46 · ADR-177 9c47647c
- **Open PRs (left alone this packet):** Dependabot #322–#328 only
- **Method:** classify → land unique via PR → delete obsolete — **no blind force-merge**

## Counts (Phase 0 snapshot)

| Kind | Count | Buckets |
|---|---:|---|
| Worktrees | 34 | {'D_DIRTY_WIP': 16, 'A_MERGED': 16, 'C_UNIQUE_KEEP': 2} |
| Remote branches | 66 | {'A_MERGED': 46, 'C_UNIQUE_KEEP': 13, 'B_PR_OPEN': 7} |
| Local branches | 57 | {'A_MERGED': 47, 'C_UNIQUE_KEEP': 10} |

## Primary checkout finding (critical)

Primary was on cursor/split-B-buzz-local-relay-20260810 with dirty UPI.
Working-tree diff **deleted** ind_client (~81 lines) and weakened guest-bind tests — **truncation/regression, not valuable WIP**.
origin/main already has single ind_client. HEAD tip had **duplicate** ind_client (F811).
**Action taken:** restored UPI files from git; moved .tmp_buzz_* canary scratch → _scratch/buzz_canary_20260812/.
Branch tip reclassified **E_OBSOLETE** (do not merge).

## Worktrees

| Path | Branch | HEAD | Dirty | Unique | Bucket |
|---|---|---|---:|---:|---|
| leadgen-admin-harden | fix/admin-harden-wave1 | eaf5a39f32 | 0 | 0 | **A_MERGED** |
| leadgen-admin-logout-fix | fix/admin-auth-boot-deploy-race | b9afe1b6bc | 0 | 0 | **A_MERGED** |
| leadgen-alert34-ssrf-20260810 | cursor/ssrf-audit-normalize-20260810 | 3f2eb8a48f | 1 | 0 | **D_DIRTY_WIP** |
| leadgen-all-worktrees-20260809 | integration/all-worktrees-20260809 | 76460cc62b | 39 | 0 | **D_DIRTY_WIP** |
| leadgen-automation-max-live-20260810 | (detached) | 93ce633ba4 | 0 | 0 | **A_MERGED** |
| leadgen-bernstein-pilot | opencode/bernstein-pr-orchestration-pilot-2026-08-07 | c8ca618468 | 0 | 0 | **A_MERGED** |
| leadgen-boss-second-brain-governance-20260811 | cursor/boss-second-brain-governance-20260811 | 796c2c9b3c | 2 | 0 | **D_DIRTY_WIP** |
| leadgen-buzz-deploy-20260810 | cursor/buzz-deploy-assets-20260810 | caa8c85141 | 0 | 0 | **A_MERGED** |
| leadgen-buzz-local-first | cursor/fix-guest-upi-approved-unbound-20260810 | 169d144b4b | 1 | 0 | **D_DIRTY_WIP** |
| leadgen-coord-hub | feat/coord-hub-heartbeat-script | 5ae5a4b9d7 | 0 | 0 | **A_MERGED** |
| leadgen-d2-harvest | fix/d2-post-prospect-harvest | 091e1109b1 | 3 | 2 | **D_DIRTY_WIP** |
| leadgen-kb-grounding-20260810 | cursor/voice-kb-grounding-a1-20260810 | 40d9491a91 | 0 | 0 | **A_MERGED** |
| leadgen-launch-ready-20260810 | cursor/launch-revenue-automation-ready-20260810 | d25d78f21f | 0 | 0 | **A_MERGED** |
| leadgen-leadid-fix | feat/call-lead-crm-sync | 7962730acb | 0 | 2 | **C_UNIQUE_KEEP** |
| leadgen-master-blueprint-nav | fix/admin-master-blueprint-nav | 8b36b79542 | 2 | 0 | **D_DIRTY_WIP** |
| leadgen-pii-containment | main | a42d869c17 | 25 | 0 | **D_DIRTY_WIP** |
| leadgen-prfix-271 | pr271-work | 7d2420cc1a | 1 | 0 | **D_DIRTY_WIP** |
| leadgen-prfix-282 | pr282-work | 916ae58906 | 1 | 0 | **D_DIRTY_WIP** |
| leadgen-prfix-283 | pr283-work | 8d7bae572e | 1 | 0 | **D_DIRTY_WIP** |
| leadgen-prfix-295 | pr295-work | 3f22a9ac75 | 11 | 0 | **D_DIRTY_WIP** |
| leadgen-pytest9-cursor-20260810 | cursor/pytest9-remediation-20260810 | beff8160b5 | 0 | 5 | **C_UNIQUE_KEEP** |
| leadgen-pytest9-docs-20260810 | docs/pytest9-greenlet-blocker-20260810 | cbbc8da1b4 | 0 | 0 | **A_MERGED** |
| leadgen-rollback-retention-20260811 | cursor/rollback-retention-lineage-20260811 | 72d9bc1226 | 4 | 0 | **D_DIRTY_WIP** |
| leadgen-secfix | fix/dep-cve-2026-08-08 | 24f5fec7bc | 0 | 0 | **A_MERGED** |
| leadgen-settings-guard | fix/safe-settings-snapshot | 49984af168 | 2 | 3 | **D_DIRTY_WIP** |
| leadgen-verify-main | fix/reply-auto-send-interaction-log | 8a9dd6c18f | 3 | 0 | **D_DIRTY_WIP** |
| leadgen-voice-fix | fix/voice-paid-free-faq | e36bdfb2ee | 0 | 0 | **A_MERGED** |
| leadgenrationaiagent | cursor/split-B-buzz-local-relay-20260810 | 4395630f79 | 33 | 2 | **D_DIRTY_WIP** |
| leadgenrationaiagent/.claude/worktrees/agent-ws1-codeql-path-containment | fix/codeql-578-path-containment-image-scan | 026fca20a5 | 0 | 0 | **A_MERGED** |
| leadgenrationaiagent/.claude/worktrees/buzz-multi-agent-setup-b0ce78 | claude/buzz-multi-agent-setup-b0ce78 | a42d869c17 | 14 | 0 | **D_DIRTY_WIP** |
| leadgenrationaiagent/.claude/worktrees/jolly-bartik-6aedd3 | (detached) | a42d869c17 | 0 | 0 | **A_MERGED** |
| leadgenrationaiagent/.claude/worktrees/leadgen-enterprise-readiness-edf3a9 | (detached) | a42d869c17 | 0 | 0 | **A_MERGED** |
| leadgenrationaiagent/.freebuff/worktrees/3e91a874-0e74-4885-8a44-e4b030bc6f7a | docs/truth-fix-platform-dial-live | 199a98aed5 | 0 | 0 | **A_MERGED** |
| leadgenrationaiagent/.worktrees/cursor-31-agent-bus-20260812 | docs/pr333-auth-merge-handoff | d553897419 | 0 | 0 | **A_MERGED** |

## Remote branches — refined buckets

| Branch | Unique | Initial | Refined | Note |
|---|---:|---|---|---|
| agent/tm2/c1-test | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| alert-autofix-34 | 1 | C_UNIQUE_KEEP | **C_UNIQUE_KEEP** | SSRF autofix on website_auditor — open Draft if still unmerged vs cursor/ssrf-audit (merged). |
| chore/dial-truth-docs-dlq | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| ci-debug | 1 | C_UNIQUE_KEEP | **E_OBSOLETE** | No merge-base / debug noise. |
| claude/leadgen-enterprise-readiness-edf3a9 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/31-agent-bus-setup-20260812 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/automation-max-live-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/boss-second-brain-governance-20260811 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/buzz-deploy-assets-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/buzz-local-first-mcp-20260810 | 2 | C_UNIQUE_KEEP | **C_UNIQUE_KEEP** | deploy/buzz kit may partially exist; review as Draft docs/ops PR. |
| cursor/buzz-local-kit-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/claude-agent-teams-worktrees-63d4 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/fix-guest-upi-approved-unbound-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/launch-revenue-automation-ready-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/pytest9-remediation-20260810 | 5 | C_UNIQUE_KEEP | **C_UNIQUE_KEEP** | Pytest 9 migration — greenlet blocker known; Draft/hold, do not force. |
| cursor/reply-hard-off-containment-3790 | 2 | C_UNIQUE_KEEP | **E_OBSOLETE** | Docs-only Option A containment; superseded by later context on main. |
| cursor/rollback-retention-lineage-20260811 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/split-B-buzz-local-relay-20260810 | 1 | C_UNIQUE_KEEP | **E_OBSOLETE** | BUZZ_RELAY:3100 already on main; tip also carries duplicate bind_client (F811) + progress nuke checkpoint — do not merge. |
| cursor/split-D-trivy-ratchet-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/split-E-deploy-hardening-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/split-F-admin-soft-remove-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/split-H-revenue-tests-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/ssrf-audit-normalize-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/swara-paid-free-faq-fix | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/upi-pending-digest-probe-63d4 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| cursor/voice-kb-grounding-a1-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| dependabot/github_actions/actions/checkout-7.0.1 | 1 | B_PR_OPEN | **B_PR_OPEN** | Dependabot — separate deps packet |
| dependabot/github_actions/actions/setup-python-7.0.0 | 1 | B_PR_OPEN | **B_PR_OPEN** | Dependabot — separate deps packet |
| dependabot/pip/mkdocstrings-1.0.6 | 1 | B_PR_OPEN | **B_PR_OPEN** | Dependabot — separate deps packet |
| dependabot/pip/mypy-2.3.0 | 1 | B_PR_OPEN | **B_PR_OPEN** | Dependabot — separate deps packet |
| dependabot/pip/pylint-4.0.6 | 1 | B_PR_OPEN | **B_PR_OPEN** | Dependabot — separate deps packet |
| dependabot/pip/python-minor-patch-d4863d3830 | 1 | B_PR_OPEN | **B_PR_OPEN** | Dependabot — separate deps packet |
| dependabot/pip/sentry-sdk-2.66.1 | 1 | B_PR_OPEN | **B_PR_OPEN** | Dependabot — separate deps packet |
| docs/buzz-incident-containment-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| docs/pytest9-greenlet-blocker-20260810 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| docs/truth-fix-platform-dial-live | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| feat/call-lead-crm-sync | 2 | C_UNIQUE_KEEP | **C_UNIQUE_KEEP** | Residual tip vs #273 — Draft PR or cherry remaining blueprint commit; do not blind-merge. |
| feat/deliverable-cycle-seed | 1 | C_UNIQUE_KEEP | **C_UNIQUE_KEEP** | Overlaps #272; verify residual then Draft or E_OBSOLETE. |
| fix/admin-auth-boot-deploy-race | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/admin-harden-wave1 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/admin-master-blueprint-nav | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/agent-task-orphan-ledger | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/call-log-lead-attribution | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/ci-security-truth-2026-08-08 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/codeql-578-path-containment-image-scan | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/d2-post-prospect-harvest | 2 | C_UNIQUE_KEEP | **C_UNIQUE_KEEP** | Overlaps #274; verify residual then Draft or E_OBSOLETE. |
| fix/deliverable-ledger-alias | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/dep-cve-2026-08-08 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/fixture-tenant-quarantine | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/reply-auto-send-interaction-log | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| fix/safe-settings-snapshot | 3 | C_UNIQUE_KEEP | **C_UNIQUE_KEEP** | Overlaps #275; verify residual then Draft or E_OBSOLETE. |
| fix/security-cp5-3-deps | 1 | C_UNIQUE_KEEP | **C_UNIQUE_KEEP** | Deps/security tip — separate deps packet preferred; Draft PR only. |
| fix/voice-paid-free-faq | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| freebuff/analyze-the-project-and-the-project-launch-ready-a-41b4e256-12c0-4785-8047-e7cd30c076d4 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| freebuff/automation-opportunity-discovery-integration-20260809 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| freebuff/daily-posting-videos-are-not-a-proper-setup-the-ma-0695d324-c5c4-4e0f-b023-6f78c7ac1c01 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| freebuff/pytest9-compat-20260810 | 4 | C_UNIQUE_KEEP | **E_OBSOLETE** | Subset/overlap of pytest9 remediation tip. |
| freebuff/sec-codeql-20260809 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| freebuff/sec-py-deps-20260809 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| freebuff/security-triage-20260809 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| integration/all-worktrees-20260809 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| opencode/bernstein-pr-orchestration-pilot-2026-08-07 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| ops/capacity-staging-containment | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| release/merged-2026-08-02 | 0 | A_MERGED | **A_MERGED** | Tip already in origin/main — safe delete after this doc lands |
| rescue/local-untracked-20260806 | 3 | C_UNIQUE_KEEP | **E_OBSOLETE** | Historical rescue archive; keep evidence in docs/rescue if already present. |

## A_MERGED remotes (deletion candidates)

Count: **45**

`	ext
agent/tm2/c1-test
chore/dial-truth-docs-dlq
claude/leadgen-enterprise-readiness-edf3a9
cursor/31-agent-bus-setup-20260812
cursor/automation-max-live-20260810
cursor/boss-second-brain-governance-20260811
cursor/buzz-deploy-assets-20260810
cursor/buzz-local-kit-20260810
cursor/claude-agent-teams-worktrees-63d4
cursor/fix-guest-upi-approved-unbound-20260810
cursor/launch-revenue-automation-ready-20260810
cursor/rollback-retention-lineage-20260811
cursor/split-D-trivy-ratchet-20260810
cursor/split-E-deploy-hardening-20260810
cursor/split-F-admin-soft-remove-20260810
cursor/split-H-revenue-tests-20260810
cursor/ssrf-audit-normalize-20260810
cursor/swara-paid-free-faq-fix
cursor/upi-pending-digest-probe-63d4
cursor/voice-kb-grounding-a1-20260810
docs/buzz-incident-containment-20260810
docs/pytest9-greenlet-blocker-20260810
docs/truth-fix-platform-dial-live
fix/admin-auth-boot-deploy-race
fix/admin-harden-wave1
fix/admin-master-blueprint-nav
fix/agent-task-orphan-ledger
fix/call-log-lead-attribution
fix/ci-security-truth-2026-08-08
fix/codeql-578-path-containment-image-scan
fix/deliverable-ledger-alias
fix/dep-cve-2026-08-08
fix/fixture-tenant-quarantine
fix/reply-auto-send-interaction-log
fix/voice-paid-free-faq
freebuff/analyze-the-project-and-the-project-launch-ready-a-41b4e256-12c0-4785-8047-e7cd30c076d4
freebuff/automation-opportunity-discovery-integration-20260809
freebuff/daily-posting-videos-are-not-a-proper-setup-the-ma-0695d324-c5c4-4e0f-b023-6f78c7ac1c01
freebuff/sec-codeql-20260809
freebuff/sec-py-deps-20260809
freebuff/security-triage-20260809
integration/all-worktrees-20260809
opencode/bernstein-pr-orchestration-pilot-2026-08-07
ops/capacity-staging-containment
release/merged-2026-08-02
`

## C_UNIQUE / E_OBSOLETE outcomes plan

| Branch | Plan |
|---|---|
| alert-autofix-34 | **C_UNIQUE_KEEP** — SSRF autofix on website_auditor — open Draft if still unmerged vs cursor/ssrf-audit (merged). |
| ci-debug | **E_OBSOLETE** — No merge-base / debug noise. |
| cursor/buzz-local-first-mcp-20260810 | **C_UNIQUE_KEEP** — deploy/buzz kit may partially exist; review as Draft docs/ops PR. |
| cursor/pytest9-remediation-20260810 | **C_UNIQUE_KEEP** — Pytest 9 migration — greenlet blocker known; Draft/hold, do not force. |
| cursor/reply-hard-off-containment-3790 | **E_OBSOLETE** — Docs-only Option A containment; superseded by later context on main. |
| cursor/split-B-buzz-local-relay-20260810 | **E_OBSOLETE** — BUZZ_RELAY:3100 already on main; tip also carries duplicate bind_client (F811) + progress nuke checkpoint — do not merge. |
| feat/call-lead-crm-sync | **C_UNIQUE_KEEP** — Residual tip vs #273 — Draft PR or cherry remaining blueprint commit; do not blind-merge. |
| feat/deliverable-cycle-seed | **C_UNIQUE_KEEP** — Overlaps #272; verify residual then Draft or E_OBSOLETE. |
| fix/d2-post-prospect-harvest | **C_UNIQUE_KEEP** — Overlaps #274; verify residual then Draft or E_OBSOLETE. |
| fix/safe-settings-snapshot | **C_UNIQUE_KEEP** — Overlaps #275; verify residual then Draft or E_OBSOLETE. |
| fix/security-cp5-3-deps | **C_UNIQUE_KEEP** — Deps/security tip — separate deps packet preferred; Draft PR only. |
| freebuff/pytest9-compat-20260810 | **E_OBSOLETE** — Subset/overlap of pytest9 remediation tip. |
| rescue/local-untracked-20260806 | **E_OBSOLETE** — Historical rescue archive; keep evidence in docs/rescue if already present. |

## Phase execution log

- [x] Phase 0 inventory + this evidence → PR **#335** MERGED (`f814cfe7`)
- [x] Phase 1: UPI truncation restored (not parked as feature); buzz tmp → `_scratch/buzz_canary_20260812/`
- [x] Phase 2: Draft PRs **#336–#339** for residual C_UNIQUE (no AUTH-MERGE this packet)
- [x] Phase 3: remotes **66 → 13** (A_MERGED/E_OBSOLETE deleted; Dependabot kept)
- [x] Phase 4: worktrees **34 → 2** registered; primary on clean `main`
- [x] Phase 5: verify counts (below)

## Final snapshot (2026-08-12T07:40Z)

| Metric | Before | After |
|---|---|---|
| Registered worktrees | ~34 | **2** (primary `main` + pytest9 Draft #337) |
| Remote branches | ~66 | **13** (`main` + 4 Draft heads + 7 Dependabot + `origin/HEAD`) |
| Local branches | ~57 | **4** |
| Inventory PR | — | **#335 MERGED** |
| Unique Draft PRs | — | **#336** SSRF · **#337** pytest9 · **#338** buzz kit · **#339** CP5-3 deps |
| Dependabot | #322–#328 open | **untouched** |
| `origin/main` tip | `23ea2d46` (+ #333/#334) | **`f814cfe7`** (+ #335) |
| Deploy / flag arm | — | **none** |

### C_UNIQUE outcomes

| Tip | Outcome |
|---|---|
| `alert-autofix-34` | Draft **#336** |
| `cursor/pytest9-remediation-20260810` | Draft **#337** + worktree kept |
| `cursor/buzz-local-first-mcp-20260810` | Draft **#338** |
| `fix/security-cp5-3-deps` | Draft **#339** (deps packet); local tip **ahead 1** unpushed `WIP: cp5-3-security` — do not discard blindly |
| `feat/call-lead-crm-sync` (+ #272–#275 cousins) | Reclassified **E_OBSOLETE** (content on main); remotes deleted |

### Intentional exceptions

1. Worktree `leadgen-pytest9-cursor-20260810` kept for Draft #337
2. Orphan dirs (not in `git worktree list`; file-lock): `Documents\leadgen-boss-second-brain-governance-20260811`, `.claude\worktrees\buzz-multi-agent-setup-b0ce78` — delete manually when unlocked
3. Dependabot #322–#328 left for separate deps packet
4. Draft #336–#339 not AUTH-MERGED in this packet

## Constraints observed

- No deploy / no STAFF_BUS_ENABLED / GSC_ENABLED arm
- No force-push main
- Dependabot #322–#328 untouched
- Gate A .freebuff noise ignored

Generated: 2026-08-12T07:16:00.714477+00:00 · Closed: 2026-08-12T07:40:00+00:00
