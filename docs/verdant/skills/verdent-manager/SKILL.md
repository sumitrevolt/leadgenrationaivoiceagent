---
name: verdent-manager
description: |
  Manage tasks, messages, workspaces, projects, models, slash commands, SSH,
  UI actions, and remote operations through the verdent-manager CLI —
  orchestration, message-driven execution, worktree/workspace setup, command
  catalog management, and remote project creation via SSH.
metadata:
  version: '1.3.2'
---

# Verdent Manager

Unified skill for Verdent's IPC-backed `verdent-manager` CLI.

## When to Use

- Create/query/stop/delete tasks, fetch recent tasks, and track child task progress
- Create tasks with a required initial prompt, send follow-up messages, send control messages (plan approval, clarification answers, confirmations), and inspect message history (with server-side filtering)
- Create worktrees/workspaces and check workspace stats
- List/add local and cloud projects, and remove local projects, with explicit project source selection
- List available models
- Manage slash commands (list/create/update/delete)
- SSH remote operations: list configured hosts, test connections, browse remote directories, create remote projects
- UI actions: show manager cards and update personalization

## Scope

- If a skill mention includes `[scope=worker]`, delegate the skill to a worker task.
- Do NOT expose the `[scope=worker]` tag itself to the worker or to the user in any manner.

## Command Map

Use only the resource/action names shown here and in CLI help.

| Need | Use |
| --- | --- |
| Create a task | `task create` |
| Get task details or status | `task get` |
| Stop a task | `task stop` |
| Delete a task | `task delete` |
| Fetch recent tasks or task history | `task recent` |
| Fetch child tasks | `task children` |
| Send a follow-up task message | `message send` |
| Steer the current local running turn | `message steer` |
| Approve plans or answer pending controls | `message control` |
| Inspect task messages | `message list` |
| Inspect projects | `project list` |
| Add a local or Cloud project | `project add` |
| Remove a local project | `project remove` |

## Core Concepts

### Task Modes

- **Normal mode** (default): the worker starts executing immediately after task creation or after receiving a follow-up message.
- In normal mode, the worker does the work directly and reports back through task notifications when it finishes or reaches another terminal state.
- **Plan mode**: the worker first prepares a plan instead of executing immediately.
- After the worker submits the plan, the task enters `pending` and waits for manager approval.
- The manager approves the plan with `verdent-manager message control --action-type submit_plan`.
- Use `--data '{}'` to approve the plan as-is.
- Use `--data '{"content":"..."}'` to approve with an edited plan.
- After approval, the worker begins execution and later reports completion through task notifications.
- Plan mode is useful for complex tasks where you want to review direction first, or for multi-step work that should be approved before execution starts.

### Pending-State Control Actions

- `submit_plan`: approve a plan-mode proposal and let the worker proceed, optionally with edited plan content.
- `submit_clarify`: answer a clarification request raised by the worker, such as a selection or form response.
- `skip_clarify`: skip a clarification request and let the worker make its own best judgment.
- `submit_code_review`: respond to a worker's code review request so it can continue with the requested feedback.

### Message Send vs Steer

- Use `message steer` only for a local task that is currently running in normal mode when the user wants immediate guidance, correction, or scope narrowing for the in-progress turn.
- Use `message send` for Cloud tasks, idle/pending tasks, plan/longrun follow-up, or new follow-up requests.

### Project Source Rules

- `project add` is the origin decision point. Pass `--source local|cloud` explicitly.
- `project list` returns local projects and includes Cloud projects when the runtime has Cloud access.
- Use Cloud for Preview, Publish, Analytics, public URL, online access, deployment, or share-link work.
- Use Local for local files, local exports, local-only analysis, or SSH remote projects.
- After a project/task exists, keep using the legacy arguments; supported commands resolve local/cloud from project identity or taskId automatically.
- Do not add `--source` to task/message commands unless you are intentionally debugging or overriding routing.
- Cloud-compatible task commands are `task create`, `task get`, `task stop`, `task delete`, `task recent`, and `task children`.
- Cloud-compatible message commands are `message send`, `message list`, and `message control`.
- `message steer` is local-only active-turn steering. Do not use it for Cloud tasks.
- `--type local|remote` is only for local-source local/SSH execution. Cloud is never `--type remote`.

## CLI Shape

```bash
verdent-manager <resource> <action> [flags]
```

```text
verdent-manager — Manage tasks, messages, workspaces, projects, models, slash commands, SSH, and UI actions

Usage:
  verdent-manager <resource> <action> [flags]

Resources:
  task       Task lifecycle management
  message    Task messaging and pending-state control
  workspace  Worktree/workspace management
  project    Project management
  model      Model discovery
  command    Slash command management
  ssh        SSH remote operations
  ui         Manager UI actions
```

### task

```text
verdent-manager task — Task lifecycle management

Subcommands:
  create    --name <name> (--prompt <text> | --prompt-file <path>) [--pending-id <id>]
            (--project-id <id> | --project-path <path>)
            [--workspace-id <id>] [--worktree-path <path>]
            [--orchestrator-session-id <id>]
            [--mode normal|plan|longrun] [--model <key>]
            [--think-level <n>]
            Project identity resolves local/cloud automatically. Use the legacy task create shape after project add.
            Cloud workspaceId is resolved from project data when omitted.
            Cloud tasks support the same task id based get/stop/delete/children commands where available.
            Cloud rejects local-only options: --pending-id, --worktree-path, --mode longrun.
            Use --prompt-file for long prompts.

  get       --task-id <id>
            TaskId resolves local/cloud automatically and can fetch supported Cloud tasks.

  stop      --task-id <id>
            TaskId resolves local/cloud automatically and can stop supported Cloud tasks.

  delete    --task-id <id>
            TaskId resolves local/cloud automatically and can delete supported Cloud tasks.

  recent    [--since-ms <epoch_ms>] [--limit <n>] [--min-count <n>]
            Fetches recent local tasks and includes Cloud tasks when the runtime has Cloud access.

  children  --task-id <parent-task-id>
            Parent taskId resolves local/cloud automatically and can list supported Cloud child tasks.
```

### message

```text
verdent-manager message — Task messaging and pending-state control

Subcommands:
  send     --task-id <id> (--message <text> | --message-file <path>)
           [--mode normal|plan|manager|longrun] [--model <key>]
           [--think-level <n>]
           TaskId resolves local/cloud automatically and can send to supported Cloud tasks.
           --mode manager, --mode longrun, and LongRun metadata are local-source features.
           Use --message-file for multi-line or long messages so the shell cannot split or reinterpret the payload.
           If the task is running, message send queues for later and does not steer the current turn; use message steer for active-turn guidance.

  steer    --task-id <id> (--message <text> | --message-file <path>)
           Local-only. Guides the current active normal-mode running turn.
           Do not use for Cloud tasks; it does not auto-route by taskId.

  control  --task-id <id> --action-type <type> [--data <json>]

           <type> and --data:
             submit_plan        {"content":"<edited plan>"} or {}
             submit_clarify     {"result":[{"type":"select","text":"option A"},{"type":"mult","text":["option B","option C"]},{"type":"form","text":"extra details"}]}
             skip_clarify       {}
             submit_code_review {"content":"<review response>"}

           Notes:
             The latest pending interactive tool for the task is selected automatically.
             --data is the action input JSON only, not the full control body.
             TaskId resolves local/cloud automatically and can control supported Cloud pending states.

  list     --task-id <id>
           [--limit <n>] [--before <msgId>] [--after <msgId>]
           [--source user|agent|status|control]
           [--order asc|desc]
           [--body-type <type>] [--content-type <type>] [--min-length <n>]
           `--source user|agent|status|control` keeps the legacy message-source filter.
           This command lists messages for a task, not task history.
           TaskId resolves local/cloud automatically and can list supported Cloud task messages.
```

### workspace

```text
verdent-manager workspace — Worktree/workspace management

Subcommands:
  create  --name <name> (--project-id <id> | --project-path <path>) --base-branch <branch>
          Create a workspace/worktree

  stats   --workspace-id <id>
          Get workspace stats

  list    (--project-id <id> | --project-path <path>)
          List workspaces for a project
```

### project

```text
verdent-manager project — Project management

Subcommands:
  list
          Lists local projects and includes Cloud projects when the runtime has Cloud access.
          Remote SSH projects are still local-source projects with type remote.

  add     [--source local|cloud] [--path <path>] --name <name>
          [--type local|remote]
          [--ssh-host <host>] [--ssh-hostname <host>] [--ssh-user <user>]
          [--ssh-port <port>] [--ssh-identity-file <file>]
          Pass --source local|cloud explicitly for new work; omitted source is local only for legacy compatibility.
          --path is required for local source. For cloud source, --path is optional; when omitted, the cloud runtime chooses its default project directory.
          --type only applies to local source and describes local vs SSH remote execution/connection.

  remove  --project-id <id> | --project-path <path>
          Remove a local project
```

### model

```text
verdent-manager model — Model discovery

Subcommands:
  list
        List available models
```

### command

```text
verdent-manager command — Slash command management

Subcommands:
  list    [--project-path <path>] [--query <text>]
          List slash commands

  create  --name <name> --content <text> [--description <text>]
          Create a slash command

  update  --original-name <name>
          [--name <name>] [--content <text>] [--description <text>]
          Update a slash command

  delete  --name <name>
          Delete a slash command
```

### ssh

```text
verdent-manager ssh — SSH remote operations

Subcommands:
  list-hosts
                       List hosts from ~/.ssh/config

  test-connection      (--host <host> | --hostname <host>)
                       [--user <user>] [--port <port>] [--identity-file <file>]
                       Test SSH connectivity

  create-client        (--host <host> | --hostname <host>)
                       [--user <user>] [--port <port>] [--identity-file <file>]
                       Create a persistent SSH client session

  list-directories     --client-id <id> [--path <path>]
                       List directories on remote host

  get-home-directory   --client-id <id>
                       Get remote home directory

  release-client       --client-id <id>
                       Release a persistent SSH client

  release-all-clients
                       Release all SSH clients
```

### ui

```text
verdent-manager ui — Manager UI actions

Subcommands:
  show-card               --type memory-onboarding|prompt-recommendation [--payload <json>]
                          Show a manager UI card

  update-personalization  [--role-name <name>]
                          [--avatar green|blue|purple|red|yellow|custom]
                          [--avatar-url <url> | --avatar-file <file>]
                          Update manager role name and/or avatar
```

## Examples

### Example 1: Plan 模式完整流程

```bash
# 1. 创建 plan 模式任务
verdent-manager task create --name "重构认证模块" \
  --prompt "将 OAuth 改为 OIDC，保持 API 兼容" \
  --mode plan --project-path /path/to/project

# 2. worker 提交方案后任务进 pending，等审批
# 3. 查看 worker 的方案
verdent-manager message list --task-id <id> --source agent --limit 1

# 4. 审批方案（原样通过）
verdent-manager message control --task-id <id> --action-type submit_plan --data '{}'

# 或修改方案后通过
verdent-manager message control --task-id <id> --action-type submit_plan \
  --data '{"content":"只改 auth 层，不动 session 管理"}'

# 5. worker 开始执行，完成后通过 task notification 回报
```

### Example 2: Cloud Preview / Publish / Analytics

```bash
# 用户需要在线预览、发布 URL、Analytics，先创建或选择 Cloud 项目
verdent-manager project add --source cloud --name "招生网站"

# Task create keeps the legacy shape; projectId routes to Cloud and workspaceId is resolved when possible
verdent-manager task create --project-id <cloud-project-id> \
  --name "招生网站" \
  --prompt "基于招生资料做一个网站，打开 Cloud Preview，发布线上 URL，并接入 Analytics。"

# Cloud follow-up, list, and control auto-resolve origin by taskId
verdent-manager message send --task-id <cloud-task-id> --message "继续检查发布结果"
verdent-manager message list --task-id <cloud-task-id> --limit 20
verdent-manager message control --task-id <cloud-task-id> --action-type submit_plan --data '{}'
```

### Example 3: Normal local 模式 + 后续消息

```bash
# 创建任务
verdent-manager task create --name "修复登录bug" \
  --prompt "修复 #123 登录超时问题" \
  --project-path /path/to/project

# 任务运行中发现需要补充信息，发送后续消息
verdent-manager message send --task-id <id> --message "补充：只在 Safari 上复现"
```

### Example 4: 响应 worker 澄清

```bash
# worker 提了选择题，选第一个选项
verdent-manager message control --task-id <id> --action-type submit_clarify \
  --data '{"result":[{"type":"select","text":"option A"}]}'

# 跳过澄清，让 worker 自己判断
verdent-manager message control --task-id <id> --action-type skip_clarify --data '{}'
```

### Notes

```text
Output:
  Commands return JSON on stdout.
  Help/usage text is emitted on stdout by the desktop app.
  Errors are emitted on stderr by the desktop app.
Plan Mode:
  --mode plan can be used with task create and message send.
  In plan mode, tasks remain pending until a plan is approved.
Thinking:
  --think-level <n> controls worker reasoning depth and is optional.
Prerequisites:
  Verdent application must be running
  verdent-manager must be available in PATH
Cloud:
  Cloud task create requires --project-id and a Manager parent session.
  When --workspace-id is omitted, the CLI resolves the Cloud base workspace from project data.
  Pass --workspace-id only to select a specific workspace.
  The agent bash tool usually forwards VERDENT_SESSION_ID automatically; external callers can pass --orchestrator-session-id.
  Cloud completion, pending, and error notifications return to Manager through Cloud events.
```
