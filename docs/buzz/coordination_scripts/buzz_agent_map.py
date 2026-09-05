#!/usr/bin/env python3
"""Print managed-agents roster minus avatar blobs."""
import json, os
from pathlib import Path

p = Path(os.environ["APPDATA"]) / "xyz.block.buzz.app" / "agents" / "managed-agents.json"
data = json.loads(p.read_text(encoding="utf-8"))
for a in data:
    a.pop("avatar_url", None)
    a.pop("system_prompt", None)
    print(json.dumps(a, ensure_ascii=False))
