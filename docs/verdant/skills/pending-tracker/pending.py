#!/usr/bin/env python3
"""
Pending Tracker CLI

A command-line tool for managing requirement-level pending items.
Data is stored in the current manager workspace at
$VERDENT_HOME/pending-tracker.json. VERDENT_HOME is required.
Legacy ~/.verdent/workspace/pending-tracker.json is imported once when the new
file does not exist.
"""

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from typing import Any, Optional


def get_verdent_home() -> str:
    verdent_home = os.environ.get("VERDENT_HOME")
    if not verdent_home:
        raise RuntimeError("VERDENT_HOME is required for manager skills")
    return verdent_home


def get_data_file() -> str:
    return os.path.join(get_verdent_home(), "pending-tracker.json")


def get_legacy_data_files() -> list[str]:
    return [os.path.expanduser("~/.verdent/workspace/pending-tracker.json")]


DATA_FILE = get_data_file()


def import_legacy_data_if_needed() -> None:
    if os.path.exists(DATA_FILE):
        return
    for legacy_file in get_legacy_data_files():
        if os.path.abspath(legacy_file) == os.path.abspath(DATA_FILE):
            continue
        if not os.path.exists(legacy_file):
            continue
        dir_path = os.path.dirname(DATA_FILE)
        os.makedirs(dir_path, exist_ok=True)
        with open(legacy_file, "r", encoding="utf-8") as src:
            data = json.load(src)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=dir_path, delete=False, suffix=".tmp"
        ) as tmp:
            json.dump(data, tmp, indent=2, ensure_ascii=False)
            tmp_path = tmp.name
        os.replace(tmp_path, DATA_FILE)
        return


def _migrate_items(data: dict[str, Any]) -> bool:
    """Migrate old format items to current format. Returns True if any migration occurred."""
    migrated = False
    for item in data.get("items", []):
        if "ref" in item:
            ref = item.pop("ref")
            if isinstance(ref, dict) and ref.get("id") is not None:
                ref_task = {"id": ref["id"], "name": ref.get("name", "")}
                if "tasks" not in item:
                    item["tasks"] = [ref_task]
                else:
                    # Merge: add ref task if not already in tasks
                    existing_ids = {t.get("id") for t in item["tasks"]}
                    if ref_task["id"] not in existing_ids:
                        item["tasks"].append(ref_task)
            elif "tasks" not in item:
                item["tasks"] = []
            migrated = True
        
        if "tasks" not in item:
            item["tasks"] = []
            migrated = True
        
        if "updated_at" not in item:
            item["updated_at"] = item.get("created_at", datetime.now(timezone.utc).isoformat())
            migrated = True
    
    return migrated


def load_data() -> dict[str, Any]:
    """Load pending tracker data from JSON file. Raises on corruption."""
    import_legacy_data_if_needed()
    if not os.path.exists(DATA_FILE):
        return {"items": []}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    if _migrate_items(data):
        save_data(data)
    
    return data


def save_data(data: dict[str, Any]) -> None:
    """Save pending tracker data to JSON file atomically."""
    dir_path = os.path.dirname(DATA_FILE)
    os.makedirs(dir_path, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=dir_path, delete=False, suffix=".tmp"
    ) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp_path = tmp.name
    os.replace(tmp_path, DATA_FILE)


def generate_id(title: str) -> str:
    """Generate 8-char hex ID from title + timestamp."""
    content = title + datetime.now(timezone.utc).isoformat()
    return hashlib.sha256(content.encode()).hexdigest()[:8]


def calculate_age(created_at: str) -> str:
    """Calculate age from created_at timestamp (e.g., '3d', '2h')."""
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - created
        days = delta.days
        if days > 0:
            return f"{days}d"
        hours = delta.seconds // 3600
        if hours > 0:
            return f"{hours}h"
        minutes = delta.seconds // 60
        return f"{minutes}m"
    except Exception:
        return "?"


def is_stale(updated_at: str) -> bool:
    """Check if item is stale (updated > 3 days ago)."""
    try:
        updated = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        delta = now - updated
        return delta.days >= 3
    except Exception:
        return False


def count_tasks(tasks: list) -> int:
    """Count number of linked tasks."""
    if isinstance(tasks, list):
        return len(tasks)
    return 0


def cmd_list(args: argparse.Namespace) -> dict[str, Any]:
    """List pending items."""
    data = load_data()
    items = data.get("items", [])
    
    if not args.all:
        items = [item for item in items if item.get("status") != "complete"]
    
    result_items = []
    for item in items:
        result_items.append({
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "status": item.get("status", "pend"),
            "tasks": count_tasks(item.get("tasks", [])),
            "age": calculate_age(item.get("created_at", "")),
            "stale": is_stale(item.get("updated_at", item.get("created_at", ""))),
        })
    
    return {"count": len(result_items), "items": result_items}


def cmd_add(args: argparse.Namespace) -> dict[str, Any]:
    """Add a new pending item."""
    data = load_data()
    item_id = generate_id(args.title)
    now = datetime.now(timezone.utc).isoformat()
    
    new_item = {
        "id": item_id,
        "title": args.title,
        "status": "pend",
        "tasks": [],
        "note": args.note or "",
        "created_at": now,
        "updated_at": now,
    }
    
    data.setdefault("items", []).append(new_item)
    save_data(data)
    
    return {"success": True, "id": item_id, "title": args.title}


def cmd_update(args: argparse.Namespace) -> dict[str, Any]:
    """Update an existing pending item."""
    data = load_data()
    items = data.get("items", [])
    
    for item in items:
        if item.get("id") == args.id:
            if args.status:
                item["status"] = args.status
            if args.note is not None:
                item["note"] = args.note
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_data(data)
            return {"success": True, "id": args.id, "status": item["status"]}
    
    return {"success": False, "error": f"Item not found: {args.id}"}


def cmd_complete(args: argparse.Namespace) -> dict[str, Any]:
    """Mark an item as complete and manage retention."""
    data = load_data()
    items = data.get("items", [])
    
    found = False
    for item in items:
        if item.get("id") == args.id:
            item["status"] = "complete"
            if args.note is not None:
                item["note"] = args.note
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            found = True
            break
    
    if not found:
        return {"success": False, "error": f"Item not found: {args.id}"}
    
    complete_items = [item for item in items if item.get("status") == "complete"]
    if len(complete_items) > 10:
        complete_items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        keep_ids = {item["id"] for item in complete_items[:10]}
        data["items"] = [item for item in items if item.get("status") != "complete" or item["id"] in keep_ids]
    
    save_data(data)
    return {"success": True, "id": args.id, "status": "complete"}


def cmd_link(args: argparse.Namespace) -> dict[str, Any]:
    """Link a task to a pending item."""
    data = load_data()
    items = data.get("items", [])
    
    for item in items:
        if item.get("id") == args.id:
            tasks = item.setdefault("tasks", [])
            
            existing_ids = {task.get("id") for task in tasks if isinstance(task, dict)}
            if args.task_id not in existing_ids:
                tasks.append({
                    "id": args.task_id,
                    "name": args.task_name or "",
                })
            
            item["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_data(data)
            return {"success": True, "id": args.id, "linked": args.task_id}
    
    return {"success": False, "error": f"Item not found: {args.id}"}


def cmd_delete(args: argparse.Namespace) -> dict[str, Any]:
    """Delete a pending item."""
    data = load_data()
    items = data.get("items", [])
    
    original_count = len(items)
    data["items"] = [item for item in items if item.get("id") != args.id]
    
    if len(data["items"]) == original_count:
        return {"success": False, "error": f"Item not found: {args.id}"}
    
    save_data(data)
    return {"success": True, "id": args.id}


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Pending Tracker CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    list_parser = subparsers.add_parser("list", help="List pending items")
    list_parser.add_argument("--all", action="store_true", help="Include completed items")
    
    add_parser = subparsers.add_parser("add", help="Add a new pending item")
    add_parser.add_argument("title", help="Requirement title")
    add_parser.add_argument("--note", help="Optional note or context")
    
    update_parser = subparsers.add_parser("update", help="Update a pending item")
    update_parser.add_argument("id", help="Item ID")
    update_parser.add_argument("--status", choices=["pend", "running", "hold"], help="New status")
    update_parser.add_argument("--note", help="Update note")
    
    complete_parser = subparsers.add_parser("complete", help="Mark item as complete")
    complete_parser.add_argument("id", help="Item ID")
    complete_parser.add_argument("--note", help="Completion note")
    
    link_parser = subparsers.add_parser("link", help="Link a task to an item")
    link_parser.add_argument("id", help="Item ID")
    link_parser.add_argument("--task-id", required=True, help="Task UUID")
    link_parser.add_argument("--task-name", help="Task name")
    
    delete_parser = subparsers.add_parser("delete", help="Delete a pending item")
    delete_parser.add_argument("id", help="Item ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    try:
        result = None
        if args.command == "list":
            result = cmd_list(args)
        elif args.command == "add":
            result = cmd_add(args)
        elif args.command == "update":
            result = cmd_update(args)
        elif args.command == "complete":
            result = cmd_complete(args)
        elif args.command == "link":
            result = cmd_link(args)
        elif args.command == "delete":
            result = cmd_delete(args)
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except json.JSONDecodeError as e:
        print(json.dumps({"success": False, "error": f"Data file corrupted: {e}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
