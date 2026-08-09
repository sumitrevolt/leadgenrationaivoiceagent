# CodeQL py/path-injection investigation — 2026-08-08

Four `py/path-injection` HIGH alerts (GitHub alert IDs #572–575) reported on
`app/platform/workforce_memory.py`, first seen 2026-08-06. PR #288 (merged
2026-08-08) does **not** touch this file — the alerts predate it and are
**rediscovered, not introduced** by that PR. Investigation below is primitive
evidence (rule, file, line, source-to-sink, reachability), not vibes.

Branch: `fix/ci-security-truth-2026-08-08`, base `origin/main` `822cae0b`.

---

## The two structural defences (why most of these are safe)

1. **Agent ids are regex-gated** (`app/platform/workforce_memory.py:71`):

   ```python
   _AGENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
   ```

   No dots, no slashes, no separators, ASCII lowercase only — a `_safe_agent`
   pass makes path traversal structurally impossible, and every caller of the
   module's public functions runs it.

2. **Tenant ids are never raw in a path.** `_agent_dir` routes the tenant
   component through `_tenant_key()`, which sha256-hexdigests it before it
   reaches any join. Hexdigest charset = `[0-9a-f]` — cannot contain `/`, `..`
   or `\`. A hostile tenant string can therefore never climb the tree.

---

## Alert-by-alert

### #572 + #573 — `_append_entry` (lines 230/236, `entries_path` join) — **FIXED**

**Sink:** `_append_entry` builds `entries_path` with the raw `agent_id`
argument and `os.path.join` → `open(..., "a")` (write).

**Source-to-sink:** the module's own boundary. The only caller, `remember()`,
pre-validates with `_safe_agent`, but `_append_entry` itself trusts its
argument — a future caller (or a direct import) could pass a hostile id and get
an arbitrary file **append** (not truncate) on disk.

**Reachability:** no current HTTP surface passes a raw agent id here —
`app/api/workforce_memory_admin.py` is `require_admin`-gated and validates
first. So today it is defense-in-depth, not a live exploit.

**Fix (minimal, additive):** re-validate inside `_append_entry` —
`aid = _safe_agent(agent_id)`; return `False` on failure; also reject a
non-empty, invalid `tenant_id`. Paths now use only the validated `aid`.

**Test:** `tests/test_workforce_memory_path_injection.py` (6 cases — hostile
agent id and hostile tenant id are rejected at the sink; valid ids still write).

### #574 — `offload_ref` (line 289, `ref_path` join) — **structurally safe, documented**

**Sink:** `ref_path = os.path.join(rd, f"{node_id}.md")` where `rd =
_refs_dir(aid, tenant_id)`.

**Source-to-sink analysis:**
- `agent_id` already passed `_safe_agent` earlier in the function (the guard is
  in the same function body, above the join) → regex-gated.
- `tenant_id` (the only remaining attacker input) is **hashed** by
  `_tenant_key()` before it enters `_agent_dir`, and `node_id` is a fresh
  `uuid4().hex` — neither can traverse.

**Verdict:** false positive. No path component under attacker control reaches
the join unvalidated or unhashed. Documented here rather than changing code
(the existing behaviour is correct); CodeQL cannot see that `_tenant_key()` is a
hash, hence the alert.

### #575 — `hub_snapshot` (line 929, `os.path.join(root, name, ...)`) — **hardened**

**Sink:** `os.listdir(root)` names are joined into read-only probe paths
(`entries.jsonl`, `tenants/`, `scoped_paths`).

**Source-to-sink:** every directory under `root` is created by `_agent_dir`
from `_safe_agent`-validated ids, and the joins are only used for `os.path.isdir`
/ `os.path.exists` probes (never open/write). A hostile name could at worst be
probed, and no current code can create one.

**Verdict:** low risk, but the join is unfiltered — a stray or manually-placed
directory name would be joined and probed. **Hardened:** skip any listing entry
that does not match `_AGENT_RE` before it reaches a join. Test added in the same
file above.

---

## Dismissal mechanism

CodeQL runs as GitHub default setup (no `codeql.yml` in this repo), so the
repository-approved suppression path is the alert-dismiss API with a documented
reason — there is no in-repo config to add, and nothing here disables or
weakens the CodeQL gate. After this PR lands on `main`, CodeQL re-analyzes:
#572/#573/#575 change the sink shape and should auto-close; if any persist,
dismiss with `reason: false positive` and reference this file.

---

## Verification status

| check | result |
|---|---|
| `tests/test_workforce_memory_path_injection.py` | 6 passed |
| `tests/test_workforce_memory_2026_08_03.py` (+ related suites) | pass |
| Ruff Gate-A (`ruff format --check`, 0.16.1) on changed files | clean |
| `scripts/check_secrets.py` | OK |
| `scripts/prod_check.py` | ALL PASSED |
| Security floor tests (local venv) | venv drift (sentry-sdk 1.39.2 vs lock 1.45.1) — CI-installed env is green; not caused by this diff |
