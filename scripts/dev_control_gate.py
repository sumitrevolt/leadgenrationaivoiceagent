"""Hard invariant gate for the Claude-managed engineering control plane.

Enterprise Definition-of-Done: this gate FAILS (non-empty violations / exit 1)
the moment any safety invariant is weakened. It is deliberately light to import
(only app.dev_control.* + text reads) so it runs anywhere, and is also invoked
from scripts/prod_check.py.

Invariants enforced:
  1. No flagship provider is "configured" without its API-key env var set.
  2. OmniRoute rejects sensitive/prohibited external dispatch.
  3. The patch-application boundary refuses even with AUTO_APPLY_PATCH=1.
  4. Code never executes a production deploy (manual Hostinger runbook only).
  5. The deploy approval token is fail-closed when unset.
  6. The state machine keeps a PRODUCTION_APPROVAL_REQUIRED gate before deploy.
  7. Every dev-control gate flag is registered in the automation flag registry.
  8. OmniRoute worktree creation stays refused and packets stay bounded.
  9. Both control-plane migrations (015 dev_tasks, 016 usage) exist.
 10. Unsigned governor rows cannot approve and the submitter stays loopback-only.
 11. Automated Claude review disables tools/customizations; unsafe Codex review refuses.
"""

from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_FLAGSHIP_KEYS = {
    "glm": "GLM_API_KEY",
    "minimax": "MINIMAX_API_KEY",
    "kimi": "KIMI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "QWEN_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
}
_REQUIRED_FLAGS = (
    "DEV_ORCHESTRATOR",
    "DEV_WORKER_ENABLED",
    "OMNIROUTE_ENABLED",
    "AUTO_APPLY_PATCH",
    "AUTO_DEPLOY",
)


def invariants(env: dict | None = None) -> list[str]:
    env = os.environ if env is None else env
    v: list[str] = []

    from app.dev_control.registry import MODEL_CATALOG

    for name, key in _FLAGSHIP_KEYS.items():
        if not str(env.get(key, "")).strip() and MODEL_CATALOG.get(name, {}).get("configured"):
            v.append(f"flagship '{name}' configured without {key} set")

    from app.platform.omniroute_client import get_task_route
    from app.platform.safe_ai_payload import SafePayloadError

    for task_type, privacy_class in (
        ("leadgen.coding_primary", "SENSITIVE_LOCAL_ONLY"),
        ("leadgen.security_review", "INTERNAL_SANITIZED"),
    ):
        try:
            get_task_route(task_type, privacy_class)
            v.append(f"OmniRoute admitted prohibited route {task_type}/{privacy_class}")
        except SafePayloadError:
            pass

    from app.dev_control.runner import apply_patch

    if apply_patch(task_id="gate-probe").get("applied") is not False:
        v.append("apply_patch did not refuse (auto-apply boundary breached)")

    from app.dev_control.deploy import approval_gate_status, verify_approval_token

    if approval_gate_status().get("auto_deploy_executed_by_code") is not False:
        v.append("deploy gate claims code executes deploys")
    if not str(env.get("DEV_DEPLOY_APPROVAL_TOKEN", "")).strip() and verify_approval_token(
        "anything"
    ):
        v.append("approval token is not fail-closed when unset")

    from app.dev_control.service import _TRANSITIONS, TaskState

    if TaskState.PRODUCTION_DEPLOYED not in _TRANSITIONS.get(
        TaskState.PRODUCTION_APPROVAL_REQUIRED, set()
    ):
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

    from app.dev_control.context_packets import MAX_CODE_EXCERPTS

    if MAX_CODE_EXCERPTS > 8:
        v.append("OmniRoute context packet excerpt cap exceeds 8")
    try:
        worktree_script = (ROOT / "scripts" / "omniroute-worktrees.sh").read_text(encoding="utf-8")
        if "git worktree add" in worktree_script or "exit 2" not in worktree_script:
            v.append("OmniRoute worktree creation is not fail-closed")
    except Exception as e:  # noqa: BLE001
        v.append(f"could not read OmniRoute worktree guard: {type(e).__name__}")

    from app.dev_control.governor_reviews import review_gate_status

    unsigned = {
        "proposal_sha256": "a" * 64,
        "governor_reviews": {
            name: {"decision": "approve", "artifact_hash": "a" * 64}
            for name in ("claude", "chatgpt")
        },
    }
    if review_gate_status(unsigned).get("approved"):
        v.append("unsigned governor reviews can pass the promotion gate")
    try:
        api_text = (ROOT / "app" / "api" / "dev_tasks.py").read_text(encoding="utf-8")
        for marker in (
            "verify_governor_attestation",
            "X-Governor-Timestamp",
            "X-Governor-Nonce",
            "X-Governor-Signature",
        ):
            if marker not in api_text:
                v.append(f"governor review endpoint missing {marker}")
        submitter = (ROOT / "scripts" / "governor_review_submit.py").read_text(encoding="utf-8")
        if "loopback_url_required" not in submitter or "_LOOPBACK_HOSTS" not in submitter:
            v.append("governor review submitter is not loopback-only")
        model_reviewer = (ROOT / "scripts" / "governor_model_review.py").read_text(encoding="utf-8")
        for marker in (
            '"--tools"',
            '"--safe-mode"',
            '"--no-chrome"',
            '"--system-prompt"',
            "chatgpt_toolless_adapter_unavailable",
        ):
            if marker not in model_reviewer:
                v.append(f"governor model reviewer missing hard boundary {marker}")
    except Exception as e:  # noqa: BLE001
        v.append(f"could not inspect governor attestation boundary: {type(e).__name__}")

    return v


def main() -> int:
    violations = invariants()
    if violations:
        print(f"[FAIL] dev-control gate: {len(violations)} invariant violation(s):")
        for x in violations:
            print("  -", x)
        return 1
    print("[OK] dev-control gate: governed packets only; no provider worktree/auto-apply/deploy")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
