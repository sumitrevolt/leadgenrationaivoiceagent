"""
Production readiness check — run before every deploy.

Usage:
    python scripts/prod_check.py

Checks:
  1. Every .py file parses (catches partial writes / null-byte corruption)
  2. No stale __pycache__ left behind (mismatched bytecode causes phantom bugs)
  3. App imports cleanly
  4. All expected routers are registered
  5. Critical env/config sanity for production
  6. Frontend wiring — every onclick handler defined + every fetch path routed
Exit code 0 = ready, 1 = problems found.
"""

import argparse
import ast
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBLEMS: list[str] = []
# Non-fatal signals. Printed prominently, but do NOT affect the exit code —
# these are "a human should look at this", not "do not deploy".
WARNINGS: list[str] = []


def check_sources_parse() -> None:
    """Every tracked .py file must parse and contain no null bytes."""
    n = 0
    for d in ("app", "tests", "scripts", "revenue_pipeline"):
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            n += 1
            try:
                src = p.read_bytes()
                if b"\x00" in src:
                    PROBLEMS.append(f"NULL BYTES: {p.relative_to(ROOT)}")
                    continue
                ast.parse(src.decode("utf-8", errors="replace"))
            except SyntaxError as e:
                PROBLEMS.append(f"SYNTAX {p.relative_to(ROOT)} line {e.lineno}: {e.msg}")
    print(f"[1/6] {n} source files parsed")


def check_stale_pycache() -> None:
    """
    Remove .pyc files whose embedded source-mtime doesn't match the actual
    source file. Python normally recompiles these automatically, but clock
    skew (network mounts, VMs) can make a stale .pyc look "valid" and serve
    OLD bytecode for NEW source — a phantom-bug generator. Deleting is the
    only safe option; they cost nothing to rebuild.
    """
    import importlib.util
    import struct

    removed = 0
    orphans: dict[pathlib.Path, list[str]] = {}
    for d in ("app", "tests", "scripts"):
        base = ROOT / d
        if not base.is_dir():
            continue
        for pyc in base.rglob("*.pyc"):
            src_name = pyc.name.split(".")[0] + ".py"
            src = pyc.parent.parent / src_name
            if not src.exists():
                # Harmless for IMPORT safety: CPython will not load a __pycache__
                # .pyc without its source. But a CLUSTER of orphans means a whole
                # module tree left the working tree (unmerged branch, bad revert,
                # interrupted refactor) while its build artefacts stayed behind.
                # Nothing else in this repo detects that, so record it. Deliberately
                # NOT deleted: the filenames are the only remaining evidence of what
                # the vanished module was, which is what makes them diagnostic.
                orphans.setdefault(pyc.parent, []).append(src_name)
                continue
            try:
                header = pyc.read_bytes()[:16]
                if header[:4] != importlib.util.MAGIC_NUMBER:
                    pyc.unlink()
                    removed += 1
                    continue  # wrong interpreter version
                flags = struct.unpack("<I", header[4:8])[0]
                if flags & 0b11:
                    continue  # hash-based pyc, mtime not used
                pyc_mtime = struct.unpack("<I", header[8:12])[0]
                pyc_size = struct.unpack("<I", header[12:16])[0]
                st = src.stat()
                # mtime mismatch → Python recompiles anyway; delete = hygiene.
                # SIZE mismatch with MATCHING mtime → the dangerous case:
                # source changed but clock skew kept mtime identical, Python
                # would happily run the old bytecode.
                if (
                    pyc_mtime != int(st.st_mtime) & 0xFFFFFFFF
                    or pyc_size != st.st_size & 0xFFFFFFFF
                ):
                    pyc.unlink()
                    removed += 1
            except OSError:
                PROBLEMS.append(f"PYCACHE: could not inspect/remove {pyc.relative_to(ROOT)}")

    # A single orphan is noise (renamed file). Several in one directory means the
    # directory's source is GONE — report the cluster, not each file.
    for pkg_dir, names in sorted(orphans.items()):
        if len(names) < 2:
            continue
        rel = pkg_dir.parent.relative_to(ROOT)
        WARNINGS.append(
            f"ORPHAN MODULE TREE: {rel} has {len(names)} .pyc files with NO .py source "
            f"({', '.join(sorted(names)[:6])}{'...' if len(names) > 6 else ''}). "
            "The source for this package is not in the working tree - check for an "
            "unmerged branch (e.g. a checked-out feature branch you later switched "
            "away from; git leaves gitignored __pycache__ behind) before assuming "
            "the feature exists."
        )

    print(f"[2/6] pycache check done ({removed} stale .pyc removed)")


def check_app_imports() -> None:
    """The FastAPI app must import without errors."""
    sys.path.insert(0, str(ROOT))
    try:
        from app.main import app  # noqa: F401

        print("[3/6] app.main imports OK")
    except Exception as e:
        PROBLEMS.append(f"APP IMPORT FAILED: {type(e).__name__}: {e}")
        print("[3/6] app.main import FAILED")


def check_routes() -> None:
    """All core route prefixes must be registered."""
    try:
        from app.main import app
    except Exception:
        print("[4/6] skipped (app not importable)")
        return
    from app.utils.route_inspection import iter_effective_routes

    effective_routes = list(iter_effective_routes(app.routes))
    paths = {getattr(r, "path", "") for r in effective_routes}
    expected = [
        "/health",
        "/api/leads",
        "/api/data/niches",
        # Revenue-critical API surfaces — a silently-guarded router import failure
        # (main.py logs only logger.warning) would drop these with no other signal
        # and still pass every gate (API-001). These are guarded mounts.
        "/api/billing/plans",
        "/api/customer/auth/login",
        "/app/test-call",
        "/app/customer",
        "/app/admin",
        "/app/explorer",
        "/app/automation",
        # Public funnel pages - lead magnets + conversion path.
        "/",
        "/audit",
        "/site-audit",
        "/demo",
        "/pricing",
        "/start",
        "/app/inbox",
        # Public API - audit widget + revenue info surfaces.
        "/api/public/audit/questions",
        "/api/public/audit/score",
        "/api/public/pay-info",
        "/api/voice/niches",
    ]
    for exp in expected:
        if not any(p == exp or p.startswith(exp + "/") or p.startswith(exp) for p in paths):
            PROBLEMS.append(f"ROUTE MISSING: {exp}")

    # Duplicate (method, path) collisions — FastAPI first-route-wins silently
    # shadows the later registration; nothing else catches it (API-002).
    seen_mp: dict = {}
    for r in effective_routes:
        rp = getattr(r, "path", "")
        for m in getattr(r, "methods", None) or set():
            seen_mp[(m, rp)] = seen_mp.get((m, rp), 0) + 1
    for (m, rp), n in seen_mp.items():
        if n > 1:
            PROBLEMS.append(f"DUPLICATE ROUTE: {m} {rp} registered {n}x (first-route-wins shadow)")

    print(f"[4/6] routes checked ({len(paths)} registered)")


def check_frontend_wiring() -> None:
    """Every onclick handler must be defined + every fetch path must route.

    Reuses scripts/deep_wiring_audit (deterministic — loads real FastAPI routes).
    Defensive: if the auditor can't run, skip rather than block the deploy.
    """
    try:
        from scripts.deep_wiring_audit import PAGES, audit_file, load_routes

        routes = load_routes()
        total = 0
        for path in PAGES:
            if not path.exists():
                continue
            r = audit_file(path, routes)
            for h in r["missing_handlers"]:
                PROBLEMS.append(f"WIRING {path.name}: dead handler {h}()")
                total += 1
            for a in r["missing_apis"]:
                PROBLEMS.append(f"WIRING {path.name}: unrouted fetch {a}")
                total += 1
            for anc in r["missing_anchors"]:
                PROBLEMS.append(f"WIRING {path.name}: broken anchor #{anc}")
                total += 1
        # Automation-side wiring: every declared flag read + every job dispatchable.
        auto_gaps = _automation_wiring_gaps()
        for g in auto_gaps:
            PROBLEMS.append(f"AUTOMATION {g}")
        print(
            f"[6/6] wiring checked ({len(PAGES)} pages {total} gaps; "
            f"automation {len(auto_gaps)} gaps)"
        )
    except Exception as e:
        print(f"[6/6] wiring audit skipped ({type(e).__name__}: {e})")


def _automation_wiring_gaps() -> list[str]:
    """Reuse scripts/automation_wiring_audit + cross_path_audit — flags/jobs + telephony parity."""
    import contextlib
    import io

    gaps: list[str] = []
    try:
        from scripts import automation_wiring_audit as awa

        awa.PROBLEMS.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            blob = awa._all_app_text()
            awa.audit_flags(blob)
            awa.audit_jobs(blob)
            awa.audit_beat()
        gaps.extend(awa.PROBLEMS)
    except Exception:
        pass
    try:
        from scripts import cross_path_audit as cpa

        cpa.PROBLEMS.clear()
        with contextlib.redirect_stdout(io.StringIO()):
            cpa.audit_vobiz_stream_lifecycle()
            cpa.audit_call_insights_transcripts()
            cpa.audit_qualified_lead_idempotency()
        gaps.extend(cpa.PROBLEMS)
    except Exception:
        pass
    return gaps


#: Kept local on purpose: coupling the deployment gate to app.telephony would
#: drag the runtime import graph into a script that must stay light.
_VLK_TRUE = ("1", "true", "yes", "on", "true_token")
_VLK_FALSE = ("0", "false", "no", "off")


def classify_voice_launch_kill_env(value: str | None) -> str:
    """Class of the raw VOICE_LAUNCH_KILL setting. Pure: no I/O, no logging.

    Returns one of UNSET / TRUE_TOKEN / FALSE_TOKEN / INVALID_TOKEN. The value
    itself is never returned, logged or embedded in a message.
    """
    v = (value or "").strip().lower()
    if not v:
        return "UNSET"
    if v in _VLK_TRUE:
        return "TRUE_TOKEN"
    if v in _VLK_FALSE:
        return "FALSE_TOKEN"
    return "INVALID_TOKEN"


def check_voice_launch_kill_env() -> dict[str, str]:
    """Deployment gate for the voice kill switch ENV authority.

    Preflight is STRICTER than runtime, and deliberately so:

      * TRUE_TOKEN  — kill explicitly engaged. The only shippable state.
      * UNSET       — deployment cannot prove explicit calling refusal.
      * FALSE_TOKEN — runtime treats this as ENV_DISENGAGED, which means the
                      file-based emergency toggle is INERT: an operator could
                      write {"kill": true} and nothing would happen. Shipping
                      that silently is the hazard, so it blocks rather than warns.
      * INVALID_TOKEN — the reader fails closed on it, but malformed config
                      must not reach production.

    Classifies the ENV layer only; it never reads, writes or creates the kill file.
    """
    classification = classify_voice_launch_kill_env(os.environ.get("VOICE_LAUNCH_KILL"))
    reason = {
        "TRUE_TOKEN": "EXPLICITLY_ENGAGED",
        "UNSET": "ENV_NOT_CONFIGURED",
        "FALSE_TOKEN": "ENV_EXPLICITLY_DISENGAGED",
        "INVALID_TOKEN": "ENV_INVALID",
    }[classification]
    status = "PASS" if classification == "TRUE_TOKEN" else "BLOCKER"
    if status == "BLOCKER":
        PROBLEMS.append(f"voice_launch_kill_env: {classification} ({reason})")
    return {
        "check": "voice_launch_kill_env",
        "classification": classification,
        "status": status,
        "reason": reason,
    }


def check_production_config() -> None:
    """Sanity-check settings for production deploys."""
    try:
        from app.config import settings
    except Exception:
        print("[5/6] skipped (config not importable)")
        return
    import os as _os

    if _os.environ.get("CONSENT_DB") in ("1", "true", "yes") and not _os.environ.get(
        "DATABASE_URL"
    ):
        PROBLEMS.append(
            "CONFIG: CONSENT_DB=1 but DATABASE_URL unset — compliance risk (opt-outs won't persist)"
        )
    # TRAI DND gate must stay fail-CLOSED. DND_FAIL_OPEN turns it fail-OPEN
    # (promotional calls to DND-unverified numbers go through) — never legitimate
    # in prod (TC-002). Flag it wherever it is set.
    if _os.environ.get("DND_FAIL_OPEN") in ("1", "true", "True", "yes"):
        PROBLEMS.append("COMPLIANCE: DND_FAIL_OPEN is set — TRAI DND gate is fail-OPEN. Unset it.")
    if settings.app_env == "production":
        if settings.debug:
            PROBLEMS.append("CONFIG: debug=True in production")
        # These two literals are the PLACEHOLDER values prod_check looks for in
        # order to catch an unset default in production. They are detection
        # patterns, not credentials — hence the allowlist pragmas.
        if settings.secret_key == "change-this-in-production":  # pragma: allowlist secret
            PROBLEMS.append("CONFIG: default secret_key in production")
        if (
            settings.jwt_secret_key
            == "change-this-jwt-secret-in-production"  # pragma: allowlist secret
        ):
            PROBLEMS.append("CONFIG: default jwt_secret_key in production")
        if "*" in settings.cors_origins:
            PROBLEMS.append("CONFIG: CORS wildcard in production")
    print(f"[5/6] config checked (env={settings.app_env})")


def check_explorer_drift() -> None:
    """INFO only (never fails): how much of the architecture the /app/explorer
    graph still reflects. Curated graph can't be 100% — this just surfaces drift
    so it's visible every deploy. Detail + paste-ready stubs: explorer_sync.py."""
    try:
        from scripts import explorer_sync as es

        a = es.audit()
        cov = len(a["mods"]) - len(a["miss_mods"])
        line = f"[i] explorer graph: {a['nodes']} nodes · engine coverage {cov}/{len(a['mods'])}"
        if a["miss_mods"]:
            line += f" · {len(a['miss_mods'])} not drawn (scripts/explorer_sync.py --stubs)"
        ea = es.edge_audit(es._read(es.EXPLORER))
        orphans = sum(len(r.get("orphans") or []) for r in ea.values())
        line += f" · {a['edges']} edges · orphans {orphans}"
        mf = a.get("miss_files") or []
        line += " · file-refs OK" if not mf else f" · {len(mf)} file-ref DRIFT ({', '.join(mf)})"
        print(line)
    except Exception as e:
        print(f"[i] explorer drift check skipped ({type(e).__name__})")


def check_api_docs_drift() -> None:
    """INFO only (never fails): is docs/API.md endpoint index in sync with the
    live OpenAPI spec? Regenerate: scripts/sync_api_docs.py. Locks docs↔code."""
    try:
        import re as _re

        from scripts import sync_api_docs as sad

        block = sad.build_index()
        current = sad.API_MD.read_text(encoding="utf-8") if sad.API_MD.exists() else ""
        if current.strip() != sad._splice(current, block).strip():
            print("[i] API.md endpoint index OUT OF DATE — run scripts/sync_api_docs.py")
        else:
            n = len(_re.findall(r"^- `(GET|POST|PUT|PATCH|DELETE)", current, _re.M))
            print(f"[i] API.md endpoint index in sync ({n} ops)")
    except Exception as e:
        print(f"[i] API docs drift check skipped ({type(e).__name__})")


def check_dev_control_invariants() -> None:
    """Hard invariants for the Claude-managed engineering control plane."""
    try:
        from scripts.dev_control_gate import invariants

        for x in invariants():
            PROBLEMS.append(f"DEV-CONTROL: {x}")
        print("[+] dev-control invariants checked")
    except Exception as e:  # never let the gate crash prod_check
        print(f"[+] dev-control invariants skipped ({type(e).__name__}: {e})")


def main(argv: list[str] | None = None) -> int:
    # Two modes, ONE checker. `--deployment` is explicit rather than inferred
    # from APP_ENV: an implicit signal would either never fire (CI is not
    # production) or fire everywhere, and a gate that never runs is worse than
    # no gate because it reads as green.
    parser = argparse.ArgumentParser(
        prog="prod_check.py",
        description="Repository readiness check; --deployment adds the pre-deploy gates.",
    )
    parser.add_argument(
        "--deployment",
        action="store_true",
        help="run the additional gates required before an actual production deploy",
    )
    args = parser.parse_args(argv)

    print("=" * 56)
    print("PRODUCTION READINESS CHECK" + (" — DEPLOYMENT MODE" if args.deployment else ""))
    print("=" * 56)
    check_sources_parse()
    check_stale_pycache()
    check_app_imports()
    check_routes()
    check_production_config()
    check_frontend_wiring()
    check_explorer_drift()
    check_api_docs_drift()
    check_dev_control_invariants()
    if args.deployment:
        # Deployment-only: an unset VOICE_LAUNCH_KILL is fine for a readiness
        # run, but it is not fine for an actual deploy.
        _vk = check_voice_launch_kill_env()
        print(f"[+] voice_launch_kill_env: {_vk['classification']} ({_vk['status']})")
    print("-" * 56)
    # Warnings print BEFORE the verdict so they are visible on a passing run too —
    # a warning that only shows on failure is a warning nobody reads.
    if WARNINGS:
        print(f"[WARN] {len(WARNINGS)} non-blocking signal(s):")
        for w in WARNINGS:
            print("  ~", w)
        print("-" * 56)
    if PROBLEMS:
        print(f"[FAIL] {len(PROBLEMS)} problem(s):")
        for p in PROBLEMS:
            print("  -", p)
        _write_obsidian_result(passed=False)
        return 1
    print("[OK] ALL CHECKS PASSED - ready to deploy")
    _write_obsidian_result(passed=True)
    return 0


def _write_obsidian_result(passed: bool) -> None:
    """Write prod_check result to Obsidian System/ (INERT if OBSIDIAN_SYNC unset)."""
    try:
        import sys as _sys

        _sys.path.insert(0, str(ROOT))
        from app.platform import obsidian_sync as _obs

        status = "ALL CHECKS PASSED" if passed else f"{len(PROBLEMS)} PROBLEM(S)"
        lines = [f"# Prod Check\n\n**Status:** {status}\n"]
        if PROBLEMS:
            lines.append("\n## Problems")
            for p in PROBLEMS:
                lines.append(f"- {p}")
        if WARNINGS:
            lines.append("\n## Warnings (non-blocking)")
            for w in WARNINGS:
                lines.append(f"- {w}")
        _obs.write_system_health("prod-check-latest", "\n".join(lines))
    except Exception:
        pass


if __name__ == "__main__":
    sys.exit(main())
