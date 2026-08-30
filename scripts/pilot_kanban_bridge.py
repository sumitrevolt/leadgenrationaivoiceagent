import base64
import json
import os
import sqlite3
import subprocess
import time
import uuid


def send_mcp(proc, msg):
    req = json.dumps(msg)
    proc.stdin.write(req + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            return None
        try:
            resp = json.loads(line)
            if "id" in resp and resp["id"] == msg.get("id"):
                return resp
        except:
            pass


def run_cua_driver(action, text=None):
    proc = subprocess.Popen(
        ["cua-driver", "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True
    )

    # Initialize
    send_mcp(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "kanban_bridge", "version": "1.0"},
            },
        },
    )

    # Tool call
    tool_args = {"action": action}
    if text:
        tool_args["text"] = text

    res = send_mcp(
        proc,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "computer_use", "arguments": tool_args},
        },
    )

    proc.terminate()
    return res


def process_tasks():
    db_path = os.environ.get("HERMES_KANBAN_DB")
    if not db_path:
        return

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    while True:
        cursor.execute(
            "SELECT id, title, body FROM tasks WHERE assignee='pilot' AND status IN ('todo', 'ready')"
        )
        tasks = cursor.fetchall()
        for task in tasks:
            tid = task["id"]
            print(f"Claiming {tid}")

            # Claim
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            conn.execute("UPDATE tasks SET status='running' WHERE id=?", (tid,))
            conn.execute(
                "INSERT INTO task_events (task_id, kind, payload, created_at) VALUES (?, 'claimed', '{}', ?)",
                (tid, now),
            )
            conn.commit()

            if "Failure" in task["title"]:
                print("Demonstrating failure path.")
                conn.execute("UPDATE tasks SET status='blocked' WHERE id=?", (tid,))
                conn.execute(
                    "INSERT INTO task_events (task_id, kind, payload, created_at) VALUES (?, 'blocked', '{\"reason\": \"Failed as part of demonstration\"}', ?)",
                    (tid, now),
                )
                conn.commit()
            else:
                print("Executing computer_use via cua-driver")
                # Demo action
                result = run_cua_driver("capture")
                out_path = ""
                if result and "result" in result:
                    content = result["result"].get("content", [])
                    for item in content:
                        if item.get("type") == "text" and "screenshot saved to" in item.get(
                            "text", ""
                        ):
                            # extract path
                            t = item["text"]
                            out_path = t.split("screenshot saved to ")[-1].split(")")[0].strip()

                # Setup artifact attach logic mock
                conn.execute("UPDATE tasks SET status='done' WHERE id=?", (tid,))
                conn.execute(
                    "INSERT INTO task_events (task_id, kind, payload, created_at) VALUES (?, 'completed', '{\"summary\": \"Task finished via bridge.\"}', ?)",
                    (tid, now),
                )
                conn.commit()

                print(f"Completed {tid}, artifact {out_path}")
        time.sleep(5)


if __name__ == "__main__":
    process_tasks()
