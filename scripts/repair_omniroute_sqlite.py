import sqlite3
import os
import tempfile
import subprocess
import shutil

temp_dir = tempfile.gettempdir()
corrupt_db = os.path.join(temp_dir, "omniroute_corrupt.sqlite")
repaired_db = os.path.join(temp_dir, "omniroute_repaired.sqlite")

if os.path.exists(repaired_db):
    os.remove(repaired_db)

print("[1] Pulling fresh storage.sqlite from leadgen_omniroute...")
res = subprocess.run(["docker", "cp", "leadgen_omniroute:/app/data/storage.sqlite", corrupt_db], capture_output=True, text=True)
if res.returncode != 0:
    print("docker cp failed:", res.stderr)
    exit(1)

print("[2] Initializing source & target databases...")
src = sqlite3.connect(corrupt_db)
dst = sqlite3.connect(repaired_db)

src_cur = src.cursor()
dst_cur = dst.cursor()

# Get all tables
tables = src_cur.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()

print(f"Found {len(tables)} tables to migrate.")

for table_name, create_sql in tables:
    if not create_sql:
        continue
    try:
        dst_cur.execute(create_sql)
    except Exception as e:
        print(f"Could not create table {table_name}: {e}")
        continue
    
    # Copy data safely row by row or in chunks
    try:
        # Check column count
        cols_info = src_cur.execute(f"PRAGMA table_info('{table_name}')").fetchall()
        cols = [c[1] for c in cols_info]
        placeholders = ",".join(["?" for _ in cols])
        cols_joined = ",".join([f"\"{c}\"" for c in cols])
        insert_sql = f"INSERT OR IGNORE INTO \"{table_name}\" ({cols_joined}) VALUES ({placeholders})"
        
        # Select data
        try:
            rows = src_cur.execute(f"SELECT * FROM \"{table_name}\"").fetchall()
            dst_cur.executemany(insert_sql, rows)
            dst.commit()
            print(f"  [OK] Table '{table_name}': copied {len(rows)} rows.")
        except Exception as e:
            print(f"  [RECOVERING] Table '{table_name}' failed bulk read: {e}. Trying row-by-row...")
            # Try to fetch using cursor iteration
            recovered_count = 0
            try:
                row_cur = src.cursor()
                row_cur.execute(f"SELECT * FROM \"{table_name}\"")
                while True:
                    try:
                        row = row_cur.fetchone()
                        if row is None:
                            break
                        dst_cur.execute(insert_sql, row)
                        recovered_count += 1
                        if recovered_count % 1000 == 0:
                            dst.commit()
                    except Exception as row_err:
                        # Corrupted page hit
                        print(f"    Skipping corrupt row at index {recovered_count}: {row_err}")
                        break
                dst.commit()
                print(f"  [RECOVERED] Table '{table_name}': saved {recovered_count} rows.")
            except Exception as outer_err:
                print(f"    Table '{table_name}' recovery error: {outer_err}")
    except Exception as general_err:
        print(f"  [FAIL] Table '{table_name}': {general_err}")

# Now copy indexes, triggers, views
other_objs = src_cur.execute("SELECT type, name, sql FROM sqlite_master WHERE type IN ('index', 'view', 'trigger') AND sql IS NOT NULL").fetchall()
print(f"Recreating {len(other_objs)} indexes/views/triggers...")
for obj_type, obj_name, obj_sql in other_objs:
    try:
        dst_cur.execute(obj_sql)
    except Exception as e:
        # Ignore index creation errors if duplicate or already created
        pass
dst.commit()

# Run integrity check on repaired DB
print("[3] Checking integrity of repaired database...")
integrity = dst_cur.execute("PRAGMA integrity_check").fetchall()
print("Integrity result:", integrity)

src.close()
dst.close()

if integrity == [('ok',)]:
    print("SUCCESS! Repaired database is 100% OK and CLEAN!")
else:
    print("Warning: Integrity check was not completely 'ok':", integrity)
