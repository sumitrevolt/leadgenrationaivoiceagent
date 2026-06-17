#!/usr/bin/env python3
"""Functional wiring audit — onclick handlers + fetch URLs vs FastAPI routes."""
from __future__ import annotations

import re
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILES = {
    "admin": ROOT / "frontend/admin_dashboard.html",
    "customer": ROOT / "frontend/customer_dashboard.html",
}

SKIP_HANDLERS = {
    "document.getElementById",
    "navigator.clipboard.writeText",
    "window.open",
    "alert",
    "confirm",
    "return",
    "this",
    "classList.toggle",
    "classList.remove",
    "classList.add",
}


def load_routes() -> set[str]:
    sys.path.insert(0, str(ROOT))
    from app.main import app

    out: set[str] = set()
    for r in app.routes:
        p = getattr(r, "path", None)
        if p and p.startswith("/"):
            out.add(p)
    return out


def extract_onclick_handlers(html: str) -> list[str]:
    handlers: list[str] = []
    for m in re.finditer(r'onclick="([^"]+)"', html):
        expr = m.group(1).split(";")[0].strip()
        if "(" in expr:
            handlers.append(re.sub(r"\(.*", "", expr).strip())
        else:
            handlers.append(expr)
    return handlers


def extract_functions(html: str) -> set[str]:
    funcs = set(re.findall(r"(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", html))
    funcs |= set(re.findall(r"(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", html))
    return funcs


def extract_api_paths(html: str) -> list[str]:
    paths = set(re.findall(r'["\'`](/api/[A-Za-z0-9_\-./?=&%+]+)["\'`]', html))
    paths |= set(re.findall(r'["\'`](/api/[A-Za-z0-9_\-./]+)\+', html))
    paths |= set(re.findall(r'["\'`](/health[^"\']*)["\'`]', html))
    cleaned: list[str] = []
    for p in sorted(paths):
        base = p.split("?")[0]
        base = re.sub(r"/\+encodeURIComponent\([^)]+\)", "/{id}", base)
        cleaned.append(base)
    return cleaned


def route_exists(path: str, routes: set[str]) -> bool:
    if path in routes:
        return True
    static = path.split("{")[0].rstrip("/")
    if not static:
        return False
    for r in routes:
        if r == path:
            return True
        if r.startswith(static):
            return True
        # dynamic segment match
        rx = "^" + re.sub(r"\{[^}]+\}", "[^/]+", re.escape(r)) + "$"
        if re.match(rx, path):
            return True
    return False


def main() -> int:
    routes = load_routes()
    print("=== FUNCTIONAL WIRING AUDIT ===\n")
    print(f"FastAPI routes loaded: {len(routes)}\n")

    all_handler_gaps: list[tuple[str, str]] = []
    all_route_gaps: list[tuple[str, str]] = []

    for name, fpath in FILES.items():
        html = fpath.read_text(encoding="utf-8", errors="ignore")
        handlers = [
            h
            for h in extract_onclick_handlers(html)
            if h and h not in SKIP_HANDLERS and not h.startswith("this.")
        ]
        funcs = extract_functions(html)
        apis = extract_api_paths(html)

        missing_handlers = [h for h in sorted(set(handlers)) if h not in funcs]
        missing_routes = [p for p in apis if not route_exists(p, routes)]

        print(f"## {name.upper()} ({fpath.name})")
        print(f"  buttons/handlers: {len(set(handlers))} | JS functions: {len(funcs)}")
        print(f"  API paths: {len(apis)}")

        if missing_handlers:
            print(f"  MISSING HANDLERS ({len(missing_handlers)}):")
            for h in missing_handlers:
                print(f"    - {h}")
                all_handler_gaps.append((name, h))
        else:
            print("  HANDLERS: OK (sab defined)")

        if missing_routes:
            print(f"  MISSING/UNMATCHED ROUTES ({len(missing_routes)}):")
            for p in missing_routes:
                print(f"    - {p}")
                all_route_gaps.append((name, p))
        else:
            print("  API ROUTES: OK (sab registered)")

        print()

    # Explicit high-value checks
    checks = [
        "/api/admin/customers/onboard",
        "/api/admin/system/summary",
        "/api/admin/campaign/launch",
        "/api/admin/call-recordings",
        "/api/growth/overview/today",
        "/api/growth/infra/automation-health",
        "/api/growth/selfimprove/run",
        "/api/growth/process/run/{id}/approve",
        "/api/customer/branded-feed",
        "/api/customer/approvals/pending",
        "/api/customer/routing",
        "/api/brand/frames/daily",
        "/api/clientops/approvals",
        "/api/clientops/routing",
        "/api/customer/dashboard/send-to-crm",
        "/api/assessment/scores",
        "/api/assessment/run",
    ]
    print("=== CRITICAL ENDPOINT CHECK ===")
    for c in checks:
        ok = route_exists(c, routes)
        match = [r for r in sorted(routes) if c.split("{")[0] in r][:2]
        status = "OK" if ok else "MISSING"
        print(f"  {status}: {c}  {match}")

    print()
    print("=== SUMMARY ===")
    print(f"Handler gaps: {len(all_handler_gaps)}")
    print(f"Route gaps: {len(all_route_gaps)}")
    return 1 if (all_handler_gaps or all_route_gaps) else 0


if __name__ == "__main__":
    raise SystemExit(main())
