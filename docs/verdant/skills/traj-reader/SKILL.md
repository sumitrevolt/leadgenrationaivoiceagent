---
name: traj-reader
description: |
  Read and browse conversation trajectory files offloaded during Manager full-compact.
  This skill should be used when needing to review past conversation history from compact
  sessions, list available trajectory channels, read specific traj files, search for
  messages by role or content, browse offloaded conversations, reconstruct context from
  previous sessions, or inspect compact trajectory data. Trigger keywords: traj, trajectory,
  compact history, offloaded conversation, channel traj, past session, conversation replay.
metadata:
  version: '0.0.3'
---

# Traj Reader

Read and browse compact trajectory (traj) files stored at `~/.verdent/artifacts/buckets/{bucket_id}/{group_id}/traj/`.

Each traj file is a JSON snapshot of the full conversation before compact compression, containing `timestamp`, `message_count`, and `contents` (array of `{parts, role}` messages).

## CLI Tool

All operations use `scripts/traj_cli.py` (pure Python, no dependencies).

### List channels (buckets that have traj files)

```bash
python scripts/traj_cli.py channels
python scripts/traj_cli.py --json channels
```

### List traj files in a channel

```bash
python scripts/traj_cli.py list --channel <channel_id>
python scripts/traj_cli.py list --all
```

### Read traj contents

```bash
python scripts/traj_cli.py read --channel <id> --index 0
python scripts/traj_cli.py read --channel <id> --index 0 --range 10-20
python scripts/traj_cli.py read --channel <id> --index 0 --truncate 500
```

### Search across trajs

```bash
python scripts/traj_cli.py search --query "keyword"
python scripts/traj_cli.py search --query "keyword" --channel <id>
python scripts/traj_cli.py search --query "keyword" --limit 50
```

### Summary and stats

```bash
python scripts/traj_cli.py summary --channel <id> --index 0
python scripts/traj_cli.py stats
```

### JSON output

Append `--json` before the subcommand for machine-readable output:

```bash
python scripts/traj_cli.py --json channels
python scripts/traj_cli.py --json list --all
```

## Alternative: Direct file_read

For simple cases, read a traj file directly:

```
file_read("~/.verdent/artifacts/buckets/<bucket_id>/<group_id>/traj/traj_<timestamp>.json")
```

Use `offset` and `limit` params for large files.
