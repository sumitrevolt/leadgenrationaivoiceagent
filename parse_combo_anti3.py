import json
import sqlite3

conn = sqlite3.connect('omniroute_storage_temp.sqlite')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT data FROM combos WHERE name='leadgen-project-best'")
row = c.fetchone()
combo_data = json.loads(row['data'])
for m in combo_data.get('models', []):
    print(f"Model ID: {m['id']} => {m['model']}")
