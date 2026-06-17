#!/usr/bin/env python3
"""Deep wiring audit — onclick handlers + api()/fetch paths vs FastAPI routes."""
from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

PAGES = [
    ROOT / "frontend/admin_dashboard.html",
    ROOT / "frontend/customer_dashboard.html",
    ROOT / "frontend/automation.html",
    ROOT / "frontend/battlecard.html",
    ROOT / "frontend/impersonate.html",
]

SKIP_HANDLERS = {
    "document", "navigator", "window", "alert", "confirm", "return", "this",
    "classList", "copyText", "esc", "escH", "$", "show", "api", "toast",
    "adminToast", "jpre", "pills", "draftBlocks", "busy", "warnBox",
    "copyVal", "copyTxt", "scrollToId", "toggleDark", "toggleNotifPanel",
    "markAllRead", "saveTok", "tok", "hdr", "JSON", "location", "render",
    "applyFilter", "start", "load", "setMsg", "renderAll", "filterByCampaign",
}


def load_routes() -> set[str]:
    sys.path.insert(0, str(ROOT))
    from app.main import app

    return {
        getattr(r, "path", "")
        for r in app.routes
        if getattr(r, "path", "") and str(getattr(r, "path", "")).startswith("/")
    }


def _route_to_regex(route: str) -> str:
    parts: list[str] = []
    for part in route.split("/"):
        if part.startswith("{") and part.endswith("}"):
            parts.append("[^/]+")
        elif part:
            parts.append(re.escape(part))
    return "^" + "/".join(parts) + "$"


def route_exists(path: str, routes: set[str]) -> bool:
    base = path.split("?")[0].rstrip("/")
    if not base:
        return True
    if base in routes:
        return True
    for r in routes:
        if re.match(_route_to_regex(r), base):
            return True
    for r in routes:
        if "{" not in r:
            continue
        static = r.split("{", 1)[0].rstrip("/")
        if static and (base == static or base.startswith(static + "/")):
            return True
    for r in routes:
        if r.startswith(base + "/") or r == base:
            return True
    return False


def audit_file(path: pathlib.Path, routes: set[str]) -> dict:
    html = path.read_text(encoding="utf-8", errors="ignore")
    onclicks: set[str] = set()
    for m in re.finditer(r'onclick="([^"]+)"', html):
        expr = m.group(1).split(";")[0].strip()
        if "(" in expr:
            onclicks.add(re.sub(r"\(.*", "", expr).strip())
    funcs = set(re.findall(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", html))
    funcs |= set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", html))

    apis: set[str] = set()
    apis |= set(re.findall(r"""api\(['"]([^'"]+)['"]""", html))
    apis |= set(re.findall(r"""fetch\(['"]([^'"]+)['"]""", html))
    apis |= set(re.findall(r'["\'`](/api/[^"\']+)["\'`]', html))

    missing_handlers = sorted(
        h
        for h in onclicks
        if h not in funcs
        and h.split(".")[0] not in SKIP_HANDLERS
        and not h.startswith("this.")
        and not h.endswith(".splice")
    )
    missing_apis = sorted(
        p
        for p in apis
        if (p.startswith("/api") or p.startswith("/health"))
        and not route_exists(p, routes)
    )
    # sidebar anchors
    anchors = set(re.findall(r'href="#([^"]+)"', html))
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    missing_anchors = sorted(a for a in anchors if a not in ids)

    return {
        "file": path.name,
        "handlers": len(onclicks),
        "funcs": len(funcs),
        "apis": len(apis),
        "missing_handlers": missing_handlers,
        "missing_apis": missing_apis,
        "missing_anchors": missing_anchors,
    }


def main() -> int:
    routes = load_routes()
    print(f"=== DEEP WIRING AUDIT ({len(routes)} routes) ===\n")
    total_h = total_a = total_anchor = 0
    for path in PAGES:
        if not path.exists():
            print(f"SKIP {path.name} (missing)\n")
            continue
        r = audit_file(path, routes)
        print(f"## {r['file']}")
        print(f"  handlers={r['handlers']} funcs={r['funcs']} api_refs={r['apis']}")
        if r["missing_handlers"]:
            print(f"  MISSING HANDLERS ({len(r['missing_handlers'])}):")
            for h in r["missing_handlers"]:
                print(f"    - {h}")
            total_h += len(r["missing_handlers"])
        else:
            print("  HANDLERS: OK")
        if r["missing_apis"]:
            print(f"  MISSING APIs ({len(r['missing_apis'])}):")
            for p in r["missing_apis"][:25]:
                print(f"    - {p}")
            if len(r["missing_apis"]) > 25:
                print(f"    ... +{len(r['missing_apis']) - 25} more")
            total_a += len(r["missing_apis"])
        else:
            print("  APIs: OK")
        if r["missing_anchors"]:
            print(f"  BROKEN ANCHORS ({len(r['missing_anchors'])}):")
            for a in r["missing_anchors"][:15]:
                print(f"    - #{a}")
            total_anchor += len(r["missing_anchors"])
        else:
            print("  ANCHORS: OK")
        print()

    print("=== TOTAL GAPS ===")
    print(f"handlers={total_h} apis={total_a} anchors={total_anchor}")
    return 1 if (total_h or total_a or total_anchor) else 0


if __name__ == "__main__":
    raise SystemExit(main())
