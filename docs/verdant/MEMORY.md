# Memory System

- Location: memories/
- Structure: `_index.md` (index), `rules/` (model directives), `knowledge/` (accumulated knowledge), `state/` (runtime state)
- **Rules files** (`rules/task-dispatch.md`, `rules/memory-query.md`): framework-managed, auto-loaded, overwritten on upgrade
- **User rules** (`rules/proactivity.md`, `rules/communication.md`, `rules/others.md`): user-managed, never overwritten

## Memory Files Reference

| Directory             | Purpose                          | Examples                                                |
| --------------------- | -------------------------------- | ------------------------------------------------------- |
| `rules/`              | Model directives (auto-loaded)   | `task-dispatch.md`, `memory-query.md`, `proactivity.md` |
| `knowledge/lessons/`  | Experience accumulation (search) | `manager-lessons.md`                                    |
| `knowledge/code/`     | Code analysis results            | `hotfiles-{date}.json`                                  |
| `knowledge/projects/` | Project context                  | `relations.json`                                        |
| `state/daily/`        | Daily work logs                  | `2026-04-10.md`                                         |
