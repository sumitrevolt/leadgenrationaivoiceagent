"""Fresh-host classification for the bootstrap entry point.

`hostinger_hermes_bootstrap.sh` runs `git reset --hard origin/main` against
`$LOCAL_DIR`. The default is a sandbox clone under `$HOME`, but the value is an
environment variable, so it can be pointed at `/opt/leadgen` -- where the live
invoice, consent and suppression ledgers and 182 MB of DPDP call recordings sit
inside the checkout. A default is not a restriction.

This module answers exactly one question: **is this target provably a fresh,
safe installation target?** It does not deploy, recover, or decide policy about
runtime-data roots -- that authority stays in `runtime_data.py`. Ambiguity is
resolved as REFUSE, never as "probably fine": the whole reason this file exists
is that a comment claiming sandbox-only behaviour was treated as evidence.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Classifications (exactly one is returned).
FRESH_HOST = "FRESH_HOST_BOOTSTRAP_ONLY"
EXISTING_HOST = "EXISTING_HOST_MUTATION_CAPABLE"
INVALID_TARGET = "INVALID_TARGET"

# Operator-facing status for a refusal on an existing installation.
EXISTING_INSTALL_STATUS = "EXISTING_INSTALLATION_REQUIRES_DEPLOY_OR_RECOVERY_PATH"

# Exit codes. Distinct from the release parent's 90/91 so an operator reading a
# log can tell a bootstrap refusal from a release-guard denial.
EXIT_OK = 0
EXIT_REFUSED = 92
EXIT_INVALID_TARGET = 93
EXIT_PREFLIGHT_UNAVAILABLE = 94

# Paths that are production installations by convention. Allowed only when
# proven empty AND explicitly authorised, never by default.
PROTECTED_ROOTS = ("/opt/leadgen",)

# Any of these inside the target means an installation already exists.
INSTALL_EVIDENCE_PATHS = (
    ".git",
    "data",
    "docker-compose.vps.yml",
    ".env",
    "runtime-data",
    ".runtime-data-cutover.json",
)

_MIN_FREE_BYTES = 512 * 1024 * 1024  # 512 MB


def _protected_form(raw: str) -> str:
    """Normalise a path for protected-root comparison: forward slashes, no drive."""
    s = str(raw).replace("\\", "/")
    if len(s) > 1 and s[1] == ":":  # strip 'C:' so C:/opt/leadgen matches /opt/leadgen
        s = s[2:]
    return s.rstrip("/") or "/"


def _reason(code: str, detail: str = "") -> dict[str, str]:
    return {"code": code, "detail": detail}


def _validate_path(raw: str) -> tuple[Path | None, list[dict[str, str]]]:
    """Structural validation before the filesystem is touched at all."""
    problems: list[dict[str, str]] = []
    if raw is None or not str(raw).strip():
        return None, [_reason("TARGET_EMPTY", "no target directory supplied")]

    text = str(raw)
    # Control characters (including NUL) can truncate a path at the syscall
    # boundary, so the string validated is not the path acted on.
    if any(ord(ch) < 32 for ch in text):
        problems.append(_reason("TARGET_CONTROL_CHARS", "control character in target"))
    if text.startswith("\\\\"):
        problems.append(_reason("TARGET_UNC_PATH", "UNC/network path refused"))
    if ".." in Path(text).parts:
        problems.append(_reason("TARGET_TRAVERSAL", "`..` component in target"))
    if not os.path.isabs(text):
        problems.append(_reason("TARGET_NOT_ABSOLUTE", f"relative target: {text}"))

    if problems:
        return None, problems
    return Path(text), problems


def classify(
    target: str,
    *,
    authorize_protected_root: bool = False,
    runtime_data_root: str | None = None,
) -> dict[str, Any]:
    """Classify a bootstrap target. Never raises; never mutates anything."""
    report: dict[str, Any] = {
        "target_raw": target,
        "classification": INVALID_TARGET,
        "fresh_host": False,
        "reasons": [],
        "evidence": {},
    }

    path, problems = _validate_path(target)
    if path is None:
        report["reasons"] = problems
        return report

    # Resolve symlinks BEFORE any decision: a symlinked empty-looking directory
    # pointing into /opt/leadgen must be judged as /opt/leadgen.
    try:
        resolved = path.resolve()
    except OSError as e:  # pragma: no cover - defensive
        report["reasons"] = [_reason("TARGET_UNRESOLVABLE", str(e)[:120])]
        return report

    report["target_resolved"] = str(resolved)
    report["symlink"] = path.is_symlink()

    reasons: list[dict[str, str]] = []

    # Protected production roots: refuse unless explicitly authorised.
    #
    # Checked against BOTH the raw input and the resolved path, with any drive
    # letter stripped. On Windows `Path("/opt/leadgen").resolve()` becomes
    # `C:\opt\leadgen`, so matching only the resolved value would make this
    # check silently platform-dependent — passing in CI while the operator who
    # typed `/opt/leadgen` is the one who needs stopping.
    resolved_str = _protected_form(str(resolved))
    raw_str = _protected_form(target)
    if not authorize_protected_root:
        for root in PROTECTED_ROOTS:
            if any(s == root or s.startswith(root + "/") for s in (resolved_str, raw_str)):
                reasons.append(
                    _reason(
                        "TARGET_IS_PROTECTED_ROOT",
                        f"{resolved_str} requires explicit authorisation",
                    )
                )
                break

    # Installation evidence.
    found: list[str] = []
    if resolved.exists():
        if not resolved.is_dir():
            reasons.append(_reason("TARGET_NOT_A_DIRECTORY", resolved_str))
        else:
            for name in INSTALL_EVIDENCE_PATHS:
                if (resolved / name).exists():
                    found.append(name)
            try:
                entries = list(resolved.iterdir())
            except OSError as e:  # pragma: no cover - defensive
                reasons.append(_reason("TARGET_UNREADABLE", str(e)[:120]))
                entries = []
            if entries and not found:
                # Non-empty but no recognised marker: unknown content, so the
                # honest answer is "not proven fresh", not "assume fine".
                reasons.append(
                    _reason(
                        "TARGET_NOT_EMPTY",
                        f"{len(entries)} existing entries, no recognised install marker",
                    )
                )
    report["evidence"]["install_markers"] = found
    if found:
        reasons.append(_reason("EXISTING_INSTALLATION", ", ".join(sorted(found))))

    # An external runtime-data root pointing at this target would be orphaned
    # by a clone/reset here.
    rd_root = (
        runtime_data_root
        if runtime_data_root is not None
        else os.environ.get("LEADGEN_RUNTIME_DATA_HOST_DIR", "")
    )
    if rd_root:
        try:
            rd = Path(rd_root).resolve()
            if rd == resolved or resolved in rd.parents:
                reasons.append(
                    _reason("RUNTIME_DATA_ROOT_INSIDE_TARGET", f"{rd} would be orphaned")
                )
        except OSError:  # pragma: no cover - defensive
            pass

    # Disk headroom on the nearest existing ancestor.
    probe = resolved
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        import shutil as _sh

        free = _sh.disk_usage(str(probe)).free
        report["evidence"]["free_bytes"] = free
        if free < _MIN_FREE_BYTES:
            reasons.append(_reason("INSUFFICIENT_DISK", f"{free} bytes free at {probe}"))
    except OSError:  # pragma: no cover - defensive
        report["evidence"]["free_bytes"] = -1

    report["reasons"] = reasons
    if reasons:
        report["classification"] = (
            EXISTING_HOST
            if any(
                r["code"] in {"EXISTING_INSTALLATION", "TARGET_IS_PROTECTED_ROOT"} for r in reasons
            )
            else INVALID_TARGET
        )
        report["fresh_host"] = False
    else:
        report["classification"] = FRESH_HOST
        report["fresh_host"] = True
    return report


def exit_code_for(report: dict[str, Any]) -> int:
    if report.get("fresh_host"):
        return EXIT_OK
    if report.get("classification") == EXISTING_HOST:
        return EXIT_REFUSED
    return EXIT_INVALID_TARGET


__all__ = [
    "FRESH_HOST",
    "EXISTING_HOST",
    "INVALID_TARGET",
    "EXISTING_INSTALL_STATUS",
    "EXIT_OK",
    "EXIT_REFUSED",
    "EXIT_INVALID_TARGET",
    "EXIT_PREFLIGHT_UNAVAILABLE",
    "PROTECTED_ROOTS",
    "INSTALL_EVIDENCE_PATHS",
    "classify",
    "exit_code_for",
]
