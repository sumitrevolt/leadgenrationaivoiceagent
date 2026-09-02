---
type: AgentPolicy
title: Agent OS routing policy
description: Privacy / OmniRoute / publish / contact gates for staff agents.
tags: [agent-os, omniroute, privacy]
timestamp: 2026-07-17T00:00:00Z
resource: app/platform/agent_os_routing.py
---

# Agent OS routing policy

- Specs live under `agent-os/agents/` (code-derived from `team.py` STAFF).
- Runtime governance: `app/platform/agent_os_routing.py` (privacy class, route task, publish/contact flags).
- OmniRoute staff hook: double-gated `OMNIROUTE_ENABLED` + `OMNIROUTE_AGENTS`, bulk-only via `free_ai.chat`, sanitized `leadgen.agent_ops`, fail-open to free_ai chain.
- Even agents with `may_contact_customers=True` (e.g. Zara) still use INTERNAL_SANITIZED masking on OmniRoute path.
- Pass `agent_key` / `product` into `free_ai.chat` so governance is not bypassed.

Related: [Agent OS](../architecture/agent-os.md), [OmniRoute](../architecture/omniroute.md).
