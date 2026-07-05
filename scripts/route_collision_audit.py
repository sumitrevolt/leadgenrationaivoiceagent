#!/usr/bin/env python3
"""route_collision_audit.py — STATIC duplicate-route guard (source-level, flag-independent).

Why this exists (R-02, audit 2026-07-05): prod_check.py's runtime duplicate check
(app.routes scan) only sees routers that actually MOUNT — env-flag-gated
include_router calls inside `if os.getenv(...)` blocks are invisible in CI where
the flag is off. FastAPI is first-route-wins, so a collision hidden behind a flag
ships silently and only shadows in prod when the flag flips. This script parses
the SOURCE (ast) instead of the live app, so every mount counts regardless of flags.

FAIL  = exact (METHOD, full-path) registered from 2+ places (static shadow).
INFO  = shared router prefixes (/api/admin x3 etc.) — legitimate today, listed so
        additions to a shared surface get eyeballed; NEVER fails the check.

Usage:
  python scripts/route_collision_audit.py            # report; exit 1 on duplicates
Wired into scripts/prod_check.py (defensive import — never blocks if this breaks).
"""
from __future__ import annotations

import ast
import pathlib
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP = ROOT / "app"
ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


def _const_str(node) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _kw(call: ast.Call, name: str):
    for k in call.keywords:
        if k.arg == name:
            return k.value
    return None


class _Module:
    def __init__(self, modname: str):
        self.modname = modname
        self.routers: dict[str, str] = {}  # var -> own prefix ("" if none/dynamic)
        self.routes: list[tuple[str, str, str, int]] = []  # (var, METHOD, path, lineno)
        # include edges: (parent_var|"app", target_expr, prefix, lineno, resolvable_prefix)
        self.includes: list[tuple[str, ast.expr, str, int, bool]] = []
        self.name_imports: dict[str, tuple[str, str]] = {}  # local -> (module, orig_name)
        self.mod_imports: dict[str, str] = {}  # local -> module path


def _modname(path: pathlib.Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _parse_module(path: pathlib.Path) -> _Module | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None
    m = _Module(_modname(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                m.mod_imports[a.asname or a.name.split(".")[0]] = a.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                local = a.asname or a.name
                m.name_imports[local] = (node.module, a.name)
                # `from app.api import leads` — leads is a module too
                m.mod_imports.setdefault(local, f"{node.module}.{a.name}")
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            fname = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else "")
            if fname == "APIRouter":
                pfx_node = _kw(node.value, "prefix")
                pfx = _const_str(pfx_node) if pfx_node is not None else ""
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        m.routers[t.id] = pfx or ""
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                    continue
                owner = dec.func.value
                if not isinstance(owner, ast.Name):
                    continue
                meth = dec.func.attr
                if meth in ROUTE_METHODS or meth == "websocket":
                    path_s = _const_str(dec.args[0]) if dec.args else None
                    if path_s is not None:
                        mm = "WS" if meth == "websocket" else meth.upper()
                        m.routes.append((owner.id, mm, path_s, dec.lineno))
                elif meth == "api_route":
                    path_s = _const_str(dec.args[0]) if dec.args else None
                    meths_node = _kw(dec, "methods")
                    if path_s is not None and isinstance(meths_node, (ast.List, ast.Tuple)):
                        for el in meths_node.elts:
                            ms = _const_str(el)
                            if ms:
                                m.routes.append((owner.id, ms.upper(), path_s, dec.lineno))
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "include_router":
            owner = node.func.value
            parent = owner.id if isinstance(owner, ast.Name) else None
            if parent is None or not node.args:
                continue
            pfx_node = _kw(node, "prefix")
            if pfx_node is None:
                pfx, ok = "", True
            else:
                s = _const_str(pfx_node)
                pfx, ok = (s, True) if s is not None else ("", False)
            m.includes.append((parent, node.args[0], pfx, node.lineno, ok))
    return m


def _resolve_target(mod: _Module, expr: ast.expr) -> tuple[str, str] | None:
    """Resolve an include_router target expr to (module, router_var)."""
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        base = expr.value.id
        if base in mod.mod_imports:
            return (mod.mod_imports[base], expr.attr)
        return None
    if isinstance(expr, ast.Name):
        n = expr.id
        if n in mod.routers:  # local router var
            return (mod.modname, n)
        if n in mod.name_imports:
            src_mod, orig = mod.name_imports[n]
            return (src_mod, orig)
    return None


def audit() -> dict:
    mods: dict[str, _Module] = {}
    for p in APP.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        m = _parse_module(p)
        if m is not None:
            mods[m.modname] = m

    skipped = 0
    # (module, var) -> list of accumulated mount prefixes
    acc: dict[tuple[str, str], list[str]] = defaultdict(list)

    def expand(key: tuple[str, str], base: str, depth: int) -> None:
        nonlocal skipped
        if depth > 8:  # cycle guard
            skipped += 1
            return
        modname, var = key
        mod = mods.get(modname)
        if mod is None or var not in mod.routers:
            skipped += 1
            return
        full = base + mod.routers[var]
        acc[key].append(full)
        for parent, target, pfx, _ln, ok in mod.includes:
            if parent != var:
                continue
            if not ok:
                skipped += 1
                continue
            child = _resolve_target(mod, target)
            if child is None:
                skipped += 1
                continue
            expand(child, full + pfx, depth + 1)

    # roots: app.include_router(...) + @app.<method> in app/main.py
    main_mod = mods.get("app.main")
    static_routes: list[tuple[str, str, str]] = []  # (METHOD, full_path, origin)
    if main_mod is not None:
        for parent, target, pfx, ln, ok in main_mod.includes:
            if parent != "app":
                continue
            if not ok:
                skipped += 1
                continue
            child = _resolve_target(main_mod, target)
            if child is None:
                skipped += 1
                continue
            expand(child, pfx, 1)
        for var, meth, path_s, ln in main_mod.routes:
            if var == "app":
                static_routes.append((meth, path_s, f"app/main.py:{ln}"))

    for (modname, var), bases in acc.items():
        mod = mods[modname]
        rel = modname.replace(".", "/") + ".py"
        for rvar, meth, path_s, ln in mod.routes:
            if rvar != var:
                continue
            for base in bases:
                static_routes.append((meth, base + path_s, f"{rel}:{ln}"))

    groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    for meth, full, origin in static_routes:
        groups[(meth, full)].append(origin)
    duplicates = [
        f"{meth} {full} <- {', '.join(sorted(set(origins)))}"
        for (meth, full), origins in sorted(groups.items())
        if len(origins) > 1
    ]

    # INFO: router-declared prefixes shared across files (legit today; census only)
    by_prefix: dict[str, set] = defaultdict(set)
    for modname, mod in mods.items():
        for var, pfx in mod.routers.items():
            if pfx:
                by_prefix[pfx].add(modname.replace(".", "/") + f".py::{var}")
    shared_prefixes = {p: sorted(v) for p, v in by_prefix.items() if len(v) > 1}

    return {
        "n_routes": len(static_routes),
        "duplicates": duplicates,
        "shared_prefixes": shared_prefixes,
        "skipped": skipped,
    }


def main() -> int:
    rep = audit()
    print(f"# static route scan: {rep['n_routes']} routes resolved, "
          f"{rep['skipped']} unresolvable mounts/prefixes skipped")
    if rep["shared_prefixes"]:
        print(f"\n[i] shared router prefixes ({len(rep['shared_prefixes'])}) — legit today, "
              "naya route add karne se pehle in files me grep karo:")
        for p, owners in sorted(rep["shared_prefixes"].items()):
            print(f"  {p}  x{len(owners)}: {', '.join(owners)}")
    if rep["duplicates"]:
        print(f"\n[FAIL] {len(rep['duplicates'])} static duplicate (method,path) — "
              "first-route-wins shadow (flag-gated mounts included):")
        for d in rep["duplicates"]:
            print("  -", d)
        return 1
    print("\n[OK] no static duplicate routes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
