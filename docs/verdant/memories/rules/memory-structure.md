# Memory System Index

Ontology-first layout: retrieval paths are stable, authoring paths may evolve.

## Directory Structure

```text
memories/
├── _index.md                    # Structure guide
├── active/                      # Runtime high-value injection layer (serving, not content type)
├── semantic/                    # Stable knowledge about user, world, entities
│   ├── profile/                 # User preferences and interaction style
│   ├── learned_facts/           # Reusable lessons not tied to one entity
│   └── entities/                # Entity-scoped engineering knowledge (projects, repos, tools)
├── procedural/                  # Action knowledge, workflows, operating guidance
│   ├── operating-rules/         # User-authored direct rules
│   └── skills/workflows/        # Repeatable workflows and playbooks
├── episodic/                    # Historical experience and time-bound records
│   └── daily/                   # Daily logs (auto-written, do not manually edit)
├── rules/                       # Framework-managed prompt/runtime rules (cold-start overwritten)
├── lessons.jsonl                # System-managed lesson log (consolidation input)
├── scripts/                     # Utility scripts for memory maintenance
└── customize/                   # Design reference docs (not memory ontology)
```

Outside `memories/`: `~/.verdent/workspace/config/` contains machine config (feishu-bots.json, user-memory.json).

## Classification Quick Reference

| Location                       | Put here when                                                    |
| ------------------------------ | ---------------------------------------------------------------- |
| `semantic/profile/`            | Stable user preferences, communication style, proactive behavior |
| `semantic/learned_facts/`      | Reusable lesson not tied to one entity                           |
| `semantic/entities/`           | Knowledge about a concrete project, repo, tool, or relation      |
| `procedural/operating-rules/`  | User-authored direct operating rule                              |
| `procedural/skills/workflows/` | Repeatable workflow, playbook, or verification process           |
| `episodic/daily/`              | Dated events, observations, or outcomes                          |
| `active/`                      | Content promoted for runtime injection (not raw source)          |
| `rules/`                       | Framework-managed rules (may be overwritten on cold start)       |

## Read / Write Guide

| Location                       | Read when                            | Write when                        |
| ------------------------------ | ------------------------------------ | --------------------------------- |
| `semantic/profile/`            | Adapting tone and initiative level   | User preference becomes stable    |
| `semantic/learned_facts/`      | Reusing durable lessons              | A reusable lesson is consolidated |
| `semantic/entities/`           | Reasoning about a project/repo/issue | New entity facts become stable    |
| `procedural/operating-rules/`  | Checking user constraints            | User authors a standing rule      |
| `procedural/skills/workflows/` | Executing a repeatable workflow      | A workflow is formalized          |
| `episodic/daily/`              | Reviewing recent history             | Logging daily events (auto)       |
| `active/`                      | Building runtime context             | Promoting important memory        |
| `rules/`                       | Cold start rule loading              | Framework refreshes rules         |
