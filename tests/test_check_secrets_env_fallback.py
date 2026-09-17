"""Regression guard for the check_secrets.py env-fallback blind spot.

2026-09-17: `python scripts/check_secrets.py --all` scanned 4272 tracked files and
printed "[OK] no secrets detected" while TWO live credentials sat in plain sight as
`os.getenv(...)` fallback defaults:

  * app/platform/typesafe_integration.py:13  (~100-char TypeSafe key, commit 7317f990)
  * scripts/hourly_audit.py:12               (32-char WAHA key)

All 12 pre-existing patterns missed both. Root cause: every pattern required a quote
(or an unquoted blob) IMMEDIATELY after `KEY =`, but the getenv form is
`KEY = os.getenv(` — the regex sees `= o`, so it never matches. `--all` mode was
never broken; the detection logic was.

These tests pin the fix from BOTH directions so the hole cannot silently reopen:
  1. the env-fallback leak shape MUST be caught, and
  2. legitimate config defaults MUST NOT be flagged (otherwise the scanner gets
     muted/ignored, which is how the hole survived in the first place).

The literal values below are OBVIOUSLY-SYNTHETIC dummies, never real credentials.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "check_secrets_under_test", ROOT / "scripts" / "check_secrets.py"
)
assert _SPEC and _SPEC.loader
cs = importlib.util.module_from_spec(_SPEC)
sys.modules["check_secrets_under_test"] = cs
_SPEC.loader.exec_module(cs)

_ENV_FALLBACK_LABEL = "env-lookup fallback literal (getenv/os.environ.get default)"


def _env_fallback_pattern():
    for label, pat in cs.PATTERNS:
        if label == _ENV_FALLBACK_LABEL:
            return pat
    pytest.fail(f"pattern {_ENV_FALLBACK_LABEL!r} missing from PATTERNS")


def _is_flagged(line: str) -> bool:
    """Mirror scan_file's decision for the env-fallback pattern only."""
    pat = _env_fallback_pattern()
    m = pat.search(line)
    if not m or cs.PLACEHOLDER.search(line):
        return False
    if m.groups() and cs.FALLBACK_ALLOW.match((m.group(1) or "").strip()):
        return False
    return True


# ---------------------------------------------------------------- must CATCH
#
# NOTE ON THE VALUES BELOW: they are synthetic and MUST NOT contain substrings
# matched by cs.PLACEHOLDER (`dummy`, `example`, `aaaa`, `1234567890`, ...), or
# the scanner's placeholder filter correctly suppresses them and the test would
# be asserting the wrong thing. High-entropy, clearly-not-real random strings.
#
# Each line carries a `nosecret` marker: this suite deliberately contains the
# leak SHAPE, so check_secrets.py must skip these lines or it self-triggers and
# turns CI red. The marker is the scanner's documented escape hatch.

LEAKS = {
    "typesafe shape (~100-char)": (
        'TYPEsafe_API_KEY = os.getenv("TYPEsafe_API_KEY", '  # nosecret
        '"y7q2v9n4x8k3m6p1w5r0t2j4h6g8s1d3f5b7l9c0z2a4e6i8o1u3")'
    ),
    "waha shape (32-char)": (
        'WAHA_API_KEY = os.environ.get("WAHA_API_KEY", "m4k8p2v6n1x9q3w7e5r0t2y4")'  # nosecret
    ),
    "generic hex blob": (
        'STRIPE_SECRET = os.getenv("STRIPE_SECRET", "9f3a2b8c7d6e5f4a1b2c3d4e5f6a7b8c9d0e")'  # nosecret
    ),
    "webhook secret": (
        'SMARTFLO_WEBHOOK_SECRET = os.environ.get("SMARTFLO_WEBHOOK_SECRET", '  # nosecret
        '"whsec_p7k2m9v4n1x6q3w8e5r0t2y7u4i1o6a3s8d5f0g2")'
    ),
}


@pytest.mark.parametrize("name", sorted(LEAKS))
def test_env_fallback_literal_is_flagged(name: str) -> None:
    line = LEAKS[name]
    assert _is_flagged(line), (
        f"REGRESSION: {name} not flagged. The env-fallback blind spot is back — "
        f"a live key in this shape would ship undetected.\n  line: {line}"
    )


def test_typefaced_getenv_form_is_flagged() -> None:
    """The original 7317f990 shape, abridged to a synthetic value."""
    line = 'TYPEsafe_API_KEY = os.getenv("TYPEsafe_API_KEY", "k3m7p1v5n9x2q6w8e4r0t2y7u1")'  # nosecret
    assert _is_flagged(line)


# ------------------------------------------------------------ must NOT flag

CLEAN = {
    "base url": 'API_BASE = os.getenv("API_BASE", "https://api-smartflo.tatateleservices.com")',
    "localhost": 'WAHA_URL = os.getenv("WAHA_URL", "http://localhost:3111")',
    "absolute path": 'LOG_PATH = os.getenv("LOG_PATH", "/opt/leadgen/data/hourly_audit.log")',
    "env mode": 'ENV = os.getenv("APP_ENV", "production")',
    "model name": 'LLM_MODEL = os.getenv("LLM_MODEL", "mistral-small-latest")',
    "db url": (
        'DATABASE_URL = os.getenv("DATABASE_URL", '
        '"postgresql://leadgen:pw@localhost:5432/leadgen_db")'
    ),
    "empty string": 'SOME_KEY = os.getenv("SOME_KEY", "")',
    "timezone": 'TZ = os.getenv("TZ", "Asia/Kolkata")',
}


@pytest.mark.parametrize("name", sorted(CLEAN))
def test_legitimate_config_default_is_not_flagged(name: str) -> None:
    line = CLEAN[name]
    assert not _is_flagged(line), (
        f"FALSE POSITIVE: {name} flagged. A noisy scanner gets muted, and a muted "
        f"scanner is how the blind spot survived.\n  line: {line}"
    )


# ------------------------------------------------------------------ plumbing


def test_allowlist_exists_and_is_tight() -> None:
    """FALLBACK_ALLOW must exist and NOT wave through an opaque blob."""
    assert hasattr(cs, "FALLBACK_ALLOW")
    assert not cs.FALLBACK_ALLOW.match("dummy0e0e6c2aa5b91413a88fd64c9e")
    assert cs.FALLBACK_ALLOW.match("https://api.example.com")
    assert cs.FALLBACK_ALLOW.match("/opt/leadgen/data/x.log")
    assert cs.FALLBACK_ALLOW.match("production")


def test_allowlist_does_not_swallow_a_url_with_embedded_credential() -> None:
    """A plain URL is config — a URL carrying `user:pass@` is a credential leak.

    Regression guard for the anchor bug found while writing this suite: the
    `https?://` alternative originally had no `\\S+` tail, so `.match()` failed
    every real URL. While fixing that, the `\\S+` tail must NOT become a
    blanket pass for credential-bearing URLs.
    """
    pat = _env_fallback_pattern()
    line = (
        'SERVICE_SECRET = os.getenv("SERVICE_SECRET", '
        '"https://admin:dummysecretvalue123456@internal.example.com")'
    )
    m = pat.search(line)
    assert m is not None, "URL-shaped secret was not matched at all"
    literal = (m.group(1) or "").strip()
    # A URL with embedded userinfo is NOT safe config — it must stay flagged.
    assert not cs.FALLBACK_ALLOW.match(literal), (
        "REGRESSION: a URL containing `user:pass@` was allowlisted as plain config. "
        "That hides a real credential. Require the allowlist to reject userinfo URLs."
    )
