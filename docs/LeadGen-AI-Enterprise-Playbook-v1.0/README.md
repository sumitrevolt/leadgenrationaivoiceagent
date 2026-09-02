# LeadGen AI Enterprise Operating System Playbook v1.0

Generated for the LeadGen AI project.

This repository is a production engineering documentation suite for hardening, testing, governing, and operating an AI-powered lead generation SaaS platform.

## How to Use

1. Copy this folder into your project under `docs/`.
2. Give `docs/playbook/00_MASTER_EXECUTION_PROMPT.md` to Claude Code, Codex, Cursor, or your coding agent.
3. Ask the agent to read the full `docs/` folder before modifying code.
4. Enforce the checklists before deployment.
5. Record major technical decisions under `docs/adr/`.
6. Update runbooks after every production incident.

## Core Rule

No agent, workflow, scheduler, queue, API, billing flow, CRM flow, voice flow, or customer-facing module is production-ready unless it is implemented, tested, observable, recoverable, secure, documented, and covered by a runbook.

## Recommended Project Placement

```text
leadgen-ai/
  docs/
    LeadGen-AI-Enterprise-Playbook-v1.0/
      README.md
      docs/
      checklists/
      templates/
      diagrams/
```

## Documents Included

- Master execution prompt
- AI constitution
- Executive agent system
- LLM council constitution
- Architecture standards
- Workflow and automation playbooks
- Scheduler, queue, event bus and self-healing standards
- Security, testing, deployment and operations playbooks
- Agent specifications
- Workflow specifications
- Runbooks
- Checklists
- ADR templates
- Claude/Cursor/Codex rules

## Version

v1.0 — 2026-06-25
