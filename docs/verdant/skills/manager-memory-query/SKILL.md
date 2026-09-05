---
name: manager-memory-query
description: |
  Memory Query Skill for Manager to asynchronously query historical memory files.
  Enables reading manager-lessons.md, mistakes.md, task-complexity-signals.md, and daily logs
  to provide context-aware decision making. Used by creating short-lived Memory Query Tasks.
metadata:
  version: '1.0.4'
---

# Manager Memory Query Skill

This skill enables the Manager to query historical memory files through short-lived Memory Query Tasks using **Agentic exploration**. The Memory Query Task autonomously explores the memory file tree using tools like `file_read`, `glob`, and `grep_content` to extract relevant context.

## When to Use

- Manager receives a new user task and needs to recall relevant past lessons
- Checking for similar mistakes that should be avoided
- Looking up project-specific context from previous tasks
- Finding complexity signals that match the current task
- Quick memory lookups without blocking the main Manager session

---

## Memory File Tree

The skill queries files under `./memories/` in the current manager workspace. For shell commands, this workspace resolves to `$VERDENT_HOME`.

```
memories/
├── manager-lessons.md                   - Manager cross-project lessons & best practices (130 lines)
├── mistakes.md                          - Error log & avoidance guide (74 lines)
├── task-complexity-signals.md           - Task complexity judgment signal library (44 lines)
├── task-dependency-orchestration.md     - Cross-task dependency orchestration workflow specification (58 lines)
├── project-relations.json               - Inter-project dependency & relationship mapping
├── custom_loops.json                    - Custom loop configuration (empty array)
├── todos.md                             - Global TODO list (empty file)
├── daily/                               - Daily work summaries (by date YYYY-MM-DD)
│   ├── 2026-03-16.md                   - Example: verdent-agent hallucination tool fallback implementation
│   └── ...                             - (Currently only 1 log file)
└── task-workflows/                      - Cross-task dependency orchestration workspace
    ├── active/                          - Active dependency flows (empty directory)
    └── archived/                        - Archived dependency flows (empty directory)
```

### File Details

| File                                 | Purpose                                      | Content Pattern                                                                    |
| ------------------------------------ | -------------------------------------------- | ---------------------------------------------------------------------------------- |
| **manager-lessons.md**               | Cross-project lessons & best practices       | Task scenarios, error → correct approach, application context                      |
| **mistakes.md**                      | Technical decision errors & debug failures   | Date-stamped records: scenario → mistake → consequence → correct approach → lesson |
| **task-complexity-signals.md**       | Task complexity judgment signals             | Strong signals (any 1 triggers) + Weak signals (2+ needed)                         |
| **task-dependency-orchestration.md** | Cross-task dependency orchestration workflow | Requirement decomposition, dependency file format, orchestration rules             |
| **project-relations.json**           | Project relationship mapping                 | Clone variants, frontend-backend pairs, project metadata                           |
| **daily/**                           | Daily work summaries (YYYY-MM-DD)            | Time-stamped sections, commit hashes, project interaction records                  |

**Priority Search Order:**

1. Core experience library: `manager-lessons.md`, `mistakes.md`
2. Decision & judgment: `task-complexity-signals.md`, `task-dependency-orchestration.md`
3. Metadata & history: `project-relations.json`, `daily/` (recent 7-14 days)

---

## Query Guidance

### Agentic Exploration Strategy

The Memory Query Task uses an **iterative exploration approach** with the following tools:

| Tool           | Use Case                         | Example                                                                                       |
| -------------- | -------------------------------- | --------------------------------------------------------------------------------------------- |
| `glob`         | Find files by pattern            | `glob(pattern="**/*.md", dir_path="./memories/")`                          |
| `grep_content` | Search file content for keywords | `grep_content(regex="coordinate", search_path="./memories/mistakes.md")`   |
| `file_read`    | Read specific file sections      | `file_read(file_path="./memories/manager-lessons.md", offset=1, limit=50)` |

### Exploration Phases

#### Phase 1: Quick Keyword Search

1. Extract keywords from user message (tech stack, problem type, project names)
2. Priority search:
   - P0: Core experience library (`manager-lessons.md`, `mistakes.md`)
   - P1: Decision files (`task-complexity-signals.md`)
   - P2: Metadata (`project-relations.json`, `daily/`)
3. Use synonyms and variations (e.g., "task decomposition" → also search "dependency orchestration", "step-by-step planning")

#### Phase 2: Iterative Deep Dive

- Follow clues from Phase 1 results
- Read related sections in discovered files
- Cross-reference between files (e.g., mistake → related lesson)

**Example flow:**

```
User query: "How to fix Playwright Canvas click not working?"

Step 1: grep_content(regex="Playwright.*Canvas", search_path="mistakes.md")
→ Found: Line 3-11 (invested in solution research without verifying assumptions)

Step 2: file_read(file_path="mistakes.md", offset=3, limit=15)
→ Extract: Coordinate system issue (locator.click vs mouse.click)

Step 3: grep_content(regex="PVZ|game", search_path="manager-lessons.md")
→ Found: PVZ game verification task lesson (prioritize root cause analysis)

Step 4: file_read(file_path="manager-lessons.md", offset=3, limit=30)

→ Output structured JSON
```

#### Phase 3: Daily History Lookup

For queries about "what was done recently" or "how was it done last time":

1. `glob(pattern="*.md", dir_path="./memories/daily/")`
2. Focus on recent 3-7 days
3. `grep_content` for project names or features
4. Extract commit hashes + summaries

### Best Practices

**DO:**

- Use `grep_content` first for fast keyword location
- Use `file_read` with `offset`/`limit` for targeted reading
- Follow clues iteratively (read A → discover reference to B → read B)
- Search synonyms and variations
- Limit `daily/` searches to recent 7-14 days

**DON'T:**

- Read entire files blindly (except small files < 100 lines like `project-relations.json`)
- Stop at the first match — explore alternative implementations
- Guess content — output empty arrays if no results found

---

## Output Format

The Memory Query Task writes structured JSON to:

```
~/.verdent/artifacts/memory-query/{session_id}/result.json
```

**JSON Schema:**

```json
{
  "query_summary": "Brief description of query intent (1-2 sentences)",
  "relevant_lessons": [
    {
      "source": "manager-lessons.md",
      "title": "Lesson title",
      "content": "Core lesson content (100-200 words)",
      "relevance": "Explanation of relevance to current task"
    }
  ],
  "mistakes_to_avoid": [
    {
      "source": "mistakes.md",
      "scenario": "Scenario description",
      "mistake": "Wrong approach",
      "correct_approach": "Correct approach",
      "lesson": "Lesson summary"
    }
  ],
  "complexity_signals": [
    {
      "signal_type": "Strong signal | Weak signal",
      "description": "Signal description",
      "triggered": true | false
    }
  ],
  "project_context": {
    "related_projects": ["project1", "project2"],
    "relationships": "Description of inter-project relationships (e.g., frontend-backend, clone variant)",
    "notes": "Additional notes"
  },
  "daily_history": [
    {
      "date": "YYYY-MM-DD",
      "summary": "Daily work summary",
      "commits": ["commit_hash: brief description"]
    }
  ],
  "search_trace": [
    "Executed search steps (for debugging)",
    "Step 1: grep_content 'keyword' in mistakes.md",
    "Step 2: file_read manager-lessons.md offset=10 limit=30"
  ]
}
```

### Output Requirements

1. **Precision**: Only output content directly relevant to the user message
2. **Source Citation**: Every item must include `source` field (file name + optional line range)
3. **Empty Handling**: Use empty arrays `[]` or objects `{}` for missing data (never `null`)
4. **search_trace**: REQUIRED field for debugging and optimization
5. **Conciseness**: Each field should be 100-200 chars (unless essential details require more)

---

## Result Injection Mechanism

1. Memory Query Task completes → writes result to `~/.verdent/artifacts/memory-query/{session_id}/result.json`
2. **Next LLM call** → `before_model_hook` checks for file existence
3. File exists → read JSON → format as `<system-notification>` → inject into LLM request → delete file
4. File not found → skip injection

This ensures Memory Query results are immediately available in the next turn without session state dependency.

---

## Usage Example

### Manager Creates Memory Query Task

```python
from scripts.task_client import TaskClient

client = TaskClient()

# Create Memory Query Task
result = client.create_task(
    name="Memory Query: OAuth2 Implementation",
    project_path="/Users/zhangyu.95/.verdent/workspace",
    parent_task_id="manager-session-id"
)
task_id = result["taskId"]

# Send query message (triggers Agentic exploration)
query_input = {
    "user_message": "Implement OAuth2 authentication flow",
    "query_scope": "all"
}

client.send_message(
    task_id,
    f"Query memory: {json.dumps(query_input)}",
    parent_task_id="manager-session-id"
)

# Wait for completion (2-5 seconds typical)
time.sleep(3)

# Results automatically injected into next LLM call via before_model_hook
```

---

## Performance Targets

- **Quick keyword search**: < 2 seconds
- **Full context query**: < 5 seconds
- **Daily history lookup**: < 3 seconds (recent 7-14 days)
- **Task lifecycle**: Short-lived (auto-complete after writing result JSON)

---

## Error Handling

### File Not Found

```json
{
  "error": "File does not exist",
  "file_path": "./memories/xxx.md",
  "suggestion": "Check if file path is correct, or if the file has been moved/deleted"
}
```

### No Search Results

```json
{
  "query_summary": "No relevant content found",
  "search_trace": ["Step 1: grep_content 'keyword' → 0 results", "Step 2: ..."],
  "suggestion": "Try more general keywords, or check if user message is outside memory coverage scope"
}
```

---

## Prerequisites

- Memory files exist at `./memories/`
- Manager has permissions to read memory files
- Verdant Task Manager is running (for task creation)

---

## Resources

- **Memory file tree**: See above for structure and file purposes
- **Query guidance**: Agentic exploration strategy with tool usage patterns
- **Result injection**: Automated via `before_model_hook` for seamless context injection
