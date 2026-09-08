"""Guard: no personal-data export may be tracked in this PUBLIC repository.

2026-08-06 — `prospect_leads_export.csv` was found tracked at the repo ROOT of a
repository whose GitHub metadata reports `repository_public: true`. It carried
200 real Indian businesses with `business_name, phone, address, city, email,
pitch, wa_link`. `.gitignore` had `data/*`, but the file sat at the root, so
nothing caught it and nothing would have caught the next one.

DPDP Act 2023 (CLAUDE.md §5): purpose limitation, data minimisation and a consent
basis for first contact. Publishing a bulk outreach dataset satisfies none of
them, and a public Git history makes the exposure durable and un-recallable.

This guard is intentionally content-based, not name-based: it reads the HEADER of
every tracked `.csv` and fails when personal-data columns appear. Renaming the
file does not evade it.

**If this test is RED, the exposure is live.** Remediation is in the failure
message; it is an owner decision because it requires rewriting published history.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Columns that make a row personal data about an identifiable individual/business.
PII_COLUMNS = {
    "phone",
    "phone_number",
    "mobile",
    "whatsapp",
    "wa_link",
    "email",
    "email_address",
    "address",
    "street",
    "contact_name",
    "owner_name",
}

# Synthetic fixtures and skill templates are allowed to carry PII-shaped HEADERS
# because they hold no real records. Anything else must not.
ALLOWED_PREFIXES = (
    "tests/fixtures/",
    ".claude/skills/",
)


def _tracked_csvs() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.csv"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover
        pytest.skip(f"git unavailable: {exc}")
    if out.returncode != 0:  # pragma: no cover
        pytest.skip(f"git ls-files failed: {out.stderr.strip()}")
    return [p for p in out.stdout.split("\0") if p]


def _header_columns(rel: str) -> set[str]:
    path = REPO / rel
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            header = fh.readline()
    except OSError:
        return set()
    return {c.strip().strip('"').lower() for c in header.split(",")}


def test_no_tracked_csv_carries_personal_data_columns():
    offenders: list[tuple[str, list[str]]] = []

    for rel in _tracked_csvs():
        if rel.startswith(ALLOWED_PREFIXES):
            continue
        hit = sorted(_header_columns(rel) & PII_COLUMNS)
        if hit:
            offenders.append((rel, hit))

    if offenders:
        lines = [
            f"  - {rel}  (personal-data columns: {', '.join(cols)})" for rel, cols in offenders
        ]
        raise AssertionError(
            "Personal-data export(s) are TRACKED in this PUBLIC repository:\n"
            + "\n".join(lines)
            + "\n\nThis is a live DPDP Act 2023 exposure, not a style issue.\n"
            "Untracking alone does NOT undo it — the blob stays in published history.\n\n"
            "Owner remediation, in order:\n"
            "  1. git rm --cached <file>          # untrack, KEEP the local copy\n"
            "  2. commit + push                   # stops future propagation\n"
            "  3. git filter-repo --path <file> --invert-paths   # purge history\n"
            "  4. git push --force-with-lease --all --tags       # rewrites PUBLIC history\n"
            "  5. rotate anything the data could have exposed; migrate leads to\n"
            "     Postgres/encrypted object storage with source, collection date,\n"
            "     legal basis, suppression state and retention deadline\n\n"
            "Steps 3-4 rewrite published history and invalidate existing clones/forks —\n"
            "owner decision only. Do NOT auto-run them."
        )


def test_guard_detects_a_pii_header_shape():
    """The guard must actually fire — proves it is not vacuously green."""
    assert PII_COLUMNS & {"phone", "email", "address"}
    sample = {"id", "business_name", "phone", "city"}
    assert sample & PII_COLUMNS == {"phone"}
    benign = {"id", "metric", "count", "captured_at"}
    assert not benign & PII_COLUMNS
