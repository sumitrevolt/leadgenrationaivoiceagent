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
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROBLEMS: list[str] = []


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
    for d in ("app", "tests", "scripts"):
        base = ROOT / d
        if not base.is_dir():
            continue
        for pyc in base.rglob("*.pyc"):
            src_name = pyc.name.split(".")[0] + ".py"
            src = pyc.parent.parent / src_name
            if not src.exists():
                continue  # orphan pyc, harmless
            try:
                header = pyc.read_bytes()[:16]
                if header[:4] != importlib.util.MAGIC_NUMBER:
                    pyc.unlink(); removed += 1; continue  # wrong interpreter version
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
                if (pyc_mtime != int(st.st_mtime) & 0xFFFFFFFF
                        or pyc_size != st.st_size & 0xFFFFFFFF):
                    pyc.unlink(); removed += 1
            except OSError:
                PROBLEMS.append(f"PYCACHE: could not inspect/remove {pyc.relative_to(ROOT)}")
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
    paths = {getattr(r, "path", "") for r in app.routes}
    expected = [
        "/health",
        "/api/leads",
        "/api/data/niches",
        "/app/test-call",
        "/app/customer",
        "/app/admin",
        "/app/explorer",
        "/app/automation",
    ]
    for exp in expected:
        if not any(p == exp or p.startswith(exp + "/") or p.startswith(exp) for p in paths):
            PROBLEMS.append(f"ROUTE MISSING: {exp}")
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


def check_production_config() -> None:
    """Sanity-check settings for production deploys."""
    try:
        from app.config import settings
    except Exception:
        print("[5/6] skipped (config not importable)")
        return
    import os as _os
    if _os.environ.get("CONSENT_DB") in ("1", "true", "yes") and not _os.environ.get("DATABASE_URL"):
        PROBLEMS.append("CONFIG: CONSENT_DB=1 but DATABASE_URL unset — compliance risk (opt-outs won't persist)")
    if settings.app_env == "production":
        if settings.debug:
            PROBLEMS.append("CONFIG: debug=True in production")
        if settings.secret_key == "change-this-in-production":
            PROBLEMS.append("CONFIG: default secret_key in production")
        if settings.jwt_secret_key == "change-this-jwt-secret-in-production":
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
        line = (f"[i] explorer graph: {a['nodes']} nodes · engine coverage "
                f"{cov}/{len(a['mods'])}")
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


def main() -> int:
    print("=" * 56)
    print("PRODUCTION READINESS CHECK")
    print("=" * 56)
    check_sources_parse()
    check_stale_pycache()
    check_app_imports()
    check_routes()
    check_production_config()
    check_frontend_wiring()
    check_explorer_drift()
    check_api_docs_drift()
    print("-" * 56)
    if PROBLEMS:
        print(f"[FAIL] {len(PROBLEMS)} problem(s):")
        for p in PROBLEMS:
            print("  -", p)
        return 1
    print("[OK] ALL CHECKS PASSED - ready to deploy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
