"""Reachable dependency-CVE floors + the `--no-deps` blind spot that hid them.

WHY THIS FILE EXISTS
--------------------
`security-scan.yml` was green while 29 Dependabot alerts (8 high) sat open, and
`ci.yml` ran `pip-audit ... || true` against `requirements.txt` — not the
`requirements.lock.txt` that actually ships. A green badge asserted "the scan
ran", never "nothing vulnerable is pinned".

The root cause underneath the CVEs is narrower and worse: `Dockerfile.lock:25`
and both CI workflows install the lock with **`--no-deps`**, so pip never checks
that the pinned set is internally consistent. That is how the lock came to pair
`fastapi==0.141.1` (which declares `starlette>=0.46.0`) with `starlette==0.35.1`
— eleven minor series below its own floor, and squarely inside the multipart-DoS
advisory range. `--no-deps` will happily install any version written here, so an
install that succeeds proves nothing. These tests are the check `--no-deps` skips.

They live in the existing pytest job on purpose. That job is already a required
check and it runs locally, so the gate cannot be bypassed by a workflow simply
not being marked required — and it is a test, not a second dashboard.

A local failure here means the environment is stale, not that the test is wrong:

    pip install --no-deps -r requirements.lock.txt
"""

from __future__ import annotations

import io
import re
import ssl
from importlib.metadata import distributions, version
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

# NOTE: these three MUST be module-level. This file uses postponed annotations
# (`from __future__ import annotations`), so FastAPI resolves handler signatures
# via `get_type_hints` against the *module* globals. With `Request` imported
# inside a fixture instead, `Request` is unresolvable, FastAPI falls back to
# treating it as a query parameter, and every form request returns 422 before the
# handler ever runs — which silently satisfies a `>= 400` assertion and turns
# these regression tests into a false green. Found the hard way, 2026-08-08.

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "requirements.lock.txt"

# package -> (floor, why). Floor = the `first_patched_version` of the most
# demanding open advisory for that package, recovered from the GitHub Dependabot
# API on 2026-08-08.
FLOORS: dict[str, tuple[str, str]] = {
    "starlette": (
        "1.3.1",
        "GHSA-f96h-pmfr-66vw multipart DoS (high) - GHSA-wqp7-x3pw-xc5r UNC SSRF "
        "in StaticFiles (high) - GHSA-82w8-qh3p-5jfq form() limits ignored (high) "
        "- plus 3 medium/low",
    ),
    "cryptography": (
        "50.0.0",
        "GHSA-537c-gmf6-5ccf - GHSA-jwv3-5hgf-82ww - GHSA-g6cj-pr64-35w5 (all high, "
        "incl. vulnerable bundled OpenSSL)",
    ),
    "protobuf": ("5.29.6", "GHSA-7gcm-g887-7qv7 JSON recursion-depth bypass (high)"),
    "h2": ("4.4.1", "GHSA-6hr6-w5qg-qmwg (medium)"),
    "setuptools": ("83.0.0", "GHSA-h35f-9h28-mq5c (medium)"),
    "sentry-sdk": ("1.45.1", "GHSA-g92j-qhmh-64v2 (low) - Sentry is armed in prod"),
    "aiosmtplib": ("5.1.1", "GHSA-v3q9-hj7j-63hq (medium) - live email outreach path"),
}

# Documented, deliberate exceptions. Each MUST carry a reachability argument and
# an expiry; `test_exceptions_have_not_expired` fails the build when one lapses,
# so an exception cannot quietly become permanent.
EXCEPTIONS: dict[str, dict[str, str]] = {
    "ecdsa": {
        "ghsa": "GHSA-wj6h-64fc-37mp",
        "severity": "high",
        "fixed_version": "NONE - upstream has shipped no fix",
        "reachability": (
            "Minerva timing attack on P-256. Pulled in only by python-jose. "
            "`settings.jwt_algorithm` defaults to HS256 (app/config.py:261) - a "
            "symmetric MAC that never touches an EC curve. Unreachable unless the "
            "deployment overrides jwt_algorithm to ES256/ES384/ES512, which "
            "test_jwt_algorithm_is_symmetric pins."
        ),
        "expires": "2026-11-08",
    },
    "scrapy": {
        "ghsa": "PYSEC-2017-83",
        "severity": "medium",
        "fixed_version": "NONE - no upstream fix listed",
        "reachability": (
            "DoS by reading arbitrarily many files into memory, via the interaction "
            "between dataReceived and S3FilesStore. Surfaced by the new pip-audit "
            "gate on its first run (OSV carries it; the Dependabot list did not). "
            "Nothing imports scrapy - it arrives transitively through advertools - "
            "and the advisory's code path needs a files/images pipeline: no "
            "S3FilesStore, FILES_STORE or IMAGES_STORE is configured anywhere in "
            "app/ or scripts/."
        ),
        "expires": "2026-11-08",
    },
    "pytest": {
        "ghsa": "GHSA-6w46-j5rx-g56g",
        "severity": "medium",
        "fixed_version": "9.0.3",
        "reachability": (
            "tmpdir symlink pre-creation. pytest is a test runner: it is never "
            "imported by app code, so it is not on any request path. 7.4.4 -> 9.0.3 "
            "is a two-major bump across 750+ test files and would be the opposite of "
            "a minimum compatible upgrade. Deferred to its own slice."
        ),
        "expires": "2026-11-08",
    },
}

# Declared constraints that `--no-deps` cannot enforce. Watch the ones whose
# violation is actually dangerous rather than every edge in the graph.
CONSTRAINT_WATCHLIST = {"starlette", "protobuf", "cryptography"}


def _lock_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9._-]+)==([^\s#]+)", line.strip())
        if m:
            pins[m.group(1).lower().replace("_", "-")] = m.group(2)
    return pins


def _tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in re.findall(r"\d+", v)[:4])


# --------------------------------------------------------------------------- #
# 1. the lock itself - environment-independent, so this is the real CI gate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pkg", sorted(FLOORS))
def test_lockfile_meets_advisory_floor(pkg: str) -> None:
    floor, why = FLOORS[pkg]
    pins = _lock_pins()
    assert pkg in pins, f"{pkg} vanished from requirements.lock.txt"
    # Message hoisted to a local: this repo runs three formatters that disagree
    # about how to wrap a long assert (pre-commit black, pre-commit ruff v0.1.14,
    # Gate A's ruff format 0.16.1). A short assert takes the choice away from all
    # three, so this line stops ping-ponging between them.
    msg = f"lock pins {pkg}=={pins[pkg]}, below advisory floor {floor}.\n{why}"
    assert _tuple(pins[pkg]) >= _tuple(floor), msg


def test_lockfile_has_no_unpinned_or_duplicate_entries() -> None:
    """`--no-deps` installs the lock verbatim; a range or a dupe is a silent
    version lottery at image-build time."""
    seen: dict[str, int] = {}
    loose: list[str] = []
    for i, line in enumerate(LOCK.read_text(encoding="utf-8").splitlines(), 1):
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "==" not in s:
            loose.append(f"line {i}: {s}")
            continue
        name = re.split(r"==", s)[0].lower().replace("_", "-")
        if name in seen:
            loose.append(f"line {i}: {name} duplicated (first seen line {seen[name]})")
        seen[name] = i
    assert not loose, "requirements.lock.txt is not a strict pin set:\n" + "\n".join(loose)


# --------------------------------------------------------------------------- #
# 2. the --no-deps blind spot - the actual root cause
# --------------------------------------------------------------------------- #
def test_installed_set_satisfies_its_own_declared_constraints() -> None:
    """The check pip skips when `--no-deps` is passed.

    This is what let `fastapi==0.141.1` ship next to `starlette==0.35.1`. Scoped
    to CONSTRAINT_WATCHLIST so it stays a security guard, not a resolver.
    """
    from packaging.requirements import Requirement

    installed: dict[str, str] = {}
    for dist in distributions():
        name = (dist.metadata["Name"] or "").lower().replace("_", "-")
        if name:
            installed[name] = dist.version

    violations: list[str] = []
    for dist in distributions():
        owner = dist.metadata["Name"] or "?"
        for raw in dist.requires or []:
            try:
                req = Requirement(raw)
            except Exception:
                continue
            # Skip optional extras - they are not installed by the lock.
            if req.marker is not None and "extra" in str(req.marker):
                continue
            dep = req.name.lower().replace("_", "-")
            if dep not in CONSTRAINT_WATCHLIST or dep not in installed:
                continue
            if not req.specifier.contains(installed[dep], prereleases=True):
                violations.append(
                    f"{owner}=={dist.version} declares {dep}{req.specifier}, "
                    f"but {dep}=={installed[dep]} is installed"
                )

    assert not violations, (
        "The installed set violates its own declared constraints - exactly what "
        "`pip install --no-deps` cannot catch:\n  " + "\n  ".join(sorted(set(violations)))
    )


# --------------------------------------------------------------------------- #
# 3. runtime inspection - what is actually importable right now
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pkg", sorted(FLOORS))
def test_installed_version_meets_advisory_floor(pkg: str) -> None:
    floor, why = FLOORS[pkg]
    try:
        got = version(pkg)
    except Exception:
        pytest.skip(f"{pkg} not installed in this environment")
    assert _tuple(got) >= _tuple(floor), (
        f"installed {pkg}=={got} is below the advisory floor {floor}.\n{why}\n"
        "Refresh the environment: pip install --no-deps -r requirements.lock.txt"
    )


def test_cryptography_bundled_openssl_is_reported_and_modern() -> None:
    """One advisory is about the OpenSSL *bundled in the cryptography wheels*, so
    the pip version alone does not tell you which libcrypto is linked. Assert on
    the linked build."""
    from cryptography.hazmat.backends.openssl.backend import backend

    linked = backend.openssl_version_text()
    m = re.search(r"OpenSSL\s+(\d+)\.(\d+)", linked)
    assert m, f"could not parse linked OpenSSL from {linked!r}"
    series = (int(m.group(1)), int(m.group(2)))
    # 1.x and 3.0.x are the series carrying the advisories bundled in old wheels.
    assert series >= (3, 1), (
        f"cryptography is linked against {linked} - below the 3.1 floor. "
        f"stdlib ssl reports {ssl.OPENSSL_VERSION}"
    )


def test_jwt_algorithm_is_symmetric() -> None:
    """Pins the reachability argument behind the `ecdsa` exception. If JWT ever
    switches to an EC algorithm the Minerva exception stops being valid, and this
    says so instead of letting the exception go quietly stale."""
    from app.config import settings

    assert not str(settings.jwt_algorithm).upper().startswith("ES"), (
        "jwt_algorithm is now an EC algorithm - the `ecdsa` exception in EXCEPTIONS "
        "is no longer justified (GHSA-wj6h-64fc-37mp has no fix). Either revert to "
        "HS256/RS256 or escalate the exception to the owner."
    )


def test_exceptions_have_not_expired() -> None:
    from datetime import date

    today = date.today()
    stale = [
        f"{pkg} ({meta['ghsa']}, {meta['severity']}) expired {meta['expires']}"
        for pkg, meta in EXCEPTIONS.items()
        if date.fromisoformat(meta["expires"]) < today
    ]
    assert not stale, (
        "Time-limited dependency exceptions have lapsed - re-justify or remediate:\n  "
        + "\n  ".join(stale)
    )


# --------------------------------------------------------------------------- #
# 4. reachable behaviour - StaticFiles containment (GHSA-wqp7-x3pw-xc5r)
# --------------------------------------------------------------------------- #
@pytest.fixture
def static_app(tmp_path):
    """`app.main` mounts StaticFiles four times, including on `/`. This models
    that surface without importing the whole app."""
    public = tmp_path / "public"
    public.mkdir()
    (public / "ok.txt").write_text("public", encoding="utf-8")
    (tmp_path / "SECRET.txt").write_text("do-not-serve", encoding="utf-8")

    app = FastAPI()
    app.mount("/", StaticFiles(directory=str(public), html=False), name="root")
    return TestClient(app, raise_server_exceptions=False), tmp_path


def test_staticfiles_serves_only_inside_its_directory(static_app):
    client, _ = static_app
    assert client.get("/ok.txt").status_code == 200


@pytest.mark.parametrize(
    "path",
    [
        "/../SECRET.txt",
        "/..%2FSECRET.txt",
        "/%2e%2e/SECRET.txt",
        "/....//SECRET.txt",
        # UNC-shaped input - the GHSA-wqp7-x3pw-xc5r vector. On Windows an
        # unvalidated UNC path makes StaticFiles reach out over SMB, leaking an
        # NTLM handshake to an attacker-chosen host.
        "//attacker.example.com/share/x",
        "/%5C%5Cattacker.example.com%5Cshare%5Cx",
        "/C:/Windows/win.ini",
    ],
)
def test_staticfiles_refuses_traversal_and_unc_input(static_app, path):
    client, _ = static_app
    resp = client.get(path)
    assert "do-not-serve" not in resp.text, (
        f"StaticFiles leaked a file outside its directory for {path!r} "
        f"(status {resp.status_code}) - path containment is broken"
    )


# --------------------------------------------------------------------------- #
# 5. reachable behaviour - bounded form parsing
#    (GHSA-82w8-qh3p-5jfq / GHSA-f96h-pmfr-66vw / GHSA-2c2j-9gv5-cj73)
# --------------------------------------------------------------------------- #
@pytest.fixture
def form_client():
    app = FastAPI()

    @app.post("/form")
    async def read_form(request: Request):
        # Deliberately tiny limits: the advisory is that these were accepted and
        # then silently ignored for some content types.
        async with request.form(max_files=2, max_fields=2, max_part_size=1024) as form:
            return {"fields": len(form)}

    return TestClient(app, raise_server_exceptions=False)


def test_a_small_form_still_works(form_client):
    """Guards the two tests below from passing for the wrong reason. They assert a
    **client** error specifically, not `>= 400`: on starlette 0.35.1 those same
    limit kwargs raise `TypeError` inside the handler, which surfaces as a 500 and
    would have satisfied a `>= 400` assertion while proving nothing."""
    resp = form_client.post("/form", files={"f": ("ok.txt", io.BytesIO(b"x"), "text/plain")})
    assert resp.status_code == 200, resp.text


def test_multipart_file_limit_is_enforced(form_client):
    files = {f"f{i}": (f"f{i}.txt", io.BytesIO(b"x"), "text/plain") for i in range(6)}
    resp = form_client.post("/form", files=files)
    assert resp.status_code == 400, (
        f"6 parts against max_files=2 returned {resp.status_code}, expected 400. "
        "Unbounded multipart parsing is the GHSA-f96h-pmfr-66vw / "
        "GHSA-2c2j-9gv5-cj73 DoS vector (a 500 here means the limit kwargs are not "
        "supported at all, i.e. a pre-1.x starlette)."
    )


def test_urlencoded_form_limits_are_not_silently_ignored(form_client):
    """GHSA-82w8-qh3p-5jfq exactly: the limits passed to `request.form()` were
    honoured for multipart but silently dropped for
    `application/x-www-form-urlencoded`, so an attacker picked the content type
    and bypassed every bound."""
    body = "&".join(f"k{i}=v{i}" for i in range(200))
    resp = form_client.post(
        "/form",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert resp.status_code == 400, (
        f"200 urlencoded fields against max_fields=2 returned {resp.status_code}, "
        "expected 400 - form() limits are being ignored for urlencoded bodies "
        "(GHSA-82w8-qh3p-5jfq)."
    )


# --------------------------------------------------------------------------- #
# 6. the dependency change must not break what actually earns money
# --------------------------------------------------------------------------- #
def test_app_main_imports_after_dependency_change() -> None:
    import app.main

    assert app.main.app is not None


@pytest.mark.parametrize(
    "module",
    [
        # Product 1 - AI Marketing Automation
        "app.marketing.packages",
        "app.marketing.offers",
        "app.platform.upi_payments",
        "app.api.upi_payments",
        "app.marketing.product_one_delivery",
        # Product 2 - standalone AI Voice
        "app.marketing.voice_packages",
        "app.telephony.voice_launch",
        "app.telephony.compliance",
        "app.voice_agent.telecaller_brain",
    ],
)
def test_revenue_critical_modules_import(module: str) -> None:
    __import__(module)
