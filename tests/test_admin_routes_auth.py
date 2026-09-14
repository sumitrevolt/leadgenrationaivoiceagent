"""P0 REGRESSION GUARD — every admin sub-router must be auth-bearing.

WHY THIS FILE EXISTS
--------------------
On 2026-09-14 a code review found `app/admin/routes/tasks.py` mounted at
`/admin/api/tasks` with **no authentication at all**: `router = APIRouter()` with
no `dependencies=`, and no `Depends(require_admin)` on any of its 8 endpoints.
Because it was included unconditionally through the Admin Command Center chain
(`app/main.py:1188` -> `app/admin/main.py:18` -> `tasks.py:29`), anyone could
list, create, update, and **DELETE** tasks, and trigger `auto-assign`, without a
token. Its siblings (`docker.py`, `system.py`, `workers.py`) were all protected —
this one file was the silent outlier.

The fix is one line (router-level `dependencies=[Depends(require_admin)]`). But a
one-line fix only closes the one hole that was found. The real lesson is
**structural**: a new sub-router added to `app/admin/` must not be able to ship
unprotected. So these tests assert the *invariant*, not just the instance:

  1. Every module in `app/admin/routes/*.py` that declares routes is auth-bearing —
     either router-level `dependencies=[Depends(<auth>)]`, or a `Depends(<auth>)`
     parameter on every route function.
  2. Every sub-router included by `app/admin/main.py` is auth-bearing (so a new
     `include_router(...)` of an unprotected router fails the suite).
  3. The composed Admin Command Center router actually *enforces* auth at runtime
     for `/admin/api/tasks` — proved with a real TestClient, not assumed.

`ast` is used deliberately (not grep): a comment or a dead stub must not be able
to satisfy the check.

THESE TESTS ARE A SECURITY GATE. If any fail, do NOT "fix" them by loosening an
assertion or deleting a case — add the missing `Depends(require_admin)`.
"""

from __future__ import annotations

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

# The dependencies that legitimately gate an admin surface. `require_admin` is the
# canonical one; the others are stricter/adjacent roles that also protect a route.
AUTH_DEPS = {
    "require_admin",
    "require_admin_or_ops_readonly",
    "require_super_admin",
    "require_manager",
    "require_agent",
    "require_permission",
    "require_customer",
}

_ROUTES_DIR = Path(__file__).resolve().parents[1] / "app" / "admin" / "routes"
_ADMIN_MAIN = Path(__file__).resolve().parents[1] / "app" / "admin" / "main.py"

_ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


# --------------------------------------------------------------------------- #
# AST helpers                                                                   #
# --------------------------------------------------------------------------- #
def _dep_name(call: ast.Call) -> str | None:
    """Return the dependency symbol name for a `Depends(<name>)` / `Depends(<name>(...))`."""
    if not isinstance(call, ast.Call):
        return None
    f = call.func
    name = f.id if isinstance(f, ast.Name) else getattr(f, "attr", None)
    if name != "Depends" or not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Name):
        return arg.id
    if isinstance(arg, ast.Attribute):
        return arg.attr
    if isinstance(arg, ast.Call):  # Depends(require_permission("x"))
        inner = arg.func
        return getattr(inner, "id", None) or getattr(inner, "attr", None)
    return None


def _iter_depends(node: ast.AST):
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            yield sub


def _router_level_auth(tree: ast.Module) -> bool:
    """True if any `router = APIRouter(dependencies=[Depends(<auth>), ...])`."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "router":
                    value = node.value
                    if isinstance(value, ast.Call):
                        for kw in value.keywords:
                            if kw.arg == "dependencies":
                                for call in _iter_depends(kw.value):
                                    if _dep_name(call) in AUTH_DEPS:
                                        return True
    return False


def _route_functions(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if (
                isinstance(dec, ast.Call)
                and isinstance(dec.func, ast.Attribute)
                and dec.func.attr in _ROUTE_METHODS
                and isinstance(dec.func.value, ast.Name)
                and dec.func.value.id == "router"
            ):
                out.append(node)
                break
    return out


def _function_has_auth(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """True if the signature has a default `Depends(<auth>)`."""
    defaults = list(node.args.defaults) + [d for d in node.args.kw_defaults if d is not None]
    for dflt in defaults:
        if isinstance(dflt, ast.Call) and _dep_name(dflt) in AUTH_DEPS:
            return True
    # also allow annotation-style Depends
    for arg in list(node.args.args) + list(node.args.kwonlyargs):
        if arg.annotation is not None:
            for call in _iter_depends(arg.annotation):
                if _dep_name(call) in AUTH_DEPS:
                    return True
    return False


def _module_is_auth_bearing(path: Path) -> tuple[bool, str]:
    """(ok, reason). ok=True when the module's routes are all protected."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    routes = _route_functions(tree)
    if not routes:
        return True, "no routes"
    if _router_level_auth(tree):
        return True, "router-level dependency"
    ungated = [f.name for f in routes if not _function_has_auth(f)]
    if ungated:
        return False, f"ungated route functions: {ungated}"
    return True, "per-endpoint dependencies"


# --------------------------------------------------------------------------- #
# 1. Every admin sub-router module is auth-bearing                              #
# --------------------------------------------------------------------------- #
def test_every_admin_route_module_is_auth_bearing():
    offenders = []
    for path in sorted(_ROUTES_DIR.glob("*.py")):
        if path.name == "__init__.py":
            continue
        ok, reason = _module_is_auth_bearing(path)
        if not ok:
            offenders.append(f"{path.name}: {reason}")
    assert not offenders, (
        "Admin sub-router(s) mounted with NO authentication — add "
        "`dependencies=[Depends(require_admin)]` to the APIRouter (or gate every "
        f"endpoint): {offenders}"
    )


# --------------------------------------------------------------------------- #
# 2. The parent Admin Command Center router only includes protected sub-routers #
# --------------------------------------------------------------------------- #
def _included_router_imports(main_path: Path) -> dict[str, str]:
    """Map local alias -> source MODULE path for routers imported in app/admin/main.py.

    Handles `from app.admin.routes.system import router as system_router` by mapping
    `system_router -> app.admin.routes.system` (the module that defines the router),
    not the imported symbol name.
    """
    tree = ast.parse(main_path.read_text(encoding="utf-8"))
    alias_to_module: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                alias = a.asname or a.name
                alias_to_module[alias] = node.module
    return alias_to_module


def test_admin_main_includes_only_protected_routers():
    tree = ast.parse(_ADMIN_MAIN.read_text(encoding="utf-8"))
    alias_to_module = _included_router_imports(_ADMIN_MAIN)

    included: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "include_router"
            and node.args
            and isinstance(node.args[0], ast.Name)
        ):
            included.append(node.args[0].id)

    assert included, "app/admin/main.py includes no sub-routers — unexpected"

    repo_root = _ADMIN_MAIN.parents[2]
    unprotected = []
    for alias in included:
        module = alias_to_module.get(alias)
        assert module, f"included router `{alias}` has no resolvable import"
        module_path = repo_root / (module.replace(".", "/") + ".py")
        assert module_path.exists(), f"resolved module missing: {module_path}"
        ok, reason = _module_is_auth_bearing(module_path)
        if not ok:
            unprotected.append(f"{alias} -> {module}: {reason}")

    assert not unprotected, (
        "app/admin/main.py includes unprotected sub-router(s): " f"{unprotected}"
    )


# --------------------------------------------------------------------------- #
# 3. Runtime proof — the composed router actually enforces auth                 #
# --------------------------------------------------------------------------- #
def test_admin_command_center_router_enforces_auth_on_tasks():
    """Mount the real composed Admin Command Center router and hit the task API
    with NO credentials. A 401/403 proves the dependency chain is live."""
    from app.admin.main import admin_router

    app = FastAPI()
    app.include_router(admin_router)
    with TestClient(app) as client:
        for path in (
            "/admin/api/tasks",
            "/admin/api/tasks/kanban",
            "/admin/api/tasks/duplicates?title=x",
            "/admin/api/tasks/worker/pilot",
        ):
            resp = client.get(path)
            assert resp.status_code in (401, 403), (
                f"GET {path} returned {resp.status_code} — admin task API is NOT "
                "auth-gated"
            )


def test_tasks_router_declares_require_admin_dependency():
    """Identity check: the router's dependency IS require_admin (not a lookalike)."""
    from app.admin.routes.tasks import router
    from app.api.auth_deps import require_admin

    dep_functions = {d.dependency for d in router.dependencies}
    assert require_admin in dep_functions, (
        "tasks router does not declare require_admin as a dependency; "
        f"found {dep_functions}"
    )


def test_tasks_router_protects_every_endpoint_via_router_level_dependency():
    """Router-level deps apply to all routes — assert the router has >0 routes and
    a non-empty dependency list, so no endpoint can be accidentally exempt."""
    from app.admin.routes.tasks import router

    assert len(router.routes) >= 8, "expected the 8 task endpoints to be registered"
    assert router.dependencies, "tasks router has no dependencies — P0 regression"


# --------------------------------------------------------------------------- #
# 4. Negative control — prove the AST guard actually has teeth                  #
# --------------------------------------------------------------------------- #
def test_helper_flags_an_ungated_module(tmp_path: Path):
    """The exact pre-fix shape of tasks.py MUST be rejected by the checker.
    If this ever passes as 'ok', the structural guard has gone blind."""
    ungated = tmp_path / "ungated.py"
    ungated.write_text(
        "from fastapi import APIRouter, Query\n"
        "router = APIRouter()\n"
        "@router.get('/admin/api/things')\n"
        "async def things(status: str | None = Query(None)):\n"
        "    return []\n",
        encoding="utf-8",
    )
    ok, reason = _module_is_auth_bearing(ungated)
    assert ok is False, "checker failed to flag an unauthenticated admin router"
    assert "things" in reason


def test_helper_accepts_router_level_and_per_endpoint_auth(tmp_path: Path):
    """Both legitimate fix shapes must pass."""
    router_level = tmp_path / "rl.py"
    router_level.write_text(
        "from fastapi import APIRouter, Depends\n"
        "from app.api.auth_deps import require_admin\n"
        "router = APIRouter(dependencies=[Depends(require_admin)])\n"
        "@router.get('/x')\n"
        "async def x():\n"
        "    return []\n",
        encoding="utf-8",
    )
    per_endpoint = tmp_path / "pe.py"
    per_endpoint.write_text(
        "from fastapi import APIRouter, Depends\n"
        "from app.api.auth_deps import require_admin\n"
        "router = APIRouter()\n"
        "@router.get('/x')\n"
        "async def x(_user=Depends(require_admin)):\n"
        "    return []\n",
        encoding="utf-8",
    )
    assert _module_is_auth_bearing(router_level)[0] is True
    assert _module_is_auth_bearing(per_endpoint)[0] is True


def test_helper_rejects_comment_that_merely_mentions_require_admin(tmp_path: Path):
    """A comment mentioning require_admin must NOT satisfy the check (why ast, not grep)."""
    fake = tmp_path / "fake.py"
    fake.write_text(
        "from fastapi import APIRouter\n"
        "# TODO: add Depends(require_admin) here one day\n"
        "router = APIRouter()\n"
        "@router.get('/x')\n"
        "async def x():\n"
        "    return []\n",
        encoding="utf-8",
    )
    assert _module_is_auth_bearing(fake)[0] is False


# --------------------------------------------------------------------------- #
# 5. F2 — the fabricated Archify demo pages must not be publicly reachable       #
# --------------------------------------------------------------------------- #
def test_archify_demo_pages_are_admin_gated():
    """`/app/archify*` served hardcoded seed data with zero API calls and were
    UNAUTHENTICATED. They are now require_admin-gated (F2). This test fails if
    the gate is ever removed."""
    from app.api.product_consoles import router as consoles_router

    app = FastAPI()
    app.include_router(consoles_router)
    with TestClient(app) as client:
        for path in ("/app/archify", "/app/archify/customer", "/app/archify/marketing"):
            resp = client.get(path)
            assert resp.status_code in (401, 403), (
                f"{path} returned {resp.status_code} — fabricated Archify demo page "
                "is publicly reachable again"
            )
