import sqlite3, json

db = sqlite3.connect(r"C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent\data\admin_tasks.db")
db.row_factory = sqlite3.Row
for r in db.execute("SELECT * FROM tasks"):
    print(json.dumps(dict(r), ensure_ascii=False, default=str)[:400])
