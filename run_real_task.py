"""Run the dispatcher against the REAL existing task_79406871 in the live
orchestrator_ledger.db. End-to-end integration check, no mocks.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

WORKTREE = Path(__file__).resolve().parent
# Worktrees sit under <repo>/.worktrees/<name>/; the live data dir is at
# <repo>/data/ — go up two levels from the script to reach the repo root.
ROOT = WORKTREE.parent.parent
sys.path.insert(0, str(WORKTREE))

import os
os.environ.setdefault("TELEGRAM_OWNER_CHAT_IDS", "1621120182")

# IMPORTANT: use the REAL orchestrator + real ledger
# Disable network in send_message_with_message_id via a stub
import app.integrations.telegram_bot as tb_mod

# Swap out send_message_with_message_id to skip network but record the call
_orig_send_with_id = tb_mod.TelegramBot.send_message_with_message_id
_sent_calls: list[dict] = []


def _stub_send(self, chat_id, text, parse_mode=None):
    _sent_calls.append({"chat_id": chat_id, "text_len": len(text), "text_first_120": text[:120]})
    return True, 888777  # fake but plausible message_id


tb_mod.TelegramBot.send_message_with_message_id = _stub_send

# Also stub the token check to bypass network
def _stub_init(self, *a, **kw):
    self.token = "stub"
    # any other attrs accessed lazily
tb_mod.TelegramBot.__init__ = _stub_init


from app.platform.telegram_owner_command_dispatcher import dispatch_owner_command
from app.platform.automation_orchestrator import AutomationOrchestrator, DurableTaskStore
from app.integrations.telegram_bot import TelegramBot

# Use the real ledger paths (NOT worktree copies — we want the LIVE task_79406871)
LIVE_LEDGER_DB = ROOT / "data" / "orchestrator_ledger.db"
if not LIVE_LEDGER_DB.exists():
    print(f"ERROR: live ledger not at {LIVE_LEDGER_DB}")
    sys.exit(2)

print(f"Live ledger: {LIVE_LEDGER_DB} ({LIVE_LEDGER_DB.stat().st_size}B)")

# AutomationOrchestrator takes a pre-built store, NOT a db_path.
# DurableTaskStore accepts db_path directly.
live_store = DurableTaskStore(db_path=str(LIVE_LEDGER_DB))
orch = AutomationOrchestrator(store=live_store)
bot = TelegramBot()  # token stubbed, send_message stubbed

# Pre-state
import sqlite3
con = sqlite3.connect(str(LIVE_LEDGER_DB))
con.row_factory = sqlite3.Row
pre = con.execute(
    "SELECT task_id, status, version, fencing_token, idempotency_key, "
    "input_payload, evidence, error_message FROM task_records "
    "WHERE task_id='task_79406871'"
).fetchone()
print("\n=== PRE-STATE ===")
print(json.dumps(dict(pre), indent=2, default=str))

# Run the dispatcher
UPDATE_ID = 800001
COMMAND = "/status"
TASK_ID = "task_79406871"
CHAT_ID = 1621120182

print(f"\n=== DISPATCHING update_id={UPDATE_ID} command={COMMAND} task={TASK_ID} ===")
res = dispatch_owner_command(
    update_id=UPDATE_ID,
    chat_id=CHAT_ID,
    command=COMMAND,
    task_id=TASK_ID,
    orchestrator=orch,
    telegram_bot=bot,
)

print(f"\n=== RESULT ===")
print(json.dumps(res.to_redacted_dict(), indent=2))

# Post-state
post = con.execute(
    "SELECT task_id, status, version, fencing_token, idempotency_key, "
    "input_payload, evidence, error_message FROM task_records "
    "WHERE task_id='task_79406871'"
).fetchone()
print("\n=== POST-STATE ===")
print(json.dumps(dict(post), indent=2, default=str))
con.close()

print("\n=== STUBBED SEND CALLS ===")
for c in _sent_calls:
    print(json.dumps(c, indent=2))

print("\nDONE")
