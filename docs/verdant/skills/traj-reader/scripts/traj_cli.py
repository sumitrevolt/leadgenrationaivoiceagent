#!/usr/bin/env python3
"""CLI tool for reading and browsing compact trajectory (traj) files."""

import argparse
import json
import os
import re
import sys
from pathlib import Path

ARTIFACTS_BASE = Path.home() / ".verdent" / "artifacts" / "buckets"
TRAJ_DIR_NAME = "traj"
TRAJ_PREFIX = "traj_"

_META_RE = re.compile(
    r'"(message_count|timestamp)"\s*:\s*(?:"([^"]*)"|(\d+))'
)


def _salvage_meta(path):
    """Best-effort extraction of timestamp/message_count from a malformed JSON file."""
    salvaged = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            # top-of-file is enough; keys normally live within first few KB
            head = f.read(8192)
        for m in _META_RE.finditer(head):
            key = m.group(1)
            val = m.group(2) if m.group(2) is not None else m.group(3)
            if key == "message_count":
                try:
                    salvaged[key] = int(val)
                except (TypeError, ValueError):
                    pass
            else:
                salvaged[key] = val
            if "message_count" in salvaged and "timestamp" in salvaged:
                break
    except OSError:
        pass
    return salvaged


def discover_channels():
    if not ARTIFACTS_BASE.exists():
        return []
    channels = []
    for bucket_dir in sorted(ARTIFACTS_BASE.iterdir()):
        if not bucket_dir.is_dir():
            continue
        for group_dir in sorted(bucket_dir.iterdir()):
            if not group_dir.is_dir():
                continue
            traj_dir = group_dir / TRAJ_DIR_NAME
            if traj_dir.is_dir():
                traj_files = sorted(
                    f for f in traj_dir.iterdir()
                    if f.name.startswith(TRAJ_PREFIX) and f.suffix == ".json"
                )
                if traj_files:
                    channels.append({
                        "bucket_id": bucket_dir.name,
                        "group_id": group_dir.name,
                        "traj_dir": str(traj_dir),
                        "traj_count": len(traj_files),
                    })
    return channels


def get_traj_files(channel_id):
    for ch in discover_channels():
        if ch["bucket_id"] == channel_id or ch["group_id"] == channel_id:
            traj_dir = Path(ch["traj_dir"])
            files = []
            for f in sorted(traj_dir.iterdir()):
                if f.name.startswith(TRAJ_PREFIX) and f.suffix == ".json":
                    meta = load_traj_meta(f)
                    files.append({
                        "path": str(f),
                        "filename": f.name,
                        "message_count": meta.get("message_count", 0),
                        "timestamp": meta.get("timestamp", ""),
                        "corrupted": meta.get("_corrupted", False),
                    })
            return files
    return []


def load_traj_meta(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"message_count": data.get("message_count", 0), "timestamp": data.get("timestamp", "")}
    except json.JSONDecodeError as err:
        print(f"[warn] {Path(path).name}: truncated/invalid JSON ({err})", file=sys.stderr)
        salvaged = _salvage_meta(path)
        return {
            "_corrupted": True,
            "message_count": salvaged.get("message_count", 0),
            "timestamp": salvaged.get("timestamp", ""),
        }
    except Exception as err:
        print(f"[warn] {Path(path).name}: failed to read ({err})", file=sys.stderr)
        return {"_corrupted": True, "message_count": 0, "timestamp": ""}


def load_traj(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as err:
        print(f"[warn] {Path(path).name}: truncated/invalid JSON ({err})", file=sys.stderr)
        return {"timestamp": "", "message_count": 0, "contents": [], "_corrupted": True}
    except Exception as err:
        print(f"[warn] {Path(path).name}: failed to read ({err})", file=sys.stderr)
        return {"timestamp": "", "message_count": 0, "contents": [], "_corrupted": True}


def extract_text(parts):
    texts = []
    for p in parts:
        if isinstance(p, dict):
            if "text" in p:
                texts.append(p["text"])
            elif "function_call" in p:
                fc = p["function_call"]
                texts.append(f"[tool_call: {fc.get('name', '?')}]")
            elif "function_response" in p:
                fr = p["function_response"]
                resp = fr.get("response", {})
                result = resp.get("result", "")
                result_str = str(result)
                preview = result_str[:200] + "..." if len(result_str) > 200 else result_str
                texts.append(f"[tool_result: {fr.get('name', '?')}] {preview}")
        elif isinstance(p, str):
            texts.append(p)
    return "\n".join(texts)


def cmd_channels(args):
    channels = discover_channels()
    if not channels:
        print("No channels with traj files found.")
        return
    if args.json:
        print(json.dumps(channels, indent=2, ensure_ascii=False))
        return
    print(f"{'Channel ID':<40} {'Traj Count':>10}")
    print("-" * 52)
    for ch in channels:
        print(f"{ch['bucket_id']:<40} {ch['traj_count']:>10}")


def cmd_list(args):
    if args.all:
        channels = discover_channels()
        all_files = []
        for ch in channels:
            files = get_traj_files(ch["bucket_id"])
            for f in files:
                f["channel"] = ch["bucket_id"]
            all_files.extend(files)
        if args.json:
            print(json.dumps(all_files, indent=2, ensure_ascii=False))
            return
        if not all_files:
            print("No traj files found.")
            return
        print(f"{'Idx':<5} {'Channel':<40} {'Timestamp':<28} {'Messages':>8}")
        print("-" * 83)
        for i, f in enumerate(all_files):
            ch_short = f["channel"][:36] + "..." if len(f["channel"]) > 36 else f["channel"]
            tag = " [CORRUPTED]" if f.get("corrupted") else ""
            print(f"{i:<5} {ch_short:<40} {f['timestamp']:<28} {f['message_count']:>8}{tag}")
        corrupted_n = sum(1 for f in all_files if f.get("corrupted"))
        if corrupted_n:
            print(f"\n[!] {corrupted_n} corrupted file(s) detected (see [CORRUPTED] above).")
        return

    if not args.channel:
        print("Error: --channel required (or use --all)", file=sys.stderr)
        sys.exit(1)
    files = get_traj_files(args.channel)
    if args.json:
        print(json.dumps(files, indent=2, ensure_ascii=False))
        return
    if not files:
        print(f"No traj files found for channel: {args.channel}")
        return
    print(f"{'Idx':<5} {'Timestamp':<28} {'Messages':>8}  {'Filename'}")
    print("-" * 80)
    for i, f in enumerate(files):
        tag = " [CORRUPTED]" if f.get("corrupted") else ""
        print(f"{i:<5} {f['timestamp']:<28} {f['message_count']:>8}  {f['filename']}{tag}")
    corrupted_n = sum(1 for f in files if f.get("corrupted"))
    if corrupted_n:
        print(f"\n[!] {corrupted_n} corrupted file(s) detected (see [CORRUPTED] above).")


def cmd_read(args):
    if not args.channel:
        print("Error: --channel required", file=sys.stderr)
        sys.exit(1)
    files = get_traj_files(args.channel)
    if not files:
        print(f"No traj files for channel: {args.channel}", file=sys.stderr)
        sys.exit(1)
    if args.index < 0 or args.index >= len(files):
        print(f"Error: index {args.index} out of range (0-{len(files)-1})", file=sys.stderr)
        sys.exit(1)

    traj = load_traj(files[args.index]["path"])
    contents = traj.get("contents", [])

    if traj.get("_corrupted") or not contents:
        print(
            f"Error: traj file is corrupted or empty: {files[args.index]['path']}",
            file=sys.stderr,
        )
        sys.exit(1)

    start, end = 0, len(contents)
    if args.range:
        parts = args.range.split("-")
        start = int(parts[0])
        end = int(parts[1]) + 1 if len(parts) > 1 else start + 1
        start = max(0, start)
        end = min(len(contents), end)

    if args.json:
        print(json.dumps(contents[start:end], indent=2, ensure_ascii=False))
        return

    print(f"Traj: {files[args.index]['filename']} | Messages: {start}-{end-1} of {len(contents)}")
    print("=" * 80)
    for i in range(start, end):
        msg = contents[i]
        role = msg.get("role", "?")
        text = extract_text(msg.get("parts", []))
        header = f"[{i}] {role.upper()}"
        print(f"\n{header}")
        print("-" * len(header))
        if args.truncate and len(text) > args.truncate:
            print(text[:args.truncate] + f"\n... (truncated, total {len(text)} chars)")
        else:
            print(text)


def cmd_search(args):
    query = args.query.lower()
    channels = discover_channels()
    if args.channel:
        channels = [ch for ch in channels if ch["bucket_id"] == args.channel or ch["group_id"] == args.channel]

    results = []
    for ch in channels:
        files = get_traj_files(ch["bucket_id"])
        for fi, f in enumerate(files):
            traj = load_traj(f["path"])
            for mi, msg in enumerate(traj.get("contents", [])):
                text = extract_text(msg.get("parts", []))
                if query in text.lower():
                    pos = text.lower().index(query)
                    ctx_start = max(0, pos - 80)
                    ctx_end = min(len(text), pos + len(query) + 80)
                    snippet = text[ctx_start:ctx_end].replace("\n", " ")
                    results.append({
                        "channel": ch["bucket_id"],
                        "traj_index": fi,
                        "traj_file": f["filename"],
                        "msg_index": mi,
                        "role": msg.get("role", "?"),
                        "snippet": snippet,
                        "path": f["path"],
                    })

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return
    if not results:
        print(f"No results for: {args.query}")
        return
    print(f"Found {len(results)} matches for '{args.query}':\n")
    for r in results[:args.limit]:
        print(f"  [{r['channel'][:12]}...] traj#{r['traj_index']} msg#{r['msg_index']} ({r['role']})")
        print(f"    ...{r['snippet']}...")
        print()


def cmd_summary(args):
    if not args.channel:
        print("Error: --channel required", file=sys.stderr)
        sys.exit(1)
    files = get_traj_files(args.channel)
    if not files:
        print(f"No traj files for channel: {args.channel}", file=sys.stderr)
        sys.exit(1)
    if args.index < 0 or args.index >= len(files):
        print(f"Error: index {args.index} out of range (0-{len(files)-1})", file=sys.stderr)
        sys.exit(1)

    traj = load_traj(files[args.index]["path"])
    contents = traj.get("contents", [])
    is_corrupted = bool(traj.get("_corrupted"))
    roles = {}
    tool_calls = 0
    total_chars = 0
    for msg in contents:
        role = msg.get("role", "unknown")
        roles[role] = roles.get(role, 0) + 1
        for p in msg.get("parts", []):
            if isinstance(p, dict):
                if "text" in p:
                    total_chars += len(p["text"])
                if "function_call" in p:
                    tool_calls += 1

    summary = {
        "file": files[args.index]["filename"],
        "path": files[args.index]["path"],
        "timestamp": traj.get("timestamp", ""),
        "message_count": len(contents),
        "roles": roles,
        "tool_calls": tool_calls,
        "total_chars": total_chars,
        "corrupted": is_corrupted,
    }

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return

    if is_corrupted:
        print(f"[!] CORRUPTED: traj file is truncated/invalid JSON: {summary['path']}")
        print("    (counts below reflect only what could be parsed; likely 0)")
    print(f"File:       {summary['file']}")
    print(f"Path:       {summary['path']}")
    print(f"Timestamp:  {summary['timestamp']}")
    print(f"Messages:   {summary['message_count']}")
    print(f"Tool calls: {summary['tool_calls']}")
    print(f"Total chars:{summary['total_chars']}")
    print(f"Roles:")
    for role, count in sorted(roles.items()):
        print(f"  {role}: {count}")


def cmd_stats(args):
    channels = discover_channels()
    total_trajs = sum(ch["traj_count"] for ch in channels)
    total_messages = 0
    corrupted_count = 0
    corrupted_messages = 0
    for ch in channels:
        for f in get_traj_files(ch["bucket_id"]):
            total_messages += f["message_count"]
            if f.get("corrupted"):
                corrupted_count += 1
                corrupted_messages += f["message_count"]

    stats = {
        "channels": len(channels),
        "total_trajs": total_trajs,
        "total_messages": total_messages,
        "corrupted_count": corrupted_count,
        "corrupted_messages": corrupted_messages,
    }

    if args.json:
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        return

    print(f"Channels:       {stats['channels']}")
    print(f"Total trajs:    {stats['total_trajs']}")
    print(f"Total messages: {stats['total_messages']}")
    print(f"Corrupted:      {stats['corrupted_count']} (messages salvaged: {stats['corrupted_messages']})")


def main():
    parser = argparse.ArgumentParser(description="Read and browse compact trajectory files")
    parser.add_argument("--json", action="store_true", help="Output in JSON format")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("channels", help="List all channels with traj files")

    p_list = sub.add_parser("list", help="List traj files")
    p_list.add_argument("--channel", "-c", help="Channel (bucket/task) ID")
    p_list.add_argument("--all", "-a", action="store_true", help="List all channels")

    p_read = sub.add_parser("read", help="Read a traj file")
    p_read.add_argument("--channel", "-c", required=True, help="Channel ID")
    p_read.add_argument("--index", "-i", type=int, default=0, help="Traj file index (default: 0)")
    p_read.add_argument("--range", "-r", help="Message range, e.g. 0-10")
    p_read.add_argument("--truncate", "-t", type=int, default=None, help="Truncate each message to N chars")

    p_search = sub.add_parser("search", help="Search traj contents")
    p_search.add_argument("--query", "-q", required=True, help="Search query")
    p_search.add_argument("--channel", "-c", help="Limit to channel")
    p_search.add_argument("--limit", "-l", type=int, default=20, help="Max results (default: 20)")

    p_summary = sub.add_parser("summary", help="Show traj file summary")
    p_summary.add_argument("--channel", "-c", required=True, help="Channel ID")
    p_summary.add_argument("--index", "-i", type=int, default=0, help="Traj file index")

    sub.add_parser("stats", help="Global statistics")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    cmd_map = {
        "channels": cmd_channels,
        "list": cmd_list,
        "read": cmd_read,
        "search": cmd_search,
        "summary": cmd_summary,
        "stats": cmd_stats,
    }
    cmd_map[args.command](args)


if __name__ == "__main__":
    main()
