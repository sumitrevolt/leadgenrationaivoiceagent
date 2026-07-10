"""Hard invariant gate for the Claude-managed engineering control plane.

Enterprise Definition-of-Done: this gate FAILS (non-empty violations / exit 1)
the moment any safety invariant is weakened. It is deliberately light to import
(only app.dev_control.* + text reads) so it runs anywhere, and is also invoked
from scripts/prod_check.py.

Invariants enforced:
  1. No flagship provider is "configured" without its API-key env var set.
  2. Sensitive-data routing never leaves the local model.
  3. The patch-application boundary refuses even with AUTO_APPLY_PATCH=1.
  4. Code never executes a production deploy (manual Hostinger runbook only).
  5. The deploy approval token is fail-closed when unset.
  6. The state machine keeps a PRODUCTION_APPROVAL_REQUIRED gate before deploy.
  7. Every dev-control gate flag is registered in the automation flag registry.
  8. Both control-plane migrations (015 dev_tasks, 016 usage) exist.
"""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

_FLAGSHIP_KEYS = {
    "glm": "GLM_API_KEY", "minimax": "MINIMAX_API_KEY", "kimi": "KIMI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY", "qwen": "QWEN_API_KEY", "claude": "ANTHROPIC_API_KEY",
}
_REQUIRED_FLAGS = ("DEV_ORCHESTRATOR", "DEV_WORKER_ENABLED", "AUTO_APPLY_PATCH", "AUTO_DEPLOY")


def invariants(env: dict | None = None) -> list[str]:
    env = os.environ if env is None else env
    v: list[str] = []

    from app.dev_control.registry import MODEL_CATALOG, route_preview

    for name, key in _FLAGSHIP_KEYS.items():
        if not str(env.get(key, "")).strip() and MODEL_CATALOG.get(name, {}).get("configured"):
            v.append(f"flagship '{name}' configured without {key} set")

    rp = route_preview(task_type="code", sensitivity="sensitive", complexity="high")
    if rp.get("selected_provider") != "local" or any(c != "local" for c in rp.get("candidates", [])):
        v.append("sensitive-data routing leaves the local model")

    from app.dev_control.runner import apply_patch

    if apply_patch(task_id="gate-probe").get("applied") is not False:
        v.append("apply_patch did not refuse (auto-apply boundary breached)")

    from app.dev_control.deploy import approval_gate_status, verify_approval_token

    if approval_gate_status().get("auto_deploy_executed_by_code") is not False:
        v.append("deploy gate claims code executes deploys")
    if not str(env.get("DEV_DEPLOY_APPROVAL_TOKEN", "")).strip() and verify_approval_token("anything"):
        v.append("approval token is not fail-closed when unset")

    from app.dev_control.service import TaskState, _TRANSITIONS

    if TaskState.PRODUCTION_DEPLOYED not in _TRANSITIONS.get(TaskState.PRODUCTION_APPROVAL_REQUIRED, set()):
        v.append("state machine allows deploy without the approval gate")
    for pre in (TaskState.STAGING_READY, TaskState.STAGING_DEPLOYED):
        # deploy must only be reachable via the approval-required gate
        if TaskState.PRODUCTION_DEPLOYED in _TRANSITIONS.get(pre, set()):
            v.append(f"state {pre.value} can deploy without approval gate")

    try:
        flags_txt = (ROOT / "app" / "api" / "automation_flags.py").read_text(encoding="utf-8")
        for f in _REQUIRED_FLAGS:
            if f'"{f}"' not in flags_txt:
                v.append(f"gate flag {f} not registered in automation_flags")
    except Exception as e:  # noqa: BLE001
        v.append(f"could not read automation_flags registry: {type(e).__name__}")

    for mig in ("015_add_dev_tasks.py", "016_add_dev_task_usage.py"):
        if not (ROOT / "alembic" / "versions" / mig).exists():
            v.append(f"missing control-plane migration {mig}")

    return v


def main() -> int:
    violations = invariants()
    if violations:
        print(f"[FAIL] dev-control gate: {len(violations)} invariant violation(s):")
        for x in violations:
            print("  -", x)
        return 1
    print("[OK] dev-control gate: all invariants hold (draft-safe, no auto-apply/deploy)")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
