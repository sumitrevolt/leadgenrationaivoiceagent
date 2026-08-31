# _work/ — Multi-Agent Artifact Root

Scratch space for task deliverables produced by workstream agents.
Convention (see `docs/MULTI_AGENT_WORKFLOW.md` §4):

```
_work/<WS-ID>/<TASK-ID>/
    spec.md            # acceptance criteria + affected surfaces + rollback
    changed_files.txt  # exact paths, one per line
    tests.txt          # exact commands that were run
    evidence.md        # actual output (pass counts, health status, SHA)
    handoff.md         # 5-field handoff: what / where / verify / known issues / next
```

Rules:
- One directory per task. Never write outside your assigned `_work/<WS-ID>/` tree.
- **Evidence lives in `progress.md` and `docs/` — not only here.** Task dirs are gitignored
  (`_work/*/`); only this README is tracked.
- A task without `evidence.md` is not DONE.
