from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOC_OUTPUT = ROOT / "docs" / "evidence" / "DSH_MIGRATION_CONTRACT_20260814.json"
FIXTURE_OUTPUT = ROOT / "tests" / "fixtures" / "dsh_migration_contract.json"
SCHEMA = "leadgen/dsh_migration_contract/2026-08-14"
TARGET_MODULES = (
    "app.platform.agent_runtime",
    "app.platform.agent_runtime_workforce",
)
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "agent-transcripts",
    ".freebuff",
}


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _load_modules() -> tuple[Any, Any, Any]:
    root_str = str(ROOT)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    from app.platform import agent_registry as ar
    from app.platform import agent_runtime as rt
    from app.platform import agent_runtime_workforce as wf

    wf.ensure_workforce_registered()
    return ar, rt, wf


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for base in ("app", "scripts", "tests"):
        base_path = ROOT / base
        if not base_path.exists():
            continue
        for path in base_path.rglob("*.py"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _resolve_from_import(module: str | None, name: str) -> str | None:
    if module == "app.platform" and name in {"agent_runtime", "agent_runtime_workforce"}:
        return f"app.platform.{name}"
    if not module:
        return None
    if module in TARGET_MODULES or any(
        module.startswith(target + ".") for target in TARGET_MODULES
    ):
        return f"{module}.{name}"
    return None


def _resolve_import(name: str) -> str | None:
    if name in TARGET_MODULES or any(name.startswith(target + ".") for target in TARGET_MODULES):
        return name
    return None


class RuntimeUsageScanner(ast.NodeVisitor):
    def __init__(self, rel_path: str):
        self.rel_path = rel_path
        self.scope: list[str] = []
        self.alias_scopes: list[dict[str, str]] = [{}]
        self.module_level_imports: list[dict[str, Any]] = []
        self.dynamic_imports: list[dict[str, Any]] = []
        self.call_sites: list[dict[str, Any]] = []

    def _scope_name(self) -> str:
        return ".".join(self.scope) if self.scope else "module"

    def _lookup_alias(self, name: str) -> str | None:
        for scope_aliases in reversed(self.alias_scopes):
            if name in scope_aliases:
                return scope_aliases[name]
        return None

    def _record_import(self, entry: dict[str, Any]) -> None:
        if self.scope:
            self.dynamic_imports.append(entry)
        else:
            self.module_level_imports.append(entry)

    def _bind_alias(self, local_name: str, target: str) -> None:
        self.alias_scopes[-1][local_name] = target

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            target = _resolve_import(alias.name)
            if not target:
                continue
            local_name = alias.asname or alias.name.split(".")[-1]
            self._bind_alias(local_name, target)
            self._record_import(
                {
                    "file": self.rel_path,
                    "line": node.lineno,
                    "scope": self._scope_name(),
                    "module": target,
                    "symbol": "",
                    "local_name": local_name,
                }
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            target = _resolve_from_import(node.module, alias.name)
            if not target:
                continue
            local_name = alias.asname or alias.name
            self._bind_alias(local_name, target)
            parts = target.split(".")
            symbol = parts[-1] if len(parts) > 4 else ""
            module = ".".join(parts[:-1]) if symbol else target
            self._record_import(
                {
                    "file": self.rel_path,
                    "line": node.lineno,
                    "scope": self._scope_name(),
                    "module": module,
                    "symbol": symbol,
                    "local_name": local_name,
                }
            )
        self.generic_visit(node)

    def _resolve_call(self, node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            return self._lookup_alias(node.id)
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, ast.Name):
                base = self._lookup_alias(node.value.id)
                if base:
                    return f"{base}.{node.attr}"
            base_name = self._resolve_call(node.value)
            if base_name:
                return f"{base_name}.{node.attr}"
        return None

    def visit_Call(self, node: ast.Call) -> None:
        target = self._resolve_call(node.func)
        if target and any(
            target == module or target.startswith(module + ".") for module in TARGET_MODULES
        ):
            self.call_sites.append(
                {
                    "file": self.rel_path,
                    "line": node.lineno,
                    "scope": self._scope_name(),
                    "call": target,
                }
            )
        self.generic_visit(node)

    def _visit_scoped(self, node: ast.AST, name: str) -> None:
        self.scope.append(name)
        self.alias_scopes.append({})
        self.generic_visit(node)
        self.alias_scopes.pop()
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_scoped(node, node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_scoped(node, node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_scoped(node, node.name)


def _scan_runtime_usage() -> dict[str, Any]:
    module_level_imports: list[dict[str, Any]] = []
    dynamic_imports: list[dict[str, Any]] = []
    call_sites: list[dict[str, Any]] = []
    for path in _iter_python_files():
        rel_path = _relative(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel_path)
        scanner = RuntimeUsageScanner(rel_path)
        scanner.visit(tree)
        module_level_imports.extend(scanner.module_level_imports)
        dynamic_imports.extend(scanner.dynamic_imports)
        call_sites.extend(scanner.call_sites)

    def sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
        return (item["file"], item["line"], item["scope"], item.get("call", ""))

    return {
        "module_level_imports": sorted(module_level_imports, key=sort_key),
        "dynamic_imports": sorted(dynamic_imports, key=sort_key),
        "call_sites": sorted(call_sites, key=sort_key),
    }


def _collect_model_fields(tree: ast.AST) -> dict[str, list[str]]:
    models: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {_dotted_name(base) for base in node.bases}
        if "BaseModel" not in bases:
            continue
        fields: list[str] = []
        for child in node.body:
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                fields.append(child.target.id)
        models[node.name] = fields
    return models


def _route_decorator_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str] | None:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func_name = _dotted_name(decorator.func)
        if func_name not in {
            "router.get",
            "router.post",
            "router.put",
            "router.delete",
            "router.patch",
        }:
            continue
        if not decorator.args or not isinstance(decorator.args[0], ast.Constant):
            continue
        method = func_name.split(".")[-1].upper()
        return method, str(decorator.args[0].value)
    return None


def _return_dict_keys(tree: ast.AST, function_name: str) -> list[str]:
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            or node.name != function_name
        ):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Return) and isinstance(child.value, ast.Dict):
                keys: list[str] = []
                for key in child.value.keys:
                    if isinstance(key, ast.Constant) and isinstance(key.value, str):
                        keys.append(key.value)
                if keys:
                    return sorted(keys)
    return []


def _assigned_dict_keys(tree: ast.AST, function_name: str, variable_name: str) -> list[str]:
    for node in ast.walk(tree):
        if (
            not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            or node.name != function_name
        ):
            continue
        for child in node.body:
            value = None
            target_names: set[str] = set()
            if isinstance(child, ast.Assign):
                value = child.value
                target_names = {
                    target.id for target in child.targets if isinstance(target, ast.Name)
                }
            elif isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                value = child.value
                target_names = {child.target.id}
            if not isinstance(value, ast.Dict):
                continue
            if variable_name not in target_names:
                continue
            keys: list[str] = []
            for key in value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    keys.append(key.value)
            if keys:
                return sorted(keys)
    return []


def _runtime_api_contract() -> dict[str, Any]:
    api_path = ROOT / "app" / "api" / "owner_os.py"
    runtime_path = ROOT / "app" / "platform" / "agent_runtime.py"
    api_tree = ast.parse(api_path.read_text(encoding="utf-8"), filename=_relative(api_path))
    runtime_tree = ast.parse(
        runtime_path.read_text(encoding="utf-8"), filename=_relative(runtime_path)
    )
    models = _collect_model_fields(api_tree)
    routes: list[dict[str, Any]] = []
    for node in ast.walk(api_tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        route = _route_decorator_info(node)
        if not route:
            continue
        method, path = route
        if path not in {"/runtime", "/runtime/run"}:
            continue
        body_model = ""
        path_or_query: list[str] = []
        for arg in node.args.args:
            if arg.arg == "user":
                continue
            anno = _dotted_name(arg.annotation) if arg.annotation is not None else ""
            if anno in models:
                body_model = anno
            else:
                path_or_query.append(arg.arg)
        if node.name == "owner_runtime_status":
            output_fields = sorted(
                set(_return_dict_keys(runtime_tree, "runtime_status"))
                | {"dlq_tail", "workforce_rollout"}
            )
        elif node.name == "owner_runtime_run":
            output_fields = _assigned_dict_keys(api_tree, node.name, "out")
        else:
            output_fields = _return_dict_keys(api_tree, node.name)
        routes.append(
            {
                "handler": node.name,
                "method": method,
                "path": f"/api/admin/owner-os{path}",
                "body_model": body_model,
                "input_fields": models.get(body_model, []),
                "path_or_query_fields": sorted(path_or_query),
                "output_fields": output_fields,
            }
        )
    routes.sort(key=lambda item: (item["path"], item["method"]))
    return {"routes": routes}


def _tenant_scope(capabilities: list[dict[str, Any]]) -> str:
    tenant_flags = {bool(cap["tenant_scoped"]) for cap in capabilities}
    if tenant_flags == {True}:
        return "tenant"
    if tenant_flags == {False}:
        return "global"
    return "mixed"


def _approval_requirement(agent_id: str, lane: str, capabilities: list[dict[str, Any]]) -> str:
    if agent_id in {"swara", "ananya"}:
        return "red_hard_off"
    if agent_id == "zara":
        return "approved_content_only"
    if any(cap["requires_approval"] for cap in capabilities):
        return "final_approval_gated"
    if lane == "AMBER":
        return "final_approval_gated"
    return "none"


def _rollout_wave(agent_id: str, contract: Any, rt: Any) -> str:
    if agent_id in {"swara", "ananya"}:
        return "frozen_never_dsh"
    if agent_id == "kavya":
        return "wave_1_read_only"
    if agent_id == "isha":
        return "wave_2_draft"
    if agent_id == "zara":
        return "approved_social_handoff"
    if contract.team == "voice":
        return "voice_path_excluded"
    if agent_id in rt.PILOT_AGENTS:
        return "current_green_pilot_read_only"
    if contract.lane == "AMBER":
        return "amber_customer_touch_final_approval_gated"
    return "green_internal_mutator"


def _capability_record(cap: Any) -> dict[str, Any]:
    return {
        "action": cap.action,
        "side_effect": cap.side_effect,
        "tenant_scoped": bool(cap.tenant_scoped),
        "requires_approval": bool(cap.requires_approval),
        "description": cap.description,
        "handler": f"{cap.fn.__module__}.{cap.fn.__name__}",
    }


def build_contract() -> dict[str, Any]:
    ar, rt, wf = _load_modules()
    usage = _scan_runtime_usage()
    api_contract = _runtime_api_contract()
    registry = ar.build_registry()
    rows: list[dict[str, Any]] = []
    for agent_id, contract in sorted(registry.items()):
        capability_names = rt.capabilities_for(agent_id)
        capabilities = [
            _capability_record(rt.get_capability(agent_id, action)) for action in capability_names
        ]
        rows.append(
            {
                "agent_id": agent_id,
                "name": contract.name,
                "team": contract.team,
                "lane": contract.lane,
                "mode": contract.default_mode,
                "capabilities": capabilities,
                "tenant_scope": _tenant_scope(capabilities) if capabilities else "global",
                "approval_requirement": _approval_requirement(
                    agent_id, contract.lane, capabilities
                ),
                "timeout_s": contract.run_timeout_s,
                "idempotency": contract.idempotency,
                "current_callers": sorted({cap["handler"] for cap in capabilities}),
                "current_jobs": list(contract.jobs),
                "rollout_wave": _rollout_wave(agent_id, contract, rt),
                "dsh_candidate": agent_id not in {"swara", "ananya"},
                "voice_path_allowed": contract.team != "voice",
            }
        )

    dsh_candidates = [row["agent_id"] for row in rows if row["dsh_candidate"]]
    return {
        "schema": SCHEMA,
        "status": "LOCAL_ONLY",
        "scope": {
            "adr_179_still_rejects": [
                "stock wheel",
                "direct embedding",
                "default tools",
                "direct provider access",
            ],
            "conditionally_superseded_for": "owner_mandated_hardened_source_built_linux_path_only",
            "dsh_replaces_only": ["planning", "turn_loop", "tool_loop"],
            "dsh_does_not_replace": [
                "celery",
                "python_domain_engines",
                "agent_registry",
                "owner_os_approvals",
                "tenant_controls",
                "compliance_controls",
                "billing_controls",
            ],
            "preserved_identities": 31,
            "migratable_identities": 29,
            "frozen_hard_off_identities": ["swara", "ananya"],
            "all_dsh_flags_default": "OFF",
            "authority_gate": "no_authority_no_deploy_no_retirement_until_evidence_gates",
        },
        "summary": {
            "rows": len(rows),
            "dsh_candidates": len(dsh_candidates),
            "pilot_agents": sorted(rt.PILOT_AGENTS),
            "frozen_voice_agents": sorted(wf.FROZEN_VOICE_AGENTS),
        },
        "matrix": rows,
        "runtime_baseline": {
            "module_level_imports": usage["module_level_imports"],
            "dynamic_imports": usage["dynamic_imports"],
            "call_sites": usage["call_sites"],
        },
        "owner_os_runtime_api": api_contract,
    }


def render_contract_json() -> str:
    return json.dumps(build_contract(), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def write_outputs() -> list[str]:
    payload = render_contract_json()
    outputs = [DOC_OUTPUT, FIXTURE_OUTPUT]
    for path in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    return [_relative(path) for path in outputs]


def main() -> int:
    written = write_outputs()
    print(json.dumps({"ok": True, "written": written}, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
