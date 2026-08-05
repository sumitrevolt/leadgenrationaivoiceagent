# PR Factory workflow (Wave 1)

```text
GitHub Issues → Spec Kit constitution → Task YAML → tools/pr_factory
  → external_agents.create_mission → Claude/Cursor runner
  → independent reviewer → auto-merge label train
```

## Operator steps (local, flags ON)

1. Author atomic task YAML (see `task_schema.py` required fields).
2. `python -m tools.pr_factory.orchestrator submit path/to/task.yaml`
3. GREEN missions may advance via existing orchestrator APIs; AMBER → Owner OS.
4. RED titles/descriptions refused at create.
5. Merge: apply `auto-merge` label only when review GREEN + required checks (see `merge_train.py`).

## Hard rules

- No second mission ledger; no post-create `store.get`/`store.save` (use `initial_evidence`).
- Executor ≠ reviewer.
- Caps in `budgets.py`.
- CI-repair Wave 1 = read-only diagnosis (`contents: read`, `workflow_dispatch` only).
