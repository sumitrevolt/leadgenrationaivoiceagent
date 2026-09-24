"""Verify task_79406871 state from REAL ledger. Script file to avoid shell-quoting hell."""
import hashlib
import json
import sqlite3
from pathlib import Path

DB = Path(r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\data\orchestrator_ledger.db")
con = sqlite3.connect(str(DB))
con.row_factory = sqlite3.Row
row = con.execute(
    "SELECT task_id, status, version, fencing_token, idempotency_key, "
    "input_payload, evidence, error_message, retry_count, updated_at, "
    "owner_bot, assigned_agent, priority "
    "FROM task_records WHERE task_id='task_79406871'"
).fetchone()
out = dict(row) if row else {"exists": False}
con.close()

# Fingerprints (no raw secrets)
fp = {}
if out.get("input_payload"):
    fp["input_payload"] = "fp_" + hashlib.sha256(str(out["input_payload"]).encode()).hexdigest()[:10]
if out.get("evidence"):
    fp["evidence"] = "fp_" + hashlib.sha256(str(out["evidence"]).encode()).hexdigest()[:10]

# Strip large fields, replace with fingerprints
out_red = {k: v for k, v in out.items() if k not in ("input_payload", "evidence")}
out_red["_input_payload_fingerprint"] = fp.get("input_payload", None)
out_red["_evidence_fingerprint"] = fp.get("evidence", None)
out_red["_input_payload_size"] = len(str(out.get("input_payload") or ""))
out_red["_evidence_size"] = len(str(out.get("evidence") or ""))

print("TASK_79406871_STATE_FROM_REAL_LEDGER")
print(json.dumps(out_red, indent=2, default=str))
print()
print(f"DB_PATH={DB}")
print(f"DB_SIZE={DB.stat().st_size}B")
print(f"DB_MTIME={DB.stat().st_mtime}")
