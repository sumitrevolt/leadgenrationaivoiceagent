# Memory Query Rules

> Framework-managed file. Level 1: conservative — only explicit references trigger.

## Internal Terminology Prohibition

Never mention trigger levels, strategy names, or internal decision process in user-facing replies. Execute the correct strategy silently.

## When to Trigger

- User explicitly references past work ("the X we discussed before", "last time's approach") → always trigger.
- New topics without explicit reference → do NOT trigger.
- Direct follow-up to active conversation, small talk, or status queries → do NOT trigger.

## Async vs Blocking

- **Async** (default): send memory query task, continue responding with available context. Result injected on next turn.
- **Blocking**: only when user explicitly asks about past work and expects a detailed answer. Use sparingly.

## Read-Write Separation

Memory query tasks are **read-only**. They MUST NOT write to or modify memory/index files.
If a query discovers missing indexes, record to `memories/active/index-refresh-requests.json` for the cron task to handle.

## How to Create

1. Load `manager-memory-query` skill.
2. Create under the memory-query project (auto-discovered by the system, or locate via `project list`. If not exist, create it.).
3. Task uses `file_read` or `rg` through `bash` to explore memory files.
4. Result written to `~/.verdent/artifacts/memory-query/{session_id}/result.json`.
5. `before_model_hook` auto-injects result into next LLM call.

## Result Injection

Result file → `before_model_hook` checks existence → reads + formats as system-notification → injects → deletes file.
