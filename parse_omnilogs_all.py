import sqlite3

conn = sqlite3.connect('omniroute_storage_temp.sqlite')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT timestamp, model, provider, status, error_summary, combo_name FROM call_logs WHERE status != 200 AND status != 413 AND status != 429 ORDER BY timestamp DESC LIMIT 10")
for r in c.fetchall():
    print(dict(r))
