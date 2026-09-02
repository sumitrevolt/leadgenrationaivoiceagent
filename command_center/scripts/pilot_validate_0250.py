#!/usr/bin/env python3
"""Validate tasks.json + messages.jsonl after PILOT dispatch."""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
t = json.load(open(os.path.join(BASE, "tasks.json"), encoding="utf-8"))
print("tasks.json VALID, tasks:", len(t))
lines = open(os.path.join(BASE, "messages.jsonl"), encoding="utf-8").readlines()
for l in lines:
    if l.strip():
        json.loads(l)
print("messages.jsonl VALID, lines:", len([l for l in lines if l.strip()]))
for task in t:
    if task.get("status") not in ("CLOSED", "STANDBY"):
        print("ACTIVE:", task["id"], task["owner"], task["status"], "| due", task.get("deadline", "-"))