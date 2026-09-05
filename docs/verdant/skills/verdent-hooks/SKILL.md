---
name: verdent-hooks
description: 'Manage Verdent hooks (PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, SessionEnd). List, add, remove, enable/disable hooks in ~/.verdent/hooks.json. Changes take effect on the next turn.'
user-invocable: true
metadata:
  version: '1.0.4'
---

# Verdent Hooks Management

Manage hook configurations that intercept agent lifecycle events. Hooks are defined in JSON config files and executed automatically by the hook engine.

## Config File Locations

| Scope   | Path                                    | Priority               |
| ------- | --------------------------------------- | ---------------------- |
| Global  | `~/.verdent/hooks.json`                 | Lower                  |
| Project | `.verdent/hooks.json` (relative to cwd) | Higher (merged on top) |

Use `file_read` to inspect and `file_write` to update. Changes take effect on the **next turn** (no restart needed).

## Operations

### List hooks

Read the hooks.json file(s) and display all configured hooks grouped by event type.

### Add a hook

Read the current hooks.json, append a new entry to the target event array, write back.

### Remove a hook

Read the current hooks.json, remove the entry by index or matcher, write back.

### Enable / Disable a hook

Read the current hooks.json, toggle the `enabled` field on the target entry, write back.

## Hook Events

| Event              | When                        | Capabilities                                   |
| ------------------ | --------------------------- | ---------------------------------------------- |
| `UserPromptSubmit` | Each turn, after user input | Inject context into prompt, block input        |
| `PreToolUse`       | Before each tool call       | Validate, block, or modify tool arguments      |
| `PostToolUse`      | After each tool call        | Append info to tool result, patch return value |
| `SessionStart`     | New session created         | Run initialization commands                    |
| `SessionEnd`       | Each turn completes         | Trigger next turn (return query string)        |

## hooks.json Format

Use the **simplified format** (recommended). The engine auto-normalizes it.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "command": "python ~/.verdent/hooks/scripts/validate.py",
        "matcher": "file_write|file_edit",
        "description": "Validate file writes before execution",
        "enabled": true,
        "timeout": 10
      }
    ],
    "UserPromptSubmit": [
      {
        "command": "echo '{\"hookSpecificOutput\":{\"additionalContext\":\"Remember: update deps.json when task status changes.\"}}'",
        "description": "Inject deps reminder each turn",
        "mode": "manager",
        "enabled": true,
        "timeout": 5
      }
    ]
  }
}
```

**Standard format** (also supported):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "file_write|file_edit",
        "hooks": [
          {
            "type": "command",
            "command": "python ~/.verdent/hooks/scripts/validate.py",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

### Field Reference

| Field         | Required                | Description                                                                                      |
| ------------- | ----------------------- | ------------------------------------------------------------------------------------------------ |
| `command`     | Yes (for command hooks) | Shell command to execute                                                                         |
| `matcher`     | No                      | Tool name filter for PreToolUse/PostToolUse. Supports exact match, `*` glob, `\|` separated list |
| `description` | No                      | Human-readable note (stripped during normalization)                                              |
| `enabled`     | No                      | Set `false` to skip without removing. Default: `true`                                            |
| `mode`        | No                      | Restrict hook to a specific session mode: `manager` or `normal`. Omit to run in all modes        |
| `timeout`     | No                      | Max seconds. Default: 30                                                                         |

## Hook Script Protocol

Scripts receive context via **stdin** as JSON:

```json
{
  "hook_event_name": "PreToolUse",
  "session_id": "...",
  "cwd": "/path/to/project",
  "tool_name": "file_write",
  "tool_input": { "file_path": "...", "content": "..." }
}
```

Fields vary by event:

- `UserPromptSubmit`: `prompt`
- `PreToolUse`: `tool_name`, `tool_input`
- `PostToolUse`: `tool_name`, `tool_input`, `tool_response`
- `SessionStart`: `source`
- `SessionEnd`: `reason`

### Response Protocol (stdout JSON)

| Action                               | Output                                                                      |
| ------------------------------------ | --------------------------------------------------------------------------- |
| Allow (default)                      | `{"decision": "allow"}` or exit code 0 with no output                       |
| Block                                | `{"decision": "block"}` or exit code 2                                      |
| Inject context                       | `{"hookSpecificOutput": {"additionalContext": "text to inject"}}`           |
| Modify tool args (PreToolUse only)   | `{"hookSpecificOutput": {"modifiedToolInput": {"file_path": "/new/path"}}}` |
| Patch tool result (PostToolUse only) | `{"tool_result_patch": {"key": "value"}}`                                   |

## Examples

### Add a PreToolUse validation hook

```
1. file_read ~/.verdent/hooks.json (or create empty {"hooks": {}} if not exists)
2. Add to hooks.PreToolUse array:
   {
     "command": "python ~/.verdent/hooks/scripts/my_validator.py",
     "matcher": "bash",
     "description": "Review bash commands before execution",
     "enabled": true,
     "timeout": 10
   }
3. file_write ~/.verdent/hooks.json with updated content
```

### Add a UserPromptSubmit context injection

```
1. file_read ~/.verdent/hooks.json
2. Add to hooks.UserPromptSubmit array:
   {
     "command": "cat \"$VERDENT_HOME/memories/notification.md\"",
     "description": "Inject notification reminders",
     "enabled": true,
     "timeout": 5
   }
3. file_write ~/.verdent/hooks.json with updated content
```

### Disable a hook without removing it

```
1. file_read ~/.verdent/hooks.json
2. Set enabled: false on the target entry
3. file_write ~/.verdent/hooks.json
```
