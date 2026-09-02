# Codex Implementation Prompt

Use this prompt inside Codex after copying this playbook into the project.

```text
Read the entire docs/playbook, docs/governance, docs/architecture, docs/automation, docs/workflows, docs/agents, docs/security, docs/testing, docs/operations, docs/deployment, checklists and templates folders.

Then audit the current repository against the playbook.

Produce:
1. current architecture map
2. agent map
3. workflow map
4. scheduler map
5. queue map
6. gaps
7. critical blockers
8. implementation plan
9. test plan
10. production readiness score

Then implement the highest-priority fixes in small safe batches.

After each batch:
- run tests
- update docs
- create ADR if needed
- re-audit impacted systems

If uncertain, convene the LLM Council using docs/governance/02_LLM_COUNCIL_CONSTITUTION.md.
```
