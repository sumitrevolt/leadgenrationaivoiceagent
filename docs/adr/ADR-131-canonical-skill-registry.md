# ADR-131 — Canonical skill registry: consolidate `.agents/skills` into `.claude/skills`

**Status:** Proposed (Phase 12, 2026-07-21) — draft PR, not merged, no deployment.
**Supersedes the junction/mirror description in** `SKILLS_PARITY.md`.
**Phase 11 evidence:** PR #67 (inventory only).

## Context

A fresh checkout contained **two real tracked skill trees** (no junctions):

| Root | Tracked files | Skill dirs |
| --- | --- | --- |
| `.agents/skills` | 446 | 207 |
| `.claude/skills` | 403 | ~185 + 3 index files |

Comparison of blob hashes: **399 common relative paths, 0 divergent** (byte-identical);
**23 skills unique to `.agents/skills`**; **1 skill (`a2z-launch-enterprise-audit`) + 3 index
files unique to `.claude/skills`**. Workstation junction overlays are not Git state and future
edits to either side could silently diverge.

## Decision

**Canonical skill root = `.claude/skills`.** Evidence:

- Runtime loader `app/platform/skill_pack.py` uses `.claude/skills` as the primary root
  (`_SKILLS_DIR`), with `.agents/skills` only a secondary fallback.
- `.claude/skills` is the standard Claude Code / Cowork skill-discovery location.
- The majority of consumers (runtime code, `.env.example`, `.cursor/rules`, docs) reference
  `.claude/skills`; `.agents/skills` was referenced mainly by Dockerfiles, one test, and docs.

The 23 unique `.agents/skills` skills were **merged into `.claude/skills`** (no skill lost),
then the duplicate `.agents/skills` tree was removed with `git rm` on explicit paths.

**Invariant:** one canonical tracked implementation per skill name. No second registry, no
junctions, no Git symlinks.

## Consumer migration

| Consumer | Before | After |
| --- | --- | --- |
| `app/platform/skill_pack.py` | loads `.claude/skills` + `.agents/skills` | loads `.claude/skills` only |
| `scripts/vps_verify_deploy.py` | prints `agents` skill source | source line removed |
| `Dockerfile` / `Dockerfile.lock` / `Dockerfile.production` | `COPY .claude/skills` + `COPY .agents/skills` | `COPY .claude/skills` only |
| `tests/test_skill_pack_upgrader.py` | dual-root fixture + assertions | single canonical root |
| `SKILLS_PARITY.md` | described 61 junctions as topology | corrected to single canonical root |

## Compatibility

No external consumer requires the old path, so no shim is retained — the `.agents/skills`
root is removed outright. Any lingering config referencing it fails the CI guard rather than
silently reading a duplicate tree. Runtime already de-duplicated by name, so behavior is
unchanged (same skill set, one source).

## Guard

`tests/test_skill_tree_canonical_guard.py` fails CI if: `.agents/skills` reappears in Git, a
Dockerfile bakes it, runtime code references it, the canonical set shrinks unexpectedly, or a
skill id duplicates within the canonical root.

## Rollback

Revert the Phase 12 PR commit(s); restore the removed tree from tag
`safety/pre-skill-dedup-20260721`; restore prior consumers. Repository-only — no database or
production rollback. **Do not** recreate workstation junctions as the rollback mechanism.

## Non-goals / safety

No product code behavior change, no deployment, no production touch, `DEPLOY_ENABLED` stays
unset, Owner OS / OpenClaw authority and RED/AMBER/GREEN classifications unchanged.
