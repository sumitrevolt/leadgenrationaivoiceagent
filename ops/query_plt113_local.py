import sqlite3, json

db = sqlite3.connect(r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\data\admin_tasks.db")
db.row_factory = sqlite3.Row
tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("tables:", tables)
for t in tables:
    rows = db.execute(f"SELECT * FROM {t}").fetchall()
    print(f"--- {t}: {len(rows)} rows ---")
    for r in rows:
        d = dict(r)
        s = json.dumps(d, ensure_ascii=False, default=str)
        if "PLT-113" in s or "jiya" in s.lower():
            print(t, "::", s[:500])
