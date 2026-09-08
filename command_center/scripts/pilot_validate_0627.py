#!/usr/bin/env python3
"""Validate the 3 command_center JSON files + print messages count."""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
for name in ["tasks.json", "bots.json", "pinned.json"]:
    p = os.path.join(BASE, name)
    with open(p, encoding="utf-8") as f:
        obj = json.load(f)
    print(f"{name} VALID ({len(obj)} items)" if isinstance(obj, list) else f"{name} VALID object")
msgs = os.path.join(BASE, "messages.jsonl")
count = sum(1 for _ in open(msgs, encoding="utf-8"))
print(f"messages.jsonl lines: {count}")
print("ALL OK")