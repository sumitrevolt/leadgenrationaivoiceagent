#!/usr/bin/env python3
"""Deep wiring audit — onclick handlers + api()/fetch paths vs FastAPI routes."""

from __future__ import annotations

import pathlib
import re
import sys
from functools import cache, lru_cache

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Auto-discover ALL frontend pages (exhaustive — nothing left out).
PAGES = sorted((ROOT / "frontend").glob("*.html"))

SKIP_HANDLERS = {
    "document",
    "navigator",
    "window",
    "alert",
    "confirm",
    "return",
    "this",
    "classList",
    "copyText",
    "esc",
    "escH",
    "$",
    "show",
    "api",
    "toast",
    "adminToast",
    "jpre",
    "pills",
    "draftBlocks",
    "busy",
    "warnBox",
    "copyVal",
    "copyTxt",
    "scrollToId",
    "toggleDark",
    "toggleNotifPanel",
    "markAllRead",
    "saveTok",
    "tok",
    "hdr",
    "JSON",
    "location",
    "render",
    "applyFilter",
    "start",
    "load",
    "setMsg",
    "renderAll",
    "filterByCampaign",
    # JS keywords + DOM-event built-ins (inline onclicks like
    # onclick="event.stopPropagation();realFn()" — first stmt is a built-in).
    "event",
    "if",
    "else",
    "for",
    "while",
    "switch",
    "void",
    "delete",
    "console",
    "history",
    "localStorage",
    "sessionStorage",
    "Math",
    "Object",
    "Array",
    "String",
    "Number",
    "setTimeout",
    "setInterval",
    "e",
}


def load_routes() -> set[str]:
    sys.path.insert(0, str(ROOT))
    from app.main import app
    from app.utils.route_inspection import iter_effective_routes

    return {
        getattr(r, "path", "")
        for r in iter_effective_routes(app.routes)
        if getattr(r, "path", "") and str(getattr(r, "path", "")).startswith("/")
    }


@cache
def _route_to_regex(route: str) -> re.Pattern[str]:
    """Compile each FastAPI-style dynamic route once per audit run."""
    parts: list[str] = []
    for part in route.split("/"):
        if part.startswith("{") and part.endswith("}"):
            parts.append("[^/]+")
        elif part:
            parts.append(re.escape(part))
    return re.compile("^" + "/".join(parts) + "$")


def route_exists(path: str, routes: set[str]) -> bool:
    base = path.split("?")[0].rstrip("/")
    if not base:
        return True
    if base in routes:
        return True
    for r in routes:
        if _route_to_regex(r).fullmatch(base):
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
    # window.NAME = (async) function / arrow — IIFE-scoped globals (real runtime
    # handlers; regex blind-spot pehle inhe "dead handler" bata raha tha).
    funcs |= set(re.findall(r"window\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?function", html))
    funcs |= set(re.findall(r"window\.([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", html))
    # Exported controller objects can expose concise object-literal methods used
    # directly by inline handlers (for example BP.enterMode()).  Treat only an
    # explicitly window-exported object + a matching method definition as wired;
    # a missing BP.someMethod must still fail instead of skipping the whole base.
    exported_objects = set(
        re.findall(
            r"window\.([A-Za-z_$][\w$]*)\s*=\s*\1\b",
            html,
        )
    )
    for handler in onclicks:
        if "." not in handler:
            continue
        obj, method = handler.split(".", 1)
        if (
            obj in exported_objects
            and re.fullmatch(r"[A-Za-z_$][\w$]*", method)
            and re.search(
                rf"(?m)^\s*(?:async\s+)?{re.escape(method)}\s*\([^)]*\)\s*\{{",
                html,
            )
        ):
            funcs.add(handler)

    apis: set[str] = set()
    apis |= set(re.findall(r"""api\(['"]([^'"]+)['"]""", html))
    apis |= set(re.findall(r"""fetch\(['"]([^'"]+)['"]""", html))
    apis |= set(re.findall(r'["\'`](/api/[^"\']+)["\'`]', html))

    _ident = re.compile(r"^[A-Za-z_$][\w$]*$")  # clean JS identifier base
    missing_handlers = sorted(
        h
        for h in onclicks
        if h not in funcs
        and h.split(".")[0] not in SKIP_HANDLERS
        and not h.startswith("this.")
        and not h.endswith(".splice")
        # skip template-literal / ternary parse-artifacts (e.g. "${s.node?`fn")
        and _ident.match(h.split(".")[0])
    )
    _url_ok = re.compile(r"^[/\w\-.{}?=&%:]+$")  # real URL path chars only
    missing_apis = sorted(
        p
        for p in apis
        if (p.startswith("/api") or p.startswith("/health"))
        and _url_ok.match(p)  # skip desc/label strings ("/api/x · y → z")
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
