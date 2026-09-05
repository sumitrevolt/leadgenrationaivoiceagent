---
name: edit-pulse-style
description: Generate or modify a taskflow.render.json for dashboards, trackers, reports, and data boards. Accepts a user prompt, produces a JSON spec from the component catalog, validates and writes via write-render script for auto-rendering. Supports add (full generation) and modify (incremental patch). Use this when the user asks to create, update, or visualize a board.
metadata:
  version: '0.0.10'
---

# Edit Pulse Style

`<SKILL_DIR>` refers to this skill's base directory, provided in the skill loading context.

Two modes: **add** (full generation) or **modify** (incremental patch on existing board).

```
Step 0: Choose Mode
Add:    Collect Data → Prep Prompt → Generate JSON → Validate & Write → Deliver
Modify: Read Current Envelope → Plan Patch → Apply & Validate → Deliver
```

## Constraints

These are non-negotiable. Violating any of them will produce a broken or invisible board.

- **NEVER write directly to the preview path.** Always go through `<SKILL_DIR>/scripts/write-render.mjs`.
- **NEVER output raw JSON to the user.** The deliverable is the rendered board.
- **NEVER manually read `prompt/system.txt` or `prompt/styles/*.txt` in add mode.** The prep-prompt script handles prompt assembly.
- **Output pure JSON only (add mode)** — no markdown fences, no explanatory text.
- **Do not write on failure** — if validation fails after one retry, report the error instead.
- **Use only `path.join(process.env.VERDENT_HOME, 'tmp', 'edit-pulse-style')` for intermediate files.** Never use root-level `/tmp` for bootstrap data or draft render files.
- **Never manually append `workspace/base` to workspace paths.** The final Pulse target is resolved only by `<SKILL_DIR>/scripts/write-render.mjs`.

## Guidance

Soft preferences. Follow unless the user's request conflicts.

- Style is a design tendency, not a rigid template. Prioritize the style's information density and structural direction.
- UI copy language follows the user's contextual language, not a fixed language.
- Topology uses `Topology` as a container with `Card` child nodes. Dependencies go in `Topology.props.edges`.
- Callout with `info` or `warning` variant should be the **first child** of the board root.

---

## Step 0: Choose Mode

Choose the mode before any data collection, prompt preparation, or JSON editing. Execute exactly one branch.

`VERDENT_HOME` is already the manager workspace root. Never append `workspace/base`. The final render target is resolved only by `<SKILL_DIR>/scripts/write-render.mjs`.

Use Node `path.join` for all temporary files:

- `tempDir = path.join(process.env.VERDENT_HOME, 'tmp', 'edit-pulse-style')`
- `dataFile = path.join(tempDir, 'kanban-data.json')`
- `draftFile = path.join(tempDir, 'taskflow-render-draft.json')`

This keeps the same logical paths: `<VERDENT_HOME>/tmp/edit-pulse-style/kanban-data.json` and `<VERDENT_HOME>/tmp/edit-pulse-style/taskflow-render-draft.json`.
When executing commands, replace `dataFile` and `draftFile` with the concrete absolute paths computed from these expressions.
Create `tempDir` before writing `dataFile` or `draftFile`.

| Condition | Mode |
|-----------|------|
| Current render exists and has valid `spec.elements`, and the user asks to tweak / update / add / remove / move / restyle the existing board | **modify** |
| No current render, or current render is empty / `{}` / invalid | **add** |
| User says "regenerate" / "start fresh" | **add** (forced) |
| User says "tweak" / "move to top" / "add a card" and current render exists with valid `spec.elements` | **modify** |

If ambiguous, prefer **modify** only when a valid current render exists and the user refers to the current board ("this board", "it", "current view", "add a card"). Prefer **add** when the user describes a new board from scratch. If the user requests a modification but no valid current render exists, do not invent one as modify; either create a new board when the request can stand alone, or report that there is no current board to modify.

---

## Add Mode

### Step A1: Collect Data

1. **Pick a style** from `<SKILL_DIR>/prompt/styles/` based on user intent. Use `default` when unsure.

2. **Collect bootstrap data** (skip if the board is purely from user description):
   - Tasks/projects → collect via JSON CLI, write to `dataFile`.
     - Prefer `verdent-manager task list --output json` for task/session rows.
     - Use `verdent-manager project list --output json` when project navigation or project grouping is needed.
     - Preserve real identifier fields from the CLI output (`sessionId`, task/session `id`, `projectName`, `name`) so generated `Tag.props.script` values can reference real targets.
   - Files → read files + include source path metadata for subscription generation
   - Static content → skip

3. **Get managerSessionId** from the current session context.

### Step A2: Prep Prompt

```text
node <SKILL_DIR>/scripts/prep-prompt.mjs --style "<style>" --user-prompt "<user request>" --data-file "<dataFile>" --session-id "<managerSessionId>" --lang "<locale>"
```

Omit `--data-file` if no data. Omit `--lang` to fall back to the user's language.

Returns `{"ok":true, "systemPrompt":"...", "userPrompt":"..."}`.

### Step A3: Generate & Validate

1. Use `systemPrompt` as generation guidelines, `userPrompt` as the request. Generate the full JSON envelope — including the `subscriptions` array. Follow the **Runtime Dependency Rule** in the system prompt to decide whether subscriptions should be non-empty or `[]`.
2. Write to `draftFile`.
3. Validate and write:

```text
node <SKILL_DIR>/scripts/write-render.mjs "<draftFile>"
```

- `{"ok":true}` → done, go to Deliver.
- `{"ok":false,"errors":[...]}` → fix and retry **once**.

---

## Modify Mode

### Step M1: Read Current Envelope

Read the current render envelope from `./preview/taskflow.render.json` in the current manager workspace. Understand the `spec.elements` tree and `spec.root`.

Use the current `render.json` as the full render envelope. If it contains `subscriptions`, keep them unchanged unless the user's requested modification explicitly changes the runtime data source.

When adding a new component type not already in the current spec, read `<SKILL_DIR>/prompt/component-catalog.txt` to look up valid props and usage rules.

### Step M2: Plan Patch

Express changes as RFC 6902 operations. This is a structured plan — you apply it by editing the JSON in M3.

**Common operations** (cover most cases):

| Intent | Patch |
|--------|-------|
| Reorder / move element | `replace` parent's `/spec/elements/<parentId>/children` with new order |
| Change a prop | `replace` on `/spec/elements/<id>/props/<prop>` |
| Add element | `add` definition at `/spec/elements/<newId>` + insert into parent's `children` |
| Remove element | `remove` from parent's `children` + `remove` at `/spec/elements/<id>` |

### Path Reference

All valid patch paths (relative to envelope root):
- `/spec/elements/<id>/props/<prop>` — component property
- `/spec/elements/<id>/children` — children array (replace for reorder)
- `/spec/elements/<id>/children/<index>` — insert at position
- `/spec/elements/<newId>` — new element definition
- `/spec/elements/<id>` — remove element
- `/subscriptions` — preserve existing entries by default; replace only when the runtime data-source declaration intentionally changes
- `/spec/root` — root element (rare)

### Patch Rules

- Reorder → replace entire `children` array, not individual indices.
- Add → always define in `/spec/elements/` AND insert into parent's `children`.
- Remove → always remove from parent's `children` AND from `/spec/elements/`.
- Keep patches minimal — only what the user requested.

### Step M3: Apply & Validate

1. Edit the render.json content based on the planned patches. Output the full render envelope, including the existing `subscriptions` array when present. Do not drop, empty, or rewrite `subscriptions` during layout/content-only edits.
2. Write to `draftFile`.
3. Validate and write:

```text
node <SKILL_DIR>/scripts/write-render.mjs "<draftFile>"
```

- `{"ok":true}` → done, go to Deliver.
- `{"ok":false,"errors":[...]}` → fix and retry **once**.

---

## Deliver

Applies to both modes.

1. Tell the user the board has been generated/updated. Frontend auto-refreshes.
2. Remind them they can request further adjustments directly — no need to re-describe the board.
