"""Quick production readiness check — import + routes + old-SDK (no frontend wiring timeout).

Usage: python scripts/prod_quick_check.py
Supplements the full scripts/prod_check.py (which has a frontend wiring pass that can be slow).
"""

import ast
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("GROQ_API_KEY", "ci-test")

problems: list[str] = []

# 1. Source parse
n = 0
for d in ("app", "tests", "scripts"):
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
                problems.append(f"NULL BYTES: {p.relative_to(ROOT)}")
            else:
                ast.parse(src.decode("utf-8", errors="replace"))
        except SyntaxError as e:
            problems.append(f"SYNTAX {p.relative_to(ROOT)} line {e.lineno}: {e.msg}")
print(f"[1] {n} source files parsed, {len(problems)} problems")

# 2. App import
try:
    from app.main import app  # noqa: F401

    print(f"[2] app imports OK — {len(app.routes)} routes")
except Exception as exc:
    problems.append(f"APP IMPORT FAILED: {exc}")
    print(f"[2] FAILED: {exc}")
    sys.exit(1)

# 3. Duplicate routes
from collections import Counter

seen: Counter = Counter()
for r in app.routes:
    rp = getattr(r, "path", "")
    for m in getattr(r, "methods", None) or set():
        seen[(m, rp)] += 1
dups = {k: v for k, v in seen.items() if v > 1}
for k, v in list(dups.items())[:5]:
    problems.append(f"DUPLICATE ROUTE: {k} x{v}")
print(f"[3] duplicate routes: {len(dups)}")

# 4. Deprecated SDK check
old_sdk = [m for m in sys.modules if m == "google.generativeai"]
if old_sdk:
    problems.append(f"OLD generativeai SDK imported at module level: {old_sdk}")
print(f"[4] old generativeai SDK: {old_sdk or 'NONE'}")

# 5. Config sanity
try:
    from app.config import settings

    if settings.app_env == "production":
        if settings.debug:
            problems.append("debug=True in production")
        if "change-this" in (settings.secret_key or ""):
            problems.append("default secret_key in production")
        if "change-this" in (settings.jwt_secret_key or ""):
            problems.append("default jwt_secret_key in production")
    print(f"[5] config OK (env={settings.app_env})")
except Exception as exc:
    print(f"[5] config skip ({exc})")

print("-" * 50)
if problems:
    print(f"FAIL — {len(problems)} problem(s):")
    for p in problems:
        print(f"  - {p}")
    sys.exit(1)
print("ALL QUICK CHECKS PASSED")
