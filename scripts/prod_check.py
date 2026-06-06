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
    print(f"[1/5] {n} source files parsed")


def check_stale_pycache() -> None:
    """Detect .pyc files older than their source (stale bytecode hazard)."""
    stale = 0
    for d in ("app", "tests", "scripts"):
        base = ROOT / d
        if not base.is_dir():
            continue
        for pyc in base.rglob("*.pyc"):
            src_name = pyc.name.split(".")[0] + ".py"
            src = pyc.parent.parent / src_name
            if src.exists() and src.stat().st_mtime > pyc.stat().st_mtime:
                stale += 1
    if stale:
        PROBLEMS.append(
            f"{stale} stale .pyc files — run: "
            "python -c \"import pathlib,shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('__pycache__') if '.venv' not in str(p)]\""
        )
    print(f"[2/5] stale pycache check done ({stale} stale)")


def check_app_imports() -> None:
    """The FastAPI app must import without errors."""
    sys.path.insert(0, str(ROOT))
    try:
        from app.main import app  # noqa: F401
        print("[3/5] app.main imports OK")
    except Exception as e:
        PROBLEMS.append(f"APP IMPORT FAILED: {type(e).__name__}: {e}")
        print("[3/5] app.main import FAILED")


def check_routes() -> None:
    """All core route prefixes must be registered."""
    try:
        from app.main import app
    except Exception:
        print("[4/5] skipped (app not importable)")
        return
    paths = {getattr(r, "path", "") for r in app.routes}
    expected = [
        "/health",
        "/api/leads",
        "/api/data/niches",
        "/app/test-call",
        "/app/customer",
        "/app/admin",
    ]
    for exp in expected:
        if not any(p == exp or p.startswith(exp + "/") or p.startswith(exp) for p in paths):
            PROBLEMS.append(f"ROUTE MISSING: {exp}")
    print(f"[4/5] routes checked ({len(paths)} registered)")


def check_production_config() -> None:
    """Sanity-check settings for production deploys."""
    try:
        from app.config import settings
    except Exception:
        print("[5/5] skipped (config not importable)")
        return
    if settings.app_env == "production":
        if settings.debug:
            PROBLEMS.append("CONFIG: debug=True in production")
        if settings.secret_key == "change-this-in-production":
            PROBLEMS.append("CONFIG: default secret_key in production")
        if settings.jwt_secret_key == "change-this-jwt-secret-in-production":
            PROBLEMS.append("CONFIG: default jwt_secret_key in production")
        if "*" in settings.cors_origins:
            PROBLEMS.append("CONFIG: CORS wildcard in production")
    print(f"[5/5] config checked (env={settings.app_env})")


def main() -> int:
    print("=" * 56)
    print("PRODUCTION READINESS CHECK")
    print("=" * 56)
    check_sources_parse()
    check_stale_pycache()
    check_app_imports()
    check_routes()
    check_production_config()
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
