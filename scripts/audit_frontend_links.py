"""
Audit: frontend /api/... references vs registered FastAPI routes.
Finds "dead buttons" — UI fetch() calls to endpoints that don't exist (404).

Run: python scripts/audit_frontend_links.py
Exit 0 always (report-only). Heuristic — concatenated dynamic paths may be
flagged as candidates; verify each before "fixing".
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
sys.path.insert(0, str(ROOT))

# ---- 1. registered routes from the live app ----
import app.main as m  # noqa: E402

route_res: list[tuple[re.Pattern, str]] = []
raw_routes: list[str] = []
for r in m.app.routes:
    path = getattr(r, "path", None)
    if not path:
        continue
    raw_routes.append(path)
    # {param} -> match one non-slash segment ; {param:path} -> match anything
    rx = re.escape(path)
    rx = rx.replace(r"\{", "{").replace(r"\}", "}")
    rx = re.sub(r"\{[^/}]+:path\}", ".+", rx)
    rx = re.sub(r"\{[^/}]+\}", "[^/]+", rx)
    route_res.append((re.compile("^" + rx + "/?$"), path))


def matches(p: str) -> bool:
    # exact-ish match against any registered route regex
    for rx, _ in route_res:
        if rx.match(p):
            return True
    # frontend concatenation often leaves a trailing slash before a dynamic id,
    # possibly followed by MORE path: '/api/marketing/crm/'+id+'/customers'.
    # The extracted literal is only the static prefix '/api/marketing/crm/'.
    # It's valid as long as SOME registered route begins with that prefix — the
    # dynamic tail can't be statically validated anyway.
    if p.endswith("/"):
        if any(orig.startswith(p) for _, orig in route_res):
            return True
    return False


# ---- 2. extract /api (and root health/sse) refs from frontend ----
PATH_RE = re.compile(r"""['"`](/(?:api|health|r|ws|mcp|metrics|b)/[^'"`\s]*)['"`]""")
DYN = re.compile(r"\$\{[^}]+\}")

refs: dict[str, set[str]] = {}  # path -> set(files)
for html in sorted(FRONTEND.glob("*.html")):
    txt = html.read_text(encoding="utf-8", errors="ignore")
    for mo in PATH_RE.finditer(txt):
        raw = mo.group(1)
        raw = raw.split("?")[0].split("#")[0]  # drop query/hash
        raw = DYN.sub("WILD", raw)  # ${x} -> WILD token
        raw = raw.replace("WILD", "PARAM")
        # turn our PARAM token into a wildcard-matchable segment
        test = raw.replace("PARAM", "x")
        refs.setdefault(raw, set()).add(html.name)

# ---- 3. diff ----
missing: list[tuple[str, str]] = []
for raw, files in sorted(refs.items()):
    test = raw.replace("PARAM", "x")
    if not matches(test):
        missing.append((raw, ", ".join(sorted(files))))

print(f"Registered routes: {len(raw_routes)}")
print(f"Distinct frontend /api refs: {len(refs)}")
print(f"Unmatched (candidate dead links): {len(missing)}\n")
for raw, files in missing:
    print(f"  ❌ {raw}\n       in: {files}")
if not missing:
    print("  ✅ All frontend /api references match a registered route.")

# ---- 4. REVERSE diff: admin-feature endpoints with NO frontend caller ----
# (project rule: "API-only feature = adhoora". Exclude routes that legitimately
#  have no admin-HTML caller: webhooks/public/customer/runtime/infra.)
NON_UI_PREFIXES = (
    "/api/webhooks",
    "/api/public",
    "/api/customer",
    "/api/billing/webhooks",
    "/api/voiceai",
    "/api/web-call",
    "/api/events",
    "/api/telephony",
    "/api/wa/webhook",
    "/api/ml",
    "/health",
    "/metrics",
    "/mcp",
    "/ws",
    "/r/",
    "/b/",
    "/api/niche/",
    "/api/data",
)
# frontend refs as matcher regexes (PARAM->seg, trailing-slash->prefix .*)
ref_res: list[re.Pattern] = []
for raw in refs:
    rx = re.escape(raw).replace("PARAM", "[^/]+")
    if raw.endswith("/"):
        rx = rx + ".*"
    ref_res.append(re.compile("^" + rx + "/?$"))


def covered(route_path: str) -> bool:
    concrete = re.sub(r"\{[^/}]+\}", "X", route_path)  # {id} -> X
    return any(rr.match(concrete) for rr in ref_res)


seen = set()
uncovered: list[str] = []
for r in m.app.routes:
    path = getattr(r, "path", "")
    methods = getattr(r, "methods", set()) or set()
    verbs = methods - {"HEAD", "OPTIONS"}
    if not path.startswith("/api/") or not verbs:
        continue
    if any(path.startswith(p) for p in NON_UI_PREFIXES):
        continue
    key = path
    if key in seen:
        continue
    seen.add(key)
    if not covered(path):
        uncovered.append(f"{','.join(sorted(verbs)):12} {path}")

print(f"\n--- REVERSE: admin endpoints with NO frontend caller: {len(uncovered)} ---")
for u in sorted(uncovered):
    print(f"  • {u}")
