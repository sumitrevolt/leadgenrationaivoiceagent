# Dependabot triage — 2026-08-16

Source: GitHub Dependabot alerts API for `sumitrevolt/leadgenrationaivoiceagent` on 2026-08-16.

## Summary

- Open alerts observed: `transformers` in `uv.lock`, `chromadb` in `uv.lock`, `pytest` in requirements manifests, `ecdsa` in `requirements.lock.txt`, and `nanoid` in `video_renderer/hyperframes/package-lock.json`.
- Fixed/closed alerts also exist for `hono`, `black`, `h2`, `aiosmtplib`, `sentry-sdk`, `cryptography`, `setuptools`, `starlette`, and `protobuf`.
- Follow-up remediation upgraded `nanoid` in `video_renderer/hyperframes` from `3.3.17` to `3.3.18`; treat all other rows as classification/evidence, not remediation.

## Open-alert classification

| Package | Manifest | Severity seen | Current disposition | Notes |
|---|---|---:|---|---|
| `transformers` | `uv.lock` | critical/high/medium/low | REVIEW before upgrade | Present in alternate uv lock. Production dependency truth remains `requirements.lock.txt`; do not claim fixed until the lock/source relationship is reconciled and image contents are proven. |
| `chromadb` | `uv.lock` | critical | REVIEW before upgrade/remove | Chroma is not canonical production vector store; Qdrant is canonical. Still needs lock hygiene because the advisory is open. |
| `pytest` | `requirements.txt`, `requirements-filtered.txt`, `requirements-dev.txt`, `requirements.lock.txt` | medium | DEV/TEST exposure | Test framework; not a request-serving app surface. Upgrade only with full test-gate confidence because pytest version bumps can alter fixtures/timeouts. |
| `ecdsa` | `requirements.lock.txt` | high | REVIEW before upgrade/remove | Need dependency-chain inspection before changing; do not remove blindly from auth/crypto stack. |
| `nanoid` | `video_renderer/hyperframes/package-lock.json` | high | PATCHED in follow-up branch | Updated `video_renderer/hyperframes` override/lock from `3.3.17` to `3.3.18`; `npm audit --audit-level=high` reports 0 vulnerabilities for that package tree. Await GitHub alert re-evaluation after merge. |

## Safe next actions

1. Reconcile why `uv.lock` is still alerting if `requirements.lock.txt` is the production truth.
2. For `nanoid`, merged follow-up should close alert #35 after Dependabot re-scans `video_renderer/hyperframes/package-lock.json`.
3. For `pytest`, plan a separate test-infra PR.
4. For `ecdsa`, inspect reverse dependencies before any upgrade/removal.
5. Re-run Dependabot API after each patch and attach the alert ids/URLs.

## Non-claims

- This triage does **not** claim “0 vulnerabilities” or “0 exploitable in prod”.
- This triage does **not** dismiss high/critical alerts; it separates immediate runtime risk from safe remediation order.
