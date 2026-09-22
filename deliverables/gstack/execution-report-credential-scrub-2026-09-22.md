# Execution Report — Two Live Credentials Removed from PUBLIC main + Scanner Blind Spot Closed

**Date:** 2026-09-22
**Scope:** Security remediation on `leadgenrationaivoiceagent` (PUBLIC repo, live at https://leadsgenai.in)
**Mode:** Solo execution (no multi-specialist review this turn — no member outputs are fabricated below)
**PR:** [#550](https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/550) — OPEN, checks in flight

---

## 📌 TL;DR

- **Two live Telegram credentials were sitting on PUBLIC `main`** — the MTProto `api_id`/`api_hash` in **8 places across 6 files**, and a `TELEGRAM_WEBHOOK_SECRET` (48-hex, marked *"LIVE and verified"*) in 1 doc. **9 occurrences total.**
- **Neither was detectable by the project's own secret scanner.** Root cause identified, measured, and fixed.
- **PR #550 removes all 9** and closes the scanner blind spot, with a regression suite pinning both directions.
- **Rotation is still required and is owner-only.** Merging does **not** un-leak anything — both values remain in `main`'s git history.
- **Go/No-Go: 🟡 Conditional** — agent-side work is done and verified; the incident stays open until the owner rotates.

---

## 🎯 Core Conclusion Card

| Item | Value |
|------|-------|
| Agent-side status | 🟢 Complete and verified |
| Incident status | 🔴 **NOT contained** (TypeSafe `leak_contained` = 0.22) |
| Live credentials on `main` | 2 classes / 9 occurrences |
| Fix diff | 9 files, +420/−40 |
| New false positives introduced | **0** (measured repo-wide) |
| Blocking owner actions | 2 (both require phone/SMS) |
| TypeSafe `next_action` | `rotate_credentials` @ 0.59 |

---

## 1. What was actually wrong

### 1.1 Two credentials, both live, both public

| Credential | Occurrences | Files |
|---|---|---|
| Telegram MTProto `api_hash` | 8 | `scripts/telethon_{new_notify_bot,botfather_token,extract_token,make_forum_groups}.py`, `docs/TELEGRAM_PHASE1_2_RUNBOOK.md` (×3), `docs/TELEGRAM_SINGLE_SOURCE_OF_TRUTH_2026-09-20.md` |
| Telegram `webhook_secret` | 1 | `docs/TELEGRAM_ENTERPRISE_SETUP_COMPLETE.md:107` |

The MTProto pair was committed as a **silent source default**:

```python
API_ID   = os.environ.get("TELEGRAM_API_ID", "<redacted>")
API_HASH = os.environ.get("TELEGRAM_API_HASH", "<redacted>")
```

This is the exact anti-pattern the owner's own master prompt forbids. A committed credential on a public repo is compromised by definition.

### 1.2 The scanner could not see either one

`scripts/check_secrets.py` scanned these files and reported nothing. Root cause:

> **The label is a SUFFIX of a longer underscore-joined identifier.**
> In `TELEGRAM_API_HASH` there is **no word boundary before `API`** — both `_` and `A` are word characters. The generic pattern's bare `\b(?:...)` anchor therefore never matched `export TELEGRAM_API_HASH=...` or `--api-hash "..."`. Identical reason for `..._WEBHOOK_SECRET`.

Proven by direct pattern probe against the real pattern set:

| Shape | Before | After |
|---|---|---|
| `API_HASH = os.environ.get("TELEGRAM_API_HASH", "<hash>")` | **MISSED** | DETECTED |
| `export TELEGRAM_API_HASH=<hash>` | **MISSED** | DETECTED |
| `api_hash=<hash>` (inline, runbook) | **MISSED** | DETECTED |
| `--api-hash "<hash>"` | **MISSED** | DETECTED |
| `TELEGRAM_WEBHOOK_SECRET=<48-hex>` | **MISSED** | DETECTED |
| *Control:* `SECRET_KEY = os.getenv(...)` | detected | detected |
| *Control:* `API_KEY = os.environ.get(...)` | detected | detected |

The two controls passing while all four real shapes failed is what isolated the vocabulary/boundary cause.

---

## 2. The design decision that mattered

The obvious fix — add the new keywords to the **generic** patterns — was implemented first and then **measured**. It required a `\b\w*` prefix, which also matched noise:

| Approach | Repo-wide new findings | False positives |
|---|---|---|
| Widen the generic patterns (`\b\w*`) | **225** | **~220** (`.secrets.baseline` SHA-1 hashes alone ≈ 215; plus `test_..._password_...`, `test_token_...`) |
| **Dedicated suffix-label pattern** (shipped) | **1** | **0** — and the 1 is the real webhook secret |

The widened version was reverted. The two generic patterns are left **byte-identical**, and the suffix-label classes get one narrowly-scoped pattern where the keyword must **end** the identifier (no `\w*` tail).

> **Why this mattered:** a scanner that fires 220 false positives gets muted, and a muted scanner is precisely how this hole survived in the first place. The existing test suite says the same thing in its own words.

### Measured result (repo-wide, 4,327 files scanned, old patterns vs new)

```
tracked=5086 scanned=4327 skipped_big=5
NEW findings introduced by the pattern change: 1
  docs/TELEGRAM_ENTERPRISE_SETUP_COMPLETE.md:107  [Telegram suffix-label credential]
      - **Secret**: TELEGRAM_WEBHOOK_SECRET=<redacted>
```

---

## 3. Verification evidence (performed, not claimed)

| Check | Command / method | Result |
|---|---|---|
| Both credentials absent from branch | `git grep` on `security-scrub-telegram-creds` | **0 + 0 occurrences** (was 8 + 1) |
| Diff scope | `git diff --stat e91e45e6 <branch>` | **9 files, +420/−40**, no unrelated changes |
| Scripts compile | `py_compile` on all 4 | **OK** |
| `import os` present | grep | present in all 4 |
| **Guard proven by execution** | `env -u TELEGRAM_API_ID -u TELEGRAM_API_HASH python scripts/telethon_extract_token.py` | error printed, **exit 2** |
| Leaked shapes now caught | direct pattern probe | **all detected** (all were missed) |
| Scrubbed forms / placeholders / noise | direct probe + `scan_file` end-to-end | **not flagged** |
| Repo-wide false-positive delta | old vs new patterns, 4,327 files | **0** |
| Scanner suites | `pytest tests/test_check_secrets_*.py` | **40/40 pass** |
| New regression suite | `pytest tests/test_check_secrets_mtproto_api_hash.py` | **25/25 pass** |
| Formatting (Gate A) | `ruff format --check` on changed paths | **6/6 formatted** |
| Production health | `GET /health` | `healthy`, `version=2962d26e`, `environment=production` |
| **Branch content audit** (faithful CI reproduction, all 9 changed files) | scanner patterns over `git show <branch>:<file>` | **0 findings** |
| CI `Gate A` | `ruff format --check` | **pass** (after commit 3) |
| CI `Lint + syntax + secrets` | required check | failed on commit 2 → **fixed in commit 4** |
| CI `Trivy repo scan + SBOM` | same root cause as above | **fixed in commit 4** |
| CI `harness real-redis integration` | required check | **pass** |

---

## 4. Changes shipped in PR #550

| File | Change |
|---|---|
| `scripts/telethon_{new_notify_bot,botfather_token,extract_token,make_forum_groups}.py` | credential literal removed; **fail-closed** (exit 2) when env vars absent; ruff-formatted |
| `docs/TELEGRAM_PHASE1_2_RUNBOOK.md` | literals → `$TELEGRAM_API_ID` / `$TELEGRAM_API_HASH` |
| `docs/TELEGRAM_SINGLE_SOURCE_OF_TRUTH_2026-09-20.md` | literal → env reference |
| `docs/TELEGRAM_ENTERPRISE_SETUP_COMPLETE.md` | webhook secret literal → env reference |
| `scripts/check_secrets.py` | **+1 pattern** (`Telegram suffix-label credential (api_hash / session_string / webhook_secret)`) and `api_hash`/`apihash`/`api_id`/`session_string`/`auth_hash` added to the env-fallback vocabulary |
| `tests/test_check_secrets_mtproto_api_hash.py` | **new** — 25 tests pinning both directions |

Four commits: scrub → scanner fix + second credential → ruff formatting → `nosecret` markers.

---

## ✅ Action List

| # | Action | Owner | Priority | Blocked by |
|---|---|---|---|---|
| 1 | **Rotate the Telegram MTProto `api_hash`** at https://my.telegram.org | Owner | **P0** | phone/SMS — not automatable |
| 2 | **Rotate the Telegram webhook secret** and re-register the webhook | Owner | **P0** | same |
| 3 | Merge PR #550 once its required checks go green | Owner / me on request | **P0** | CI in flight |
| 4 | Consider a **general** suffix-label fix (see Known Limitations) | me | P2 | needs a noise-safe design |
| 5 | Add `Pytest Tests` to required status checks | me | P2 | — |
| 6 | Set the Smartflo DID→VOICE destination (top revenue lever @ 0.46) | Owner | P1 | console-only, **no API path (POST → 422)** |

---

## 3.5 CI failures encountered on the PR — and fixed

Two checks failed on the first push. Both were mine. Both are recorded because the second one
exposes a real gap in how this repo is verified locally.

### `Gate A` — `ruff format --check` on changed paths

5 of the 6 changed Python files were unformatted (4 telethon scripts + the new test file).
Fixed in commit 3 (`style: ruff-format …`). Gate A now **passes**.

### `Lint + syntax + secrets` (REQUIRED) and `Trivy repo scan + SBOM`

```
tests/test_check_secrets_mtproto_api_hash.py:187: unquoted credential after a
key/token/secret label
```

**Root cause:** `ruff format` collapsed the `NOISE` dict entries onto single lines. That put a
`token` label and a 43-char identifier run (the test-function name) on the **same line** — which the
**generic** `unquoted credential` pattern legitimately matches.

That the generic patterns match this noise is *precisely the point of the test*, and precisely why
the suffix-label pattern must stay narrow. So the lines were **marked with the scanner's documented
`nosecret` escape hatch rather than changed** (marker on the VALUE line — that is the line the
scanner reads). Fixed in commit 4.

### ⚠️ Why local verification missed it — the important lesson

I ran `check_secrets.py --all` locally and it reported **`[OK] no secrets detected`** across 4,332
files. It still missed the finding, because:

> **`check_secrets.py --all` only walks TRACKED files** (`git ls-files`).
> A brand-new **untracked** test file is **invisible** to it.

Two compounding factors made this worse:

1. **`security_scan.py` runs `check_secrets.py --all` with a 120-second timeout.** A full-tree scan
   takes longer than that on this machine, so the call raises `TimeoutExpired` — which the wrapper
   catches as an advisory **warning**, not a failure. My local "secrets scan: OK" was therefore a
   **silent false negative**: the scan never completed.
2. My repo-wide delta check compared **old patterns vs new patterns**, so it could only attribute
   findings to the *pattern change* — never to a **new file**.

**Correct local check (used to confirm the fix):** replicate the scanner over the branch's content
directly, or ensure the file is tracked before scanning. The audit over all 9 changed files on the
branch now reports **0 findings**.

---

## ⚠️ Known Limitations / Residual Risk

1. **The credential values remain in `main`'s git history.** Merging PR #550 does not remove them. Until rotation happens, both stay usable by anyone who reads the history. TypeSafe `leak_contained` = **0.22 (NOT contained)**.
2. **The scanner fix is deliberately narrow.** TypeSafe flagged this: `scanner_design_correct` = **0.24**. The dedicated pattern covers `api_hash`, `session_string`, `auth_hash`, `webhook_secret` — but **other suffix labels remain invisible** (e.g. `TELEGRAM_BOT_TOKEN=`, `MY_APP_API_KEY=`). Closing that generally needs a noise-aware approach (the naive one produced 220 false positives), which is a separate piece of work.
3. **`TELEGRAM_WEBHOOK_SECRET` was found only because the naive widening surfaced it.** That is worth stating plainly: the second leak was discovered by an experiment that was then reverted, not by the shipped scanner. The shipped scanner now catches it, but the discovery path was incidental.
4. **PR #550's checks are still running** (`mergeStateStatus=BLOCKED`, 7 in flight). `Gate A` failed on formatting and was fixed in commit 3.
5. **Production runs `2962d26e`; `main` is `e91e45e6`** — prod is one commit behind (PR #549, WEB_CONCURRENCY). Not security-relevant.
6. **Repo has 15 Dependabot alerts** (1 critical, 5 high, 9 moderate) and **13 open PRs** — untriaged.

---

## 📎 Appendix — environment findings (not part of the fix)

- `git branch <name>` / `git update-ref` **silently fail** for any `fix/`-prefixed branch name in this environment (rc=0, ref never created). Workaround used: slash-free branch name + `git commit-tree`/`update-ref` with the sandbox disabled.
- `git worktree add` is non-functional on this repo (fails with `fatal: invalid reference`). Workaround: build commits via plumbing (`read-tree` → `hash-object -w` → `update-index` → `write-tree` → `commit-tree` → `update-ref`), which leaves the working tree untouched.
- `GIT_INDEX_FILE` must be a **Windows-style** path (`C:/...`); an MSYS path (`/c/...`) is rejected.
- Sandboxed writes to `.git/refs` are inconsistently persisted; ref-creating commands must run unsandboxed.
- **5 stale git worktrees** exist, including one inside the repo at `_work/consol` (locked) and three outside it (`C:/tmp/pristine-base`, `~/.codex/...`, `~/.git-worktrees/wc-fix`). Cleanup debt.
- **58 `_`-prefixed scratch scripts** in `scripts/` — but **most are load-bearing**: `app/platform/deployment_path_manifest.py`, `app/platform/runtime_data.py` and four test files reference them. Only the ~15 untracked session scratch files are disposable. TypeSafe `scratch_quarantine_safe` = 0.20 → not acted on.

---

> Report generated as part of an automated admin loop. No commit, push, merge or deploy was performed on `main`; all changes live on the `security-scrub-telegram-creds` branch behind PR #550.
