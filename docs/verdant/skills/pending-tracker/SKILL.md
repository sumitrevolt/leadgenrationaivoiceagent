---
name: pending-tracker
description: |
  Manage the Pending Tracker — a requirement-level tracking system for the Manager.
  Use this skill to add, update, complete, list, and link tasks to requirements.
  The tracker persists as a JSON file and is injected into Manager context each turn.
metadata:
  version: '1.0.4'
---

# Pending Tracker

Manage requirement-level items that the Manager needs to track across sessions.

**Design philosophy**: Task layer is facts, Tracker layer is attention. The tracker records what the Manager needs to actively manage, follow up, and close out — not a mirror of task status.

## When to Use

- A new user requirement emerges that may span multiple tasks
- A task completes and has follow-up actions
- Need to check what requirements are still open
- Link a new task to an existing requirement
- Mark a requirement as complete after verifying all work is done

## Data File

`./pending-tracker.json` in the current manager workspace.

For shell-only contexts, use `$VERDENT_HOME/pending-tracker.json`.

On first use, the CLI imports legacy `~/.verdent/workspace/pending-tracker.json` when the new file does not exist. After that, all writes go to the current manager workspace file above.

## Item Schema

```json
{
  "id": "8-char hex hash (sha256(title+timestamp)[:8])",
  "title": "Requirement description",
  "status": "pend | running | hold | complete",
  "tasks": [
    { "id": "task-uuid-1", "name": "Task name 1" },
    { "id": "task-uuid-2", "name": "Task name 2" }
  ],
  "note": "Optional context",
  "created_at": "ISO-8601",
  "updated_at": "ISO-8601"
}
```

## CLI Commands

All operations are performed via `python3 ./.verdent/skills/pending-tracker/pending.py` from the current manager workspace. In shell-only contexts where the cwd is not the manager workspace, use `python3 "$VERDENT_HOME/.verdent/skills/pending-tracker/pending.py"`.

### list

Show all active items (non-complete). Include stale warnings for items not updated in 3+ days.

```bash
python3 pending.py list
python3 pending.py list --all        # include completed
```

**Output format:**

```json
{
  "count": 3,
  "items": [
    {
      "id": "a3f7b2c1",
      "title": "switch_mode 上线",
      "status": "running",
      "tasks": 2,
      "age": "3d",
      "stale": true
    }
  ]
}
```

### add

Create a new requirement item. ID is auto-generated.

```bash
python3 pending.py add "需求标题"
python3 pending.py add "需求标题" --note "补充说明"
```

**Output format:**

```json
{
  "success": true,
  "id": "a3f7b2c1",
  "title": "需求标题"
}
```

### update

Update an existing item's fields.

```bash
python3 pending.py update <id> --status running
python3 pending.py update <id> --status hold --note "原因说明"
python3 pending.py update <id> --note "更新备注"
```

**Output format:**

```json
{
  "success": true,
  "id": "a3f7b2c1",
  "status": "running"
}
```

### complete

Mark a requirement as complete. Keeps last 10 completed items, older ones are auto-deleted.

```bash
python3 pending.py complete <id>
python3 pending.py complete <id> --note "完成说明"
```

**Output format:**

```json
{
  "success": true,
  "id": "a3f7b2c1",
  "status": "complete"
}
```

### link

Link task(s) to an existing requirement. Deduplicates automatically.

```bash
python3 pending.py link <id> --task-id <uuid> --task-name "任务名称"
```

**Output format:**

```json
{
  "success": true,
  "id": "a3f7b2c1",
  "linked": "task-uuid"
}
```

### delete

Remove an item entirely (use sparingly — prefer `complete`).

```bash
python3 pending.py delete <id>
```

**Output format:**

```json
{
  "success": true,
  "id": "a3f7b2c1"
}
```

**Error format (all commands):**

```json
{
  "success": false,
  "error": "Item not found: xxx"
}
```

## Injection Rules (for PendingTrackerProcessor)

When injecting into Manager context:

- Only show items with status `pend`, `running`, `hold`
- Keep last 5 `complete` items for reference
- Add stale indicator for items where `updated_at` > 3 days ago
- Show linked task count per item

## Best Practices

1. **One requirement = one user-visible outcome**. Don't create pending items for internal steps.
2. **Link tasks as you create them**. When dispatching a task for a requirement, immediately link it.
3. **Review on completion**. When a task completes, check if the linked requirement can be closed.
4. **Keep notes actionable**. "等前端同步后一起提 PR" is good. "WIP" is not.
5. **Don't duplicate task status**. The tracker tracks _requirements_, not tasks. If you just need to know a task's status, look at Sub-Tasks Status.
