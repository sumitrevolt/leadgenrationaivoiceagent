#!/usr/bin/env python3
"""Shared runtime-data deployment preflight — the single deny authority.

WHY: production mutable state currently lives at `/opt/leadgen/data`, INSIDE the
Git checkout. A repo-wide scan found **15** production-capable destructive paths
(6 × `git reset --hard`, 1 × `git clean -fd`, 8 × `git pull`). Any of them can
revert or delete the live invoice ledger, consent ledger, suppression ledgers,
customer registry and 182 MB of DPDP call recordings.

This script is the one place that says NO, and every destructive path must call
it BEFORE its first mutating command.

Modes
-----
``diagnose``      read-only report; safe anywhere; always exit 0
``check-deploy``  strict; non-zero unless a destructive deploy is provably safe
``check-cutover`` validates prerequisites for a FUTURE cutover; performs nothing

It never prints secret values — only paths, booleans and counts.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.platform import runtime_data as rd  # noqa: E402
from app.platform import runtime_data_manifest as manifest  # noqa: E402

#: Explicit gate. Merging the Foundation must NOT switch production's mount.
CUTOVER_GATE_ENV = "RUNTIME_DATA_CUTOVER_ENABLED"
MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB

MODE_LEGACY = "LEGACY_CHECKOUT_BACKED"
MODE_EXTERNAL_UNVERIFIED = "EXTERNAL_ROOT_UNVERIFIED"
MODE_EXTERNAL_VERIFIED = "EXTERNAL_VERIFIED"


def _bool_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _free_bytes(path: Path) -> int:
    try:
        return shutil.disk_usage(str(path)).free
    except Exception:
        return -1


def _owner_mode(path: Path) -> dict[str, Any]:
    try:
        st = path.stat()
        return {"mode": oct(st.st_mode & 0o777), "uid": st.st_uid, "gid": st.st_gid}
    except Exception:
        return {"mode": None, "uid": None, "gid": None}


def gather() -> dict[str, Any]:
    """Collect facts. Never raises — an error IS a finding."""
    report: dict[str, Any] = {
        "repo_root": str(REPO_ROOT),
        "environment": os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT") or "",
        "is_production": rd.is_production(),
        "cutover_gate_enabled": _bool_env(CUTOVER_GATE_ENV),
        "manifest_version": manifest.MANIFEST_VERSION,
        "blockers": [],
        "problems": [],
        "warnings": [],
    }

    # --- manifest self-consistency -----------------------------------------
    manifest_problems = manifest.validate()
    if manifest_problems:
        report["problems"].append({"code": "MANIFEST_INCONSISTENT", "detail": manifest_problems})

    blockers = manifest.blocking_stores()
    report["blockers"] = [
        {
            "store_id": s["store_id"],
            "tier": s.get("migration_tier"),
            "state": s.get("migration_state"),
        }
        for s in blockers
    ]
    report["blocker_count"] = len(blockers)

    # --- host path (deployment concern; NOT the application path) ----------
    host_raw = (os.environ.get(rd.HOST_ENV_KEY) or "").strip()
    report["host_path_configured"] = bool(host_raw)
    report["host_path"] = host_raw or None
    if host_raw:
        host = Path(host_raw)
        report["host_path_absolute"] = host.is_absolute()
        report["host_path_exists"] = host.exists()
        report["host_path_is_dir"] = host.is_dir()
        inside = False
        try:
            host.resolve().relative_to(REPO_ROOT.resolve())
            inside = True
        except Exception:
            inside = False
        report["host_path_inside_checkout"] = inside
        if inside:
            report["problems"].append(
                {
                    "code": "HOST_PATH_INSIDE_CHECKOUT",
                    "detail": "runtime root resolves inside the Git checkout; "
                    "`git reset --hard` would destroy it",
                }
            )
        if host.exists():
            report["host_path_writable"] = os.access(host, os.W_OK)
            report.update({"host_path_" + k: v for k, v in _owner_mode(host).items()})
            free = _free_bytes(host)
            report["host_free_bytes"] = free
            if 0 <= free < MIN_FREE_BYTES:
                report["problems"].append(
                    {"code": "INSUFFICIENT_DISK", "detail": f"{free} bytes free"}
                )

    # --- application/container path ----------------------------------------
    app_raw = (os.environ.get(rd.ENV_KEY) or "").strip()
    report["app_path_configured"] = bool(app_raw)
    report["app_path"] = app_raw or None
    try:
        # Gate containers mount the external root :ro on purpose; writability is
        # a live-writer concern, not a marker-visibility concern.
        report["resolved_runtime_root"] = str(rd.runtime_root(require_writable=False))
        report["resolver_ok"] = True
    except rd.RuntimeDataError as e:
        report["resolver_ok"] = False
        report["problems"].append({"code": "RESOLVER_REFUSED", "detail": str(e)})

    # --- legacy checkout state ---------------------------------------------
    legacy_dir = REPO_ROOT / "data"
    report["legacy_data_dir_present"] = legacy_dir.is_dir()

    # --- cutover marker -----------------------------------------------------
    marker_state = "ABSENT"
    if report.get("resolver_ok"):
        try:
            marker_path = Path(report["resolved_runtime_root"]) / "migration" / "cutover.json"
            report["marker_path"] = str(marker_path)
            if marker_path.is_file():
                from app.platform import runtime_data_marker as mk

                problems = mk.validate_marker_file(marker_path)
                marker_state = "VALID" if not problems else "INVALID"
                if problems:
                    report["problems"].append({"code": "MARKER_INVALID", "detail": problems})
        except Exception as e:  # marker module optional at this stage
            marker_state = "UNREADABLE"
            report["warnings"].append({"code": "MARKER_UNREADABLE", "detail": str(e)[:200]})
    report["marker_state"] = marker_state

    # --- overall mode -------------------------------------------------------
    if not report["host_path_configured"] or not report["app_path_configured"]:
        report["mode"] = MODE_LEGACY
    elif marker_state != "VALID" or blockers:
        report["mode"] = MODE_EXTERNAL_UNVERIFIED
    else:
        report["mode"] = MODE_EXTERNAL_VERIFIED

    return report


def deploy_denied(report: dict[str, Any]) -> list[str]:
    """Reasons a destructive deployment must NOT proceed. Empty == allowed."""
    reasons: list[str] = []
    if report.get("problems"):
        reasons += [str(p.get("code")) for p in report["problems"]]
    if report.get("blocker_count"):
        reasons.append(f"LEGACY_AUTHORITATIVE_STORES_PRESENT({report['blocker_count']})")
    if report.get("mode") != MODE_EXTERNAL_VERIFIED:
        reasons.append(f"MODE_{report.get('mode')}")
    if not report.get("cutover_gate_enabled"):
        reasons.append("CUTOVER_GATE_DISABLED")
    if report.get("marker_state") != "VALID":
        reasons.append(f"MARKER_{report.get('marker_state')}")
    # Deduplicate, preserve order.
    seen: set[str] = set()
    return [r for r in reasons if not (r in seen or seen.add(r))]


def _print_human(report: dict[str, Any], reasons: list[str]) -> None:
    print("=== runtime-data preflight ===")
    print(f"  repo              : {report['repo_root']}")
    print(f"  environment       : {report['environment'] or '<unset>'}")
    print(f"  mode              : {report.get('mode')}")
    print(f"  manifest version  : {report['manifest_version']}")
    print(f"  host path set     : {report['host_path_configured']}")
    print(f"  app path set      : {report['app_path_configured']}")
    print(f"  cutover gate      : {report['cutover_gate_enabled']}")
    print(f"  marker            : {report['marker_state']}")
    print(f"  blocking stores   : {report.get('blocker_count')}")
    for b in report["blockers"]:
        print(f"      - {b['store_id']:<34} {b['tier']:<6} {b['state']}")
    for p in report.get("problems", []):
        print(f"  PROBLEM           : {p['code']}")
    if reasons:
        print("\n  DESTRUCTIVE DEPLOY: DENIED")
        for r in reasons:
            print(f"      x {r}")
    else:
        print("\n  DESTRUCTIVE DEPLOY: allowed")


def _run_bootstrap_check(args: Any) -> int:
    """Classify a bootstrap target. Fails closed on every ambiguity.

    There is deliberately no force flag, no ignore-existing-install flag and no
    emergency bypass. `--authorize-protected-root` only removes the
    'this path is /opt/leadgen' objection; every other check still has to pass,
    so it cannot be used to bootstrap over a live installation.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    try:
        from app.platform import bootstrap_target as _bt
    except Exception as e:  # pragma: no cover - defensive
        print(f"FATAL: bootstrap classifier unavailable: {e}")
        return 94  # EXIT_PREFLIGHT_UNAVAILABLE

    target = args.target or os.environ.get("LOCAL_DIR") or ""
    report = _bt.classify(target, authorize_protected_root=args.authorize_protected_root)
    code = _bt.exit_code_for(report)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        print("=== runtime-data preflight (check-bootstrap) ===")
        print(f"  target          : {report.get('target_raw')!r}")
        print(f"  resolved        : {report.get('target_resolved')}")
        print(f"  classification  : {report.get('classification')}")
        if report["reasons"]:
            print("\n  BOOTSTRAP: REFUSED")
            for r in report["reasons"]:
                print(f"      x {r['code']}: {r['detail']}")
            if report.get("classification") == _bt.EXISTING_HOST:
                print(f"\n  {_bt.EXISTING_INSTALL_STATUS}")
                print("  Use the protected normal-release parent (scripts/deploy_vps.sh)")
                print("  or an explicitly protected recovery path. Bootstrap will not")
                print("  become a second deployment implementation.")
        else:
            print("\n  BOOTSTRAP: allowed (target proven fresh)")
    return code


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Runtime-data deployment preflight")
    ap.add_argument(
        "mode",
        choices=["diagnose", "check-deploy", "check-cutover", "check-bootstrap"],
        nargs="?",
        default="diagnose",
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--target", help="bootstrap target directory (check-bootstrap only)")
    ap.add_argument(
        "--authorize-protected-root",
        action="store_true",
        help=(
            "explicitly authorise a protected production root as a bootstrap target. "
            "This is NOT a force flag: the target must still be proven empty and pass "
            "every other check."
        ),
    )
    args = ap.parse_args(argv)

    # check-bootstrap answers a different question from the release modes: not
    # "may we deploy over this installation" but "is this a fresh, safe target".
    # It therefore does NOT reuse deploy_denied(), whose blockers are all about
    # an existing installation and would be nonsensical for a fresh host.
    if args.mode == "check-bootstrap":
        return _run_bootstrap_check(args)

    report = gather()
    reasons = deploy_denied(report)
    report["deploy_denied_reasons"] = reasons
    report["deploy_allowed"] = not reasons

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
    else:
        _print_human(report, reasons)

    if args.mode == "diagnose":
        return 0
    if args.mode == "check-cutover":
        # Prerequisites for a FUTURE cutover: resolver + host path sane.
        blocking = [
            p["code"]
            for p in report.get("problems", [])
            if p["code"] in {"HOST_PATH_INSIDE_CHECKOUT", "RESOLVER_REFUSED", "INSUFFICIENT_DISK"}
        ]
        return 1 if blocking else 0
    return 1 if reasons else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
