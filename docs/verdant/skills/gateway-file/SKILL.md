---
name: gateway-file
description: |
  Access Feishu documents/wiki links and Feishu/Slack/Telegram files, images, videos, and attachments through a configured gateway channel: read, list, create, fetch, summarize, extract, or send. Use before asking the user to paste Feishu content when web access fails.
metadata:
  version: '1.2.3'
---

# Gateway File

## When to Use

Use this skill when the task needs gateway-backed file or Feishu document access:

- read, list, create, fetch, summarize, or extract Feishu docs, wiki pages, links, reports, or files
- recover from Feishu web failures caused by login, permission, private access, or missing content
- try the gateway document API before asking the user to paste Feishu content
- send or return a local file, screenshot, image, video, or report through a gateway channel
- perform an explicit gateway command after the user clearly asks for that command

Triggers: Feishu + doc/wiki/link/report/content + read/fetch/open/find/summarize/extract/access/connect.

## When NOT to Use

- Sending text-only messages (without any attachment) — use the `gateway-msg` skill instead.
- Normal conversation, including ordinary inbound gateway replies.
- Any turn where the assistant can answer directly in chat without Feishu document, wiki, file, or attachment access.
- Casual mention of Slack / Telegram without an explicit file/media request.
- Casual mention of Feishu that does not require document, wiki, file, or attachment access.
- Vague requests like "reply there", "send it", or "post this" without a trustworthy target.
- No trustworthy target ID or saved target name.
- Unclear user intent: ask first.

If the user is only chatting, explaining, summarizing, or answering a question without needing gateway-backed content, do not use this skill.

## Target Source

Prefer targets in this order:

- `--handle '<json>'` when replying to the same inbound gateway conversation
- `--channel <type> --target <id>` when the user gives an exact target ID
- `--channel <type> --name '<display-name>'` when the target already exists in `~/.verdent/gateway.json`

If not using `--handle`, extract the fields you need from the inbound handle:

- `--channel` ← `handle.channelType` (e.g. `"feishu"`)
- `--target` ← `handle.target.id` (e.g. `"oc_xxx"`)
- `--thread-id` ← `handle.target.threadId` (only if non-null)

Never guess a chat, thread, or user.

### Feishu `--target` rules

The gateway auto-detects `receive_id_type` from the ID prefix:

| Target type | `--target` format | Feishu `receive_id_type` |
| ----------- | ----------------- | ------------------------ |
| Group chat  | `oc_xxx`          | `chat_id`                |
| User (DM)   | `ou_xxx`          | `open_id`                |

Just pass the raw Feishu ID — no extra prefix needed.

## Basic Flow

For Feishu document access, use the document commands below before asking
the user to paste content manually.

For attachment delivery:

1. Confirm the user wants to send an attachment (file, image, video, etc.).
2. If this is a proactive send or cross-channel send, run `verdent-manager gateway list` first.
3. Confirm the channel is configured and connected.
4. Use one of the command templates below to send the attachment.
5. If you set a temporary status, clear it with `gateway status --message ""`.

## Command Templates

```bash
verdent-manager gateway list
```

```bash
verdent-manager gateway start --channel feishu
```

```bash
verdent-manager gateway stop --channel feishu
```

```bash
verdent-manager gateway restart --channel feishu
```

```bash
verdent-manager gateway send \
  --handle '<json>' \
  --file /path/to/report.pdf
```

```bash
verdent-manager gateway send \
  --channel feishu \
  --target oc_xxx \
  --file /path/to/report.pdf
```

```bash
verdent-manager gateway send \
  --channel feishu \
  --name "Project Group" \
  --file /path/to/video.mp4
```

```bash
verdent-manager gateway send \
  --channel feishu \
  --target oc_xxx \
  --message "Report attached." \
  --file /path/to/report.pdf
```

```bash
verdent-manager gateway status \
  --handle '<json>' \
  --message "Investigating"
```

```bash
verdent-manager gateway react \
  --handle '<json>' \
  --message-id "om_xxx" \
  --emoji "DONE"
```

```bash
verdent-manager gateway unreact \
  --handle '<json>' \
  --message-id "om_xxx" \
  --emoji "DONE"
```

## Query Templates

Use these only when the user explicitly asks to inspect channel data.

```bash
verdent-manager gateway list-chats [--channel feishu]
```

```bash
verdent-manager gateway search-chats --query "Project Group" [--channel feishu]
```

```bash
verdent-manager gateway get-messages --chat-id oc_xxx [--channel feishu]
```

```bash
verdent-manager gateway get-recent --chat-id oc_xxx --minutes 30 [--channel feishu]
```

```bash
verdent-manager gateway search-users --query "Alice" [--channel feishu]
```

## Feishu Document Operations (Feishu only)

The following commands interact with the Feishu document API. They are **not
available** on Slack or Telegram.

Use these commands before asking the user to paste Feishu document or wiki
content.

### List documents

```bash
verdent-manager gateway list-docs [--channel feishu] [--folder-token <token>]
```

### Read document content

```bash
verdent-manager gateway get-doc --doc-id <document_id> [--channel feishu]
```

`--doc-id` expects a Feishu document ID/token, not a raw URL. If the user gives a
Feishu doc/wiki URL, extract the document ID/token when it is clear; otherwise
use `list-docs` or ask for the document ID.

### Create a new document

```bash
verdent-manager gateway create-doc --title "Meeting Notes" [--channel feishu] [--folder-token <token>]
```

The response includes `documentId`, `title`, and `url` (a link to the new doc).

## Response Behavior

Your text output is **automatically forwarded** to the IM channel as the reply.
Do NOT add closing remarks like "Replied on Feishu", "Sent to Slack", "Message forwarded", or any
similar confirmation that you have replied to the channel — these would appear in
the IM conversation as redundant noise. Just provide the actual content the user
or the channel expects.

## Notes

- `send` requires at least one `--file` or `--message`. When sending attachments, `--message` is optional and serves as a caption.
- `send` accepts either `--handle` or `--channel` + `--target` / `--name`.
- `--file` is repeatable.
- **The filename passed to `--file` (basename only, excluding directory) must be 20 characters or fewer (including the extension).** If the original filename is too long, rename or copy it to a shorter name before passing it to `--file`.
- Prefer `--name` before asking for a raw target ID when the display name is already known.
- If the channel is not connected, tell the user clearly and stop.
- `list-docs`, `get-doc`, and `create-doc` are **Feishu only**. Calling them on Slack or Telegram returns an error.
