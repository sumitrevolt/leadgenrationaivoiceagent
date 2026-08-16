# Dependabot triage — 2026-08-16 (updated 2026-08-17)

Source: GitHub Dependabot alerts API for `sumitrevolt/leadgenrationaivoiceagent`.

## Summary

- Open alerts observed: `transformers` ×17 + `chromadb` in `uv.lock`, `pytest` in requirements manifests, `ecdsa` in `requirements.lock.txt`, and `nanoid` in `video_renderer/hyperframes/package-lock.json`.
- Fixed/closed alerts also exist for `hono`, `black`, `h2`, `aiosmtplib`, `sentry-sdk`, `cryptography`, `setuptools`, `starlette`, and `protobuf`.
- Follow-up remediation #1: `nanoid` patched `3.3.17 → 3.3.18` in `video_renderer/hyperframes` (PR #385, merged, prod `47605d12`).
- Follow-up remediation #2: **`uv.lock` deleted** — proven stale artifact (see below), removing 22 open alerts at their source.

## `uv.lock` — stale artifact, DELETED (2026-08-17)

Evidence chain:

- `uv.lock` was committed **once** in `673cd340` (2026-08-14, "preserve uncommitted dsh runtime leftovers — ADR-179 rejected — **NOT for main**") — an accidental sweep commit; never modified after.
- **Zero consumers:** no `uv` reference in `.github/workflows/*.yml`, `docker-compose.vps.yml`, `Dockerfile.lock`, `scripts/`, no `uv.toml`, no `.python-version`, no `[tool.uv]` in `pyproject.toml`. Only pyproject hit is the unrelated `uvicorn` package name.
- Repo packaging truth = `requirements.lock.txt` (274 lines, single source per CLAUDE.md); `requirements.txt`/`pyproject.toml` = reference only. Neither `transformers` nor `chromadb` appears in `requirements.lock.txt` — the 18 transformers/chromadb alerts were **uv.lock-only**.
- All transformers/chromadb advisories (CVE-2023-2800 … CVE-2026-45829, incl. ReDoS/deserialization/ACE) require loading untrusted model configs or Trainer execution — not reachable in prod even if the package were present.
- **Action taken:** `git rm uv.lock` + `.gitignore` entry `/uv.lock` (guard against the same accidental sweep re-commit). 22 alerts will close once GitHub re-scans the default branch.

## Open-alert classification (post-uv.lock-deletion)

| Package | Manifest | Severity seen | Current disposition | Notes |
|---|---|---:|---|---|
| `pytest` | `requirements.txt`, `requirements-filtered.txt`, `requirements-dev.txt`, `requirements.lock.txt` | medium | DEV/TEST exposure | CVE-2025-71176 (tmpdir handling). Test framework, not a request-serving app surface. Upgrade = separate test-infra PR with full test-gate confidence (pytest version bumps can alter fixtures/timeouts). |
| `ecdsa` | `requirements.lock.txt` | high | NO-FIX, not exploitable in app usage | CVE-2024-23342 (Minerva timing attack on P-256). GitHub advisory: vulnerable range `>= 0`, **no patched version exists**. App uses **HS256 exclusively** for every JWT encode/decode (`app/config.py`, `app/utils/auth.py`, `app/utils/jwt_versioning.py`, admin/impersonation/middleware) — ECDSA/ES256 code path never exercised. Transitive via `python-jose==3.5.0` hard dep; removing breaks install. |
| `nanoid` | `video_renderer/hyperframes/package-lock.json` | high | PATCHED (PR #385) | Override/lock at `3.3.18`; `npm audit --audit-level=high` = 0 vulnerabilities. Await GitHub re-evaluation. |

## Safe next actions

1. ~~Reconcile why `uv.lock` is still alerting~~ → done: stale artifact, deleted, 22 alerts closed at source.
2. `pytest`: separate test-infra PR (bump within 8.x/9.x, run full suite + CI shards, then merge).
3. `ecdsa`: keep pinned `0.19.2`; no fix exists and the vulnerable path is unreachable (HS256-only). Re-check advisory for a patched release periodically.
4. Re-run Dependabot API after each patch and attach the alert ids/URLs.

## Non-claims

- This triage does **not** claim "0 vulnerabilities" or "0 exploitable in prod" — the `pytest` and `ecdsa` alerts remain open.
- This triage does **not** dismiss high/critical alerts; it separates immediate runtime risk from safe remediation order.
