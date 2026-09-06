import subprocess
import tempfile
import sqlite3
import os

temp_dir = tempfile.gettempdir()
local_db = os.path.join(temp_dir, "omniroute_storage_inspect.sqlite")

print("[1] Copying storage.sqlite from container...")
res = subprocess.run(["docker", "cp", "leadgen_omniroute:/app/data/storage.sqlite", local_db], capture_output=True, text=True)
if res.returncode != 0:
    print("docker cp failed:", res.stderr)
    exit(1)

print("[2] Opening sqlite3 db locally...")
conn = sqlite3.connect(local_db)
cursor = conn.cursor()

tables = cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
table_names = [t[0] for t in tables]
print("Tables found:", table_names)

for t in table_names:
    try:
        count = cursor.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        print(f"Table '{t}': {count} rows")
    except Exception as e:
        print(f"ERROR reading table '{t}': {e}")

try:
    check = cursor.execute("PRAGMA integrity_check").fetchall()
    print("Integrity check first 5 lines:", check[:5])
except Exception as e:
    print("PRAGMA integrity_check error:", e)

conn.close()
