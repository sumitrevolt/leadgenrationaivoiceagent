"""Regression guard for the `.pem` SKIP_EXT blind spot in the secret scanners.

2026-09-19 P0: two RSA "-----BEGIN PRIVATE KEY-----" blocks were tracked in this  # nosecret
PUBLIC repo at ``app/telephony/freeswitch/conf/tls/{wss,dtls-srtp}.pem``. The
project's OWN secret scanners did not catch them, because BOTH
``scripts/check_secrets.py`` and ``scripts/security_scan.py`` listed ``.pem`` in
``SKIP_EXT`` on the (wrong) rationale that a PEM is an "ephemeral dev cert, not a
secret". GitGuardian caught them instead.

The flaw was a category error: a ``.pem`` is a CONTAINER, not a format guarantee.
It can hold a private key, and ``check_secrets.py`` already had a
``private key block`` pattern that would have matched — it was simply never given
the file.

These tests pin the corrected behaviour from BOTH directions:

  1. ``.pem`` MUST be scanned, and a private-key block inside one MUST be flagged;
  2. public-certificate formats (``.crt``/``.cer``/``.der``) stay skipped, because a
     scanner that cries wolf on every cert is a scanner that gets muted — and being
     muted is exactly how the hole survived.

Any key material used here is an obviously-synthetic dummy, never a real credential.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


cs = _load("check_secrets_pem_under_test", "scripts/check_secrets.py")
ss = _load("security_scan_pem_under_test", "scripts/security_scan.py")

# Synthetic only — a structurally valid header with an obviously fake body.
FAKE_PEM = (
    "-----BEGIN PRIVATE KEY-----\n"  # nosecret
    "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt9Us8cKj\n"
    "-----END PRIVATE KEY-----\n"
)


@pytest.mark.parametrize(
    "mod_name,mod",
    [("check_secrets", cs), ("security_scan", ss)],
)
def test_pem_is_no_longer_skipped(mod_name, mod):
    """`.pem` must NOT be in SKIP_EXT — that entry WAS the blind spot."""
    assert ".pem" not in {e.lower() for e in mod.SKIP_EXT}, (
        f"{mod_name}.SKIP_EXT still excludes .pem — a private key in a .pem would "
        "go undetected again (2026-09-19 P0 regression)."
    )


@pytest.mark.parametrize(
    "mod_name,mod",
    [("check_secrets", cs), ("security_scan", ss)],
)
def test_public_cert_formats_still_skipped(mod_name, mod):
    """Public certificate containers stay excluded so the scanner is not muted."""
    skipped = {e.lower() for e in mod.SKIP_EXT}
    for ext in (".crt", ".cer", ".der"):
        assert ext in skipped, f"{mod_name}.SKIP_EXT should still skip {ext}"


@pytest.mark.parametrize(
    "mod_name,mod",
    [("check_secrets", cs), ("security_scan", ss)],
)
def test_should_scan_accepts_pem(mod_name, mod):
    assert mod.should_scan("app/telephony/freeswitch/conf/tls/wss.pem") is True, (
        f"{mod_name}.should_scan() still rejects .pem files"
    )


def test_private_key_block_in_pem_is_detected(tmp_path, monkeypatch):
    """End-to-end: a private key block inside a .pem MUST be reported.

    `scan_file` resolves paths against the module-level ROOT, so ROOT is pointed at
    pytest's tmp_path rather than writing a probe file into the repo.
    """
    monkeypatch.setattr(cs, "ROOT", tmp_path)
    (tmp_path / "probe.pem").write_text(FAKE_PEM, encoding="utf-8")
    assert cs.should_scan("probe.pem") is True
    findings = cs.scan_file("probe.pem")
    assert findings, "scan_file() reported nothing for a .pem holding a private key block"
    assert any("private key block" in f for f in findings), findings


def test_repo_tracks_no_private_key_material():
    """Repo-wide invariant: no tracked .pem/.key/.p12/.pfx/.jks files at all.

    The two FreeSWITCH PEMs were the only tracked key material. Re-introducing any
    is a regression of the 2026-09-19 fix, so fail loudly rather than silently.
    """
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, timeout=60
    ).stdout
    tracked = [
        line.strip()
        for line in out.splitlines()
        if line.strip().lower().endswith((".pem", ".key", ".p12", ".pfx", ".jks"))
    ]
    assert tracked == [], f"tracked private-key material re-appeared: {tracked}"
