# Handoff to Hermes — Owner-Directive Archive Checksum Fix (`e9b584c7`)

**Date:** 2026-09-22 · **From:** FreeBuff session · **For:** PR #552 (`bbf8b5e6`) / PR #556 (`00810bea`) integration
**Status:** Fix already incorporated in PR #556 — nothing to re-implement, nothing to push.

---

## 1. Ancestry verification (owner-asked; verified locally)

- `origin/fix/project-context-reads-agents-md` **contains `e9b584c7`** (pushed from this workspace's branch; no push made by this session).
- `git log e9b584c7..00810bea` = exactly 2 commits: `eec99295` (project_context → AGENTS_REFERENCE.md + Telegram bot-token shape detection) and `00810bea` (ingest both canonical AGENTS.md and legacy REFERENCE.md + regression tests).
- `git diff e9b584c7 00810bea -- .gitattributes tests/test_owner_directive_checksum.py` → **EMPTY** — both artifacts byte-identical in PR #556 HEAD.

## 2. What the fix is (one commit, 2 files, +56)

- `.gitattributes` (+2): `docs/OWNER_DIRECTIVE_2026-09-22.md text eol=lf`
- `tests/test_owner_directive_checksum.py` (+54): parses the SHA-256 pin for the archive path out of `AGENTS.md`, hashes the **actual checked-out bytes**, fails on CRLF or content drift.

## 3. Verification evidence (fresh clone, actual `core.autocrlf=true`)

| Check | Result |
|---|---|
| HEAD blob SHA-256 | `803a4683b94f6b8cf41dccb5cb6da461b3def108c43794585d256f78a5cab6ea` (= governance pin) |
| Fresh-clone checkout disk SHA-256 @ `e9b584c7` | same, `w/lf attr/text eol=lf` |
| Regression test in fresh clone | `PYTEST_EXIT:0`, 2 passed |
| Negative control @ `bbf8b5e6` (no rule, fresh clone) | already checks out LF — CRLF NOT reproduced |
| Governance tests / secret scan | `test_1000_engineers_skill` 7/7 · `check_secrets` `[OK]` |

## 4. Corrected root cause (supersedes the earlier "Windows checkout conversion" claim)

The archive file was **created on disk with CRLF endings**; `git add` normalized the committed blob to LF (`core.autocrlf=true`), leaving the local worktree CRLF while the blob stayed LF. Net effect: the `803A4683…` pin in AGENTS.md / CLAUDE.md stub / docs/AGENTS_REFERENCE.md never matched actual on-disk bytes — tamper-evidence dead. Fresh checkouts were never the failure mode (negative control proved it). The `text eol=lf` rule guarantees LF checkout bytes on any platform/config; the regression test catches any disk CRLF or content change. Committed blob content is unchanged.

## 5. Three-copies question (owner asked; closed)

On the PR #552/#556 lineage **only one canonical archive path exists** (`docs/OWNER_DIRECTIVE_2026-09-22.md`). `docs/owner/…` and `docs/owner-master/OWNER_OS_MASTER_2026-09-22.md` were never committed — they were untracked files in a prior `main` worktree (now absent). Byte-identity of the directive content vs the master copy was verified while both existed (LF-normalized diff exit 0).

## 6. CLAUDE.md reference classification (for later waves — NO blanket replacement)

- **Active consumers (read the file):** `tests/test_1000_engineers_skill.py` (green with the 944-byte stub); Claude-style auto-loaders (the stub's purpose).
- **Compatibility (name-only):** `.claude/hooks/guard.py` + `write_guard.py` (write-guard patterns/messages); ~60 `.claude/skills/*/SKILL.md` convention citations.
- **Historical:** `ops/runbooks/registry.yaml` (~12 `source:` entries), `ops/playbooks/registry.yaml` (~7), frontend/battlecard HTML comments (4), `README.md:121` (stale byte-identical claim), `progress.md` / `docs/SESSION_LOG.md` logs.

## 7. TypeSafe evidence discipline (separate claims, per owner)

- Skill **loading**: `.claude/skills/typesafe-ai/SKILL.md` present, valid frontmatter — CONFIGURED.
- **Live API**: 2 independent `scripts/typesafe_status.py --probe` calls — success, `jev-latest → jev-1.13.0`, latency 1.512s / 5.472s, fp `2e13ca55f7f8` (state-only, no value). This proves LOCAL API availability only — **not** project-wide integration across MiniMax/9 workers/31 agents.
- Known drift: `.env.production.local` holds a TypeSafe key (fp `45d2320759d8`) that no loader reads — inert.
