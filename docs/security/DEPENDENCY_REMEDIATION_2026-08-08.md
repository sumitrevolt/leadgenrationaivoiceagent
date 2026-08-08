# Dependency remediation — CP5-3, 2026-08-08

Closes the highest-severity finding of the 2026-08-08 readiness recovery
(`docs/context/ENTERPRISE_READINESS_2026-08-08.md`, CP5-3): **29 open Dependabot
alerts, 8 high, behind a green `security-scan.yml`.**

- Branch `fix/dep-cve-2026-08-08`, base `origin/main` `5ae5a4b9`
- Alert state recovered live from
  `gh api repos/sumitrevolt/leadgenrationaivoiceagent/dependabot/alerts?state=open`
- Production at the time: `/health.version` = `42493e3f`

---

## 1. Root cause — the lock is not installable by a resolving pip

The CVEs are the symptom. The cause is that nothing ever checked the pinned set
was coherent:

| where | how the lock is installed |
|---|---|
| `Dockerfile.lock:25` (the production image) | `pip install --no-deps -r req.filtered` |
| `.github/workflows/ci.yml:106` (`tests` job) | `pip install --no-deps -r req.filtered` |
| `.github/workflows/tests.yml:35` | `pip install --no-deps -r requirements.lock.txt` |

`--no-deps` tells pip to install exactly what it is given and check nothing. So
the lock drifted into a combination pip itself rejects:

```
$ pip install "fastapi==0.141.1" "starlette==0.35.1"
ERROR: Cannot install fastapi==0.141.1 and starlette==0.35.1 because these
       package versions have conflicting dependencies.
ERROR: ResolutionImpossible
```

`fastapi==0.141.1` declares `starlette>=0.46.0`. The lock pinned **`starlette==0.35.1`
— released 2024-01-11**, two and a half years older than the FastAPI beside it, and
inside the range of three separate high-severity advisories. `sse-starlette==3.4.6`
(`starlette>=0.49.1`) and `google-api-core==2.31.0` (`protobuf>=5.29.6`, lock had
`4.25.9`) were violated the same way.

**A fourth violation was found by the new gate itself**, on its first CI run:
`packaging==23.2` against `google-cloud-bigquery==3.42.3`'s `packaging>=24.2.0`.
Nothing in this slice touched `packaging` — the resolver surfaced it the moment a
resolution was attempted for the first time. Bumped to `packaging==25.0`. That is
the gate doing its job on day one, and it is the reason the drift is best described
as a class of defect rather than a list of CVEs.

An install "succeeding" under `--no-deps` therefore proves nothing at all. That is
the check `tests/test_dependency_security_floors.py` now performs.

## 2. Remediation ledger

Every open alert. `reachable` = is there a code path in this application?

### Fixed — 7 pins raised

| GHSA | sev | package | was | now | source | reachable in prod? | advisory |
|---|---|---|---|---|---|---|---|
| GHSA-f96h-pmfr-66vw | high | starlette | 0.35.1 | **1.3.1** | direct (fastapi) | **yes** — multipart on the live request path | DoS via `multipart/form-data` |
| GHSA-wqp7-x3pw-xc5r | high | starlette | 0.35.1 | **1.3.1** | direct | **dev only** — see §3 | SSRF + NTLM theft via UNC paths in `StaticFiles` |
| GHSA-82w8-qh3p-5jfq | high | starlette | 0.35.1 | **1.3.1** | direct | **yes** | `request.form()` limits silently ignored for `x-www-form-urlencoded` |
| GHSA-x746-7m8f-x49c | med | starlette | 0.35.1 | **1.3.1** | direct | low — no `HTTPEndpoint` subclass in `app/` | arbitrary method dispatched via `getattr` |
| GHSA-86qp-5c8j-p5mr | med | starlette | 0.35.1 | **1.3.1** | direct | **yes** | missing Host validation poisons `request.url.path` |
| GHSA-2c2j-9gv5-cj73 | med | starlette | 0.35.1 | **1.3.1** | direct | **yes** | DoS parsing large multipart files |
| GHSA-jp82-jpqv-5vv3 | low | starlette | 0.35.1 | **1.3.1** | direct | **yes** | unvalidated path poisons `request.url.hostname` |
| GHSA-537c-gmf6-5ccf | high | cryptography | 48.0.0 | **50.0.0** | direct | **yes** — TLS/JWT | duplicate self-signed intermediates |
| GHSA-jwv3-5hgf-82ww | high | cryptography | 48.0.0 | **50.0.0** | direct | **yes** | PKCS#7 `EnvelopedData` Bleichenbacher oracle |
| GHSA-g6cj-pr64-35w5 | high | cryptography | 48.0.0 | **50.0.0** | direct | **yes** | vulnerable OpenSSL in the wheels |
| GHSA-m2h6-j472-rp4c | med | cryptography | 48.0.0 | **50.0.0** | direct | **yes** | — |
| GHSA-7gcm-g887-7qv7 | high | protobuf | 4.25.9 | **5.29.6** | transitive (google-*) | low — no `google.protobuf` import in `app/`, `ENABLE_OTEL` unset | JSON recursion-depth bypass |
| GHSA-6hr6-w5qg-qmwg | med | h2 | 4.4.0 | **4.4.1** | transitive (httpx/Twisted) | low — HTTP/2 not enabled on outbound clients | — |
| GHSA-h35f-9h28-mq5c | med | setuptools | 82.0.1 | **83.0.0** | transitive | build-time | — |
| GHSA-v3q9-hj7j-63hq | med | aiosmtplib | 3.0.1 | **5.1.1** | direct | **yes** — live cold-email outreach | — |
| GHSA-g92j-qhmh-64v2 | low | sentry-sdk | 1.39.2 | **1.45.1** | direct | **yes** — Sentry is armed in prod | — |
| GHSA-fj7x-q9j7-g6q6 | med | black | 24.1.1 | **24.3.0** | dev manifest only | no | — |

`protobuf 4.25.9 -> 5.29.6` also repairs a broken constraint:
`google-api-core==2.31.0` already required `protobuf>=5.29.6`.

`starlette` target is **1.3.1**, not latest. 1.3.1 (2026-06-12) is the *lowest*
version that clears all seven advisories — the minimum compatible upgrade.
1.5.0 was released the same day as this work and was deliberately not taken.

### Accepted — time-limited exceptions

Both are mirrored in `tests/test_dependency_security_floors.py::EXCEPTIONS` and in
`ci.yml`'s `--ignore-vuln` flags. `test_exceptions_have_not_expired` turns the build
RED the day one lapses, so neither can quietly become permanent.

| GHSA | sev | package | fix | why accepted | expires |
|---|---|---|---|---|---|
| GHSA-wj6h-64fc-37mp | **high** | ecdsa 0.19.2 | **none exists** | Minerva timing attack on P-256. Reaches the app only through `python-jose`, and `settings.jwt_algorithm` defaults to **HS256** (`app/config.py:261`) — a symmetric MAC that never touches an EC curve. Pinned by `test_jwt_algorithm_is_symmetric`, which fails if JWT ever moves to ES256/384/512. | 2026-11-08 |
| GHSA-6w46-j5rx-g56g | med | pytest 7.4.4 | 9.0.3 | tmpdir symlink pre-creation. pytest is never imported by app code, so it is on no request path. 7.4.4 → 9.0.3 is a two-major bump across 750+ test files — the opposite of a minimum compatible upgrade. Own slice. | 2026-11-08 |

### Out of scope — not this runtime

| GHSA | sev | package | why |
|---|---|---|---|
| GHSA-8j4g-w8fx-2239 | med | hono (npm) | `video_renderer/hyperframes/package-lock.json` — a JS renderer, not in the Python application image. Belongs to a `video_renderer` slice. |

## 3. Reachability note — the UNC advisory is Windows-scoped

GHSA-wqp7-x3pw-xc5r ("SSRF and NTLM credential theft via UNC paths in
`StaticFiles` **on Windows**") is high severity and `app/main.py` mounts
`StaticFiles` four times, including on `/` (`app/main.py:1309, 1316, 1350, 2539`).

Production runs `python:3.12-slim` (`Dockerfile.lock:13`) — Linux, where UNC paths
carry no meaning, so the credential-theft vector is **not reachable in production**.
It **is** reachable on the Windows developer machines this repo is worked on daily.
Recorded as a severity distinction, not a dismissal; it is fixed either way.

## 4. Verification

Full-tree local verification was **blocked**, and the reason is itself worth
recording: the repo `.venv` is **Python 3.11.14** while the runtime image is
**python:3.12-slim**, and the lock is 3.12-built — `multidict==6.7.1` and
`pydantic-core==2.41.6` have no 3.11 wheels. CLAUDE.md §3 says "dev, py3.12"; the
local environment has drifted. So:

| # | check | environment | result |
|---|---|---|---|
| 1 | `pip install fastapi==0.141.1 starlette==0.35.1` (resolving) | clean 3.11 venv | **ResolutionImpossible** — root cause proven |
| 2 | `pip install fastapi==0.141.1 starlette==1.3.1 cryptography==50.0.0` (resolving) | clean 3.11 venv | resolves cleanly |
| 3 | 12 behaviour tests (StaticFiles containment incl. UNC, multipart bounds, urlencoded bounds, linked OpenSSL) | upgraded venv | **12 passed** |
| 4 | same 12 tests against the shipped combination forced with `--no-deps` | pre-upgrade venv | **1 failed, 11 errors** — `request.form(max_files=…)` raises `TypeError` (the bounded-parsing API does not exist in 0.35.1); OpenSSL floor fails |
| 5 | the 4 starlette symbols `app/` imports (`BaseHTTPMiddleware`, `GZipMiddleware`, `JSONResponse`, `Response`) | starlette 1.3.1 | all present |
| 6 | FastAPI's own constraint | — | `fastapi==0.141.1` (2026-07-29) declares `starlette>=0.46.0` with **no upper bound**, and post-dates `starlette 1.0.0` (2026-03-22) — the open range is deliberate |
| 7 | full-tree `import app.main` under the amended lock | **not run locally** | blocked by the 3.11/3.12 gap above; runs in CI, which installs the lock on the correct Python |
| 8 | built runtime image scan | **not run** | image build pulls torch/pipecat/kokoro/rembg; `Trivy image scan (GHCR)` is currently **SKIPPED** in CI — see §5 |

The app's direct starlette surface is only those four long-lived symbols, which is
why a 0.35 → 1.3 jump is far less invasive than the version numbers suggest.

## 5. Repairing the signal, without a second dashboard

Two hollow gates, one fixed here and one left alone on purpose:

1. **`ci.yml` "Dependency vulnerability scan"** — labelled `MUST-PASS — no known
   CVEs in dependencies`, but the command ended in `|| true` and audited
   `requirements.txt`, a *reference* manifest, not the `requirements.lock.txt` the
   image installs. It now **blocks**, and carries the two exceptions as explicit
   `--ignore-vuln` flags.

   It also **moved from the lint job to the `tests` job**, and audits the *installed
   environment* rather than a requirements file. That was forced by evidence, not
   preference: the first blocking run failed with `ResolutionImpossible` on
   `packaging==23.2`, because auditing a requirements *file* makes pip-audit
   re-resolve the lock — producing a set that nothing in this project ever installs,
   since every real install passes `--no-deps`. The `tests` job already installs the
   lock exactly as `Dockerfile.lock` does, so auditing that environment needs no
   resolver and describes precisely what ships. pip-audit runs from its own venv and
   reaches the environment via `--path`, so its own dependencies cannot silently
   upgrade the packages being audited.
2. **`security-scan.yml`** — **not touched.** It is uncommitted-dirty in the primary
   checkout with an in-flight owner-approved CRITICAL gate of its own, and that
   checkout is on the dead pre-rewrite lineage (CP0-F1). Editing it would break the
   one-writer rule and be clobbered. Its own TODO already calls for the HIGH ratchet.
3. **`Trivy image scan (GHCR)` is SKIPPED** on PR runs, so the base-OS and
   system-package layer is not scanned at all. Owner item — not fixed here.

The real blocking gate added by this slice is
`tests/test_dependency_security_floors.py`, inside the **existing** required pytest
job. It is a test, not a dashboard: it runs locally, cannot be bypassed by a
workflow not being marked required, and asserts the lock, the installed set, the
`--no-deps` constraint blind spot, the reachable behaviours, and the exception
expiries.

## 6. Unrelated defect found while verifying — test suite writes to a real customer's ledger

Running the suite left `data/delivery_ledger/jiya-makeover.jsonl` modified — a
**tracked** file belonging to the only paying customer. The appended rows are
indistinguishable from real delivery events:

```
{"at": "2026-08-08T08:39:49+00:00", "client_id": "jiya-makeover", "event": "post_approved", ...}
{"at": "2026-08-08T08:41:15+00:00", "client_id": "jiya-makeover", "event": "plan_activated", "detail": "starter", "actor": "backfill", ...}
```

Timestamps match this session's shard run. `data/*` is in `.gitignore`, but ignore
rules do not apply to already-tracked files, so these show up as ordinary
modifications. Reverted here (`git checkout --`) and **not** committed.

Why it matters: the delivery ledger *is* the customer-visible proof Product 1
sells. Any agent that runs the suite and then does `git add -A` commits fabricated
delivery events for a paying customer. This is the concrete mechanism behind
`AGENT_WORK_RULES` R7 ("never `git add -A`") — the rule is not hygiene advice, it
is protecting this file.

Not fixed here: it needs a `tmp_path`-scoped ledger fixture (or untracking the
customer ledgers), which is its own slice. Raised in the Owner packet.

## 7. Residual risk

- `import app.main` under the amended lock is verified by CI, not locally (§4 row 7).
  If CI goes red on this PR, that is the finding — do not re-mute the gate.
- `pip-audit` could not be dry-run locally (`uvloop` is Linux-only), so the first CI
  run is the first real execution of the now-blocking step. If it surfaces vulns
  beyond this ledger, fix them or add them here with a justification and expiry.
- Nothing here was deployed. The production image still runs the pre-upgrade lock
  until the Owner approves a build.
