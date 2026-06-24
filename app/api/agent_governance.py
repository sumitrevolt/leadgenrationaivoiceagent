"""Agent governance endpoints — per-tool permissions, lifecycle hooks, custom
agents (data-defined personas).

Teen naye agent-control capabilities ke admin surface (OpenCode/Hermes/Kilo
parity):
  - agent_permissions: per-agent tool/side-effect ACL (flag AGENT_PERMISSIONS).
  - lifecycle_hooks: pre/post/error task hooks (flag AGENT_HOOKS).
  - custom_agents: data-defined personas, no code-deploy (flag CUSTOM_AGENTS).

Reads = require_admin; mutations = require_super_admin (RBAC design — core-control
changes super-admin gated, jaisa upgrader patch-status). Lazy-import per route.
Mount (main session wires): app.include_router(agent_governance.router,
prefix="/api/agents-ext").
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth_deps import require_admin, require_super_admin

router = APIRouter(tags=["AgentGovernance"])


# ----------------------------- Per-tool permissions -------------------------- #
@router.get("/permissions")
async def get_permissions(_user=Depends(require_admin)):
    """Per-agent tool/side-effect ACL matrix + risk policy + enforcement state."""
    from app.agents import agent_permissions

    return agent_permissions.list_permissions()


class PermissionIn(BaseModel):
    agent: str
    tool: str
    action: str  # allow | deny


@router.post("/permissions")
async def set_permission(body: PermissionIn, _user=Depends(require_super_admin)):
    """Ek agent+tool ka allow/deny set karo (persist). HIGH_RISK tools unset =
    deny (fail-safe). SUPER_ADMIN only — yeh side-effect gating control hai."""
    from app.agents import agent_permissions

    return agent_permissions.set_permission(body.agent, body.tool, body.action)


# ----------------------------- Lifecycle hooks ------------------------------- #
@router.get("/hooks")
async def get_hooks(_user=Depends(require_admin)):
    """Registered pre/post/error task hooks + auto-firing state."""
    from app.agents import lifecycle_hooks

    return lifecycle_hooks.list_hooks()


class HookIn(BaseModel):
    event: str  # pre_task | post_task | on_error
    name: str
    type: str  # log | ntfy | webhook
    target: str = ""


@router.post("/hooks")
async def add_hook(body: HookIn, _user=Depends(require_super_admin)):
    """Naya lifecycle hook register karo (log/ntfy/webhook). SUPER_ADMIN only —
    hooks external POST fire kar sakte hain."""
    from app.agents import lifecycle_hooks

    return lifecycle_hooks.register(body.event, body.name, body.type, body.target)


# ----------------------------- Custom agents (personas) ---------------------- #
@router.get("/custom-agents")
async def get_custom_agents(_user=Depends(require_admin)):
    """Data-defined personas (data/custom_agents/*.json) + merge note."""
    from app.agents import custom_agents

    return custom_agents.merged_roster()


class CustomAgentIn(BaseModel):
    spec: dict


@router.post("/custom-agents")
async def add_custom_agent(body: CustomAgentIn, _user=Depends(require_super_admin)):
    """Naya persona define karo (role + system_prompt + allowed_tools) bina
    code-deploy. SUPER_ADMIN only — naya agent banana control-plane change hai."""
    from app.agents import custom_agents

    return custom_agents.register(body.spec)


__all__ = ["router"]
