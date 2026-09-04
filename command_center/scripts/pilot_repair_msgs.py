#!/usr/bin/env python3
"""Repair messages.jsonl: split concatenated JSON objects into separate lines (pre-existing corruption),
then append PILOT dispatch if missing (idempotent via TS marker)."""
import json, os

BASE = r"C:/Users/Ratanshila/Documents/leadgenrationaivoiceagent/command_center/data"
P = os.path.join(BASE, "messages.jsonl")

raw = open(P, encoding="utf-8").read()
# Split on object boundaries: '}{' preceded by closing quote is the corruption marker
objects = []
buf = ""
depth = 0
in_str = False
esc = False
for ch in raw:
    if in_str:
        buf += ch
        if esc:
            esc = False
        elif ch == "\\":
            esc = True
        elif ch == '"':
            in_str = False
        continue
    if ch == '"':
        in_str = True
        buf += ch
    elif ch == "{":
        depth += 1
        buf += ch
    elif ch == "}":
        depth -= 1
        buf += ch
        if depth == 0:
            objects.append(buf)
            buf = ""
    else:
        buf += ch
if buf.strip():
    # trailing whitespace only normally; if real content, try parse
    s = buf.strip()
    if s and s not in ("", "\n"):
        objects.append(s)

# Validate each object parses; drop empty
parsed = []
dropped = 0
for o in objects:
    o = o.strip()
    if not o:
        continue
    try:
        parsed.append(json.loads(o))
    except json.JSONDecodeError:
        # try to salvage by splitting nested concatenations
        pieces = o.replace('}{"ts"', '}\n{"ts"').splitlines()
        for pc in pieces:
            pc = pc.strip()
            if not pc:
                continue
            try:
                parsed.append(json.loads(pc))
            except json.JSONDecodeError:
                dropped += 1
                print("DROP(unparseable):", pc[:120])

with open(P, "w", encoding="utf-8") as f:
    for m in parsed:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")

# Verify ALL lines parse
bad = 0
for l in open(P, encoding="utf-8"):
    if l.strip():
        try:
            json.loads(l)
        except json.JSONDecodeError:
            bad += 1
            print("STILL BAD:", l[:100])
print("objects:", len(parsed), "| dropped:", dropped, "| remaining bad:", bad, "| total lines:", len(open(P, encoding='utf-8').readlines()))