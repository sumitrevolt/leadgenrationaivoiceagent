# LeadGen Agentic Knowledge + Execution OS — ops/ layer

> **What this is:** the normalization + registry + retrieval layer that turns
> the repo's scattered documentation into a living operational knowledge
> system. Existing authoritative docs (CLAUDE.md, memory/, docs/) remain the
> source of truth — this layer INDEXES, CLASSIFIES, VALIDATES and RETRIEVES
> them. No duplication; no disconnected doc system.

## Layout

```
ops/
├── owner_truth.yaml          # LAYER A — machine-readable Owner Truth (single source)
├── playbooks/
│   ├── registry.yaml         # playbook index (21 playbooks, P0-P2)
│   └── PB-*.md               # P0 playbooks (operational format, no prose)
├── runbooks/
│   └── registry.yaml         # runbook index (37 runbooks) + GREEN/AMBER/RED classifier
knowledge/                     # LAYER B — domain knowledge (00-10, index-only + briefs)
notebook_exports/              # LAYER: Gemini Notebook-ready bundles (secret-free)
incidents/TEMPLATE.md          # Phase 9 — incident knowledge record template
tests/test_knowledge_os.py     # contract tests (12) — registry + classifier + secrets + acceptance
scripts/
├── knowledge_query.py         # Phase 5 — retrieval engine (query -> bundle)
├── validate_knowledge_os.py   # Phase 9 — validator + acceptance tests (TEST A-D)
├── gen_notebook_export.py     # Phase 8 — notebook bundle generator
├── gen_knowledge_domains.py   # Phase 1 — domain scaffold generator
└── gen_p0_playbooks.py        # Phase 3 — P0 playbook generator
```

## Operating loop (the system's runtime contract)

```
OBSERVE -> VERIFY PROJECT TRUTH (owner_truth.yaml)
        -> RETRIEVE KNOWLEDGE (knowledge_query.py)
        -> CHOOSE PLAYBOOK (playbooks/registry.yaml)
        -> CHOOSE RUNBOOK (runbooks/registry.yaml, class-checked)
        -> CHECK AUTHORITY (GREEN auto / AMBER owner / RED human)
        -> ASSIGN AGENT (HERMES_AGENT_ROSTER.yaml, 1 task = 1 owner)
        -> EXECUTE (sandboxed, idempotent where possible)
        -> TEST -> VERIFY PRODUCTION EVIDENCE (never chat claims)
        -> RECORD RESULT (progress.md + evidence path)
        -> UPDATE KANBAN (kanban/ or _tasks_sync.json)
        -> UPDATE KNOWLEDGE (incident record + runbook/playbook version + decisions.md)
        -> IMPROVE SYSTEM (lessons -> proposals, never silent authority changes)
```

## Retrieval (agents MUST use this, not giant prompts)

```bash
python scripts/knowledge_query.py "Calls are failing with Busy Line"
python scripts/knowledge_query.py "Deploy latest safe change" --json
```

Returns: domain + top runbooks (classed) + playbooks + recent incidents + truth.
Classifier note: GREEN=autonomous, AMBER=owner approval, RED=human-only.
Fail-closed: unknown/missing permission -> escalate, do NOT execute.

## Registry refresh / validation

```bash
python scripts/gen_knowledge_domains.py      # (re)create knowledge/ 00-10
python scripts/gen_p0_playbooks.py           # (re)write P0 playbooks
python scripts/gen_notebook_export.py        # (re)build notebook_exports/
python scripts/validate_knowledge_os.py      # validate + acceptance tests
.venv/Scripts/python.exe -m pytest tests/test_knowledge_os.py -q   # CI contract
```

## Acceptance tests (master prompt §23)

| Test | Prompt | Verifies |
|---|---|---|
| A | "Calls failing with Busy Line" | voice domain + RB-VOICE-002 |
| B | "Deploy latest safe change" | infra + PB-DEPLOYMENT + RB-INFRA-007/009 |
| C | "Follow up with hot leads" | PB-SALES + RB-SALES (suppression-aware) |
| D | "What did we learn from last Swara outage" | grounded voice runbook |

## Rules for agents touching this layer

1. Never edit `ops/*.yaml` by hand without re-running the validator (YAML syntax = contract).
2. New runbook -> registry.yaml entry + class + source path. Compliance/irreversible = GREEN forbidden.
3. Never store secrets in knowledge/, notebook_exports/, incidents/, ops/ — use SECRET_REF.
4. Playbook/runbook edits = version bump + `supersedes/superseded_by` + owner decision in decisions.md.
5. Freshness: every artifact carries created_at/updated_at/last_verified_at/validity.
6. Evidence rule: every automated action emits actor/task_id/runbook/action/timestamp/result/evidence_path.
7. Revenue truth = owner_confirmed_upi + invoice/ledger id ONLY. Never infer from inaccessible data.

## Gemini Notebook usage

Upload `notebook_exports/*.md` as sources. Ask grounded questions there for
RESEARCH/SYNTHESIS only. Execution authority remains Owner OS + orchestrator +
permissions + sandbox — Notebook is never the execution authority.