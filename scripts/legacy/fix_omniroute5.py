import json
import sqlite3

conn = sqlite3.connect('omniroute_storage_temp.sqlite')
conn.row_factory = sqlite3.Row
c = conn.cursor()

c.execute("SELECT data FROM combos WHERE name='leadgen-project-best'")
row = c.fetchone()
combo_data = json.loads(row['data'])

new_models = [
  {
    "id": "leadgen-project-best-model-groq-llama-3-3-70b",
    "kind": "model",
    "model": "groq/llama-3.3-70b-versatile",
    "providerId": "groq",
    "weight": 0,
    "label": "llama-3.3-70b"
  }
]
combo_data['models'] = new_models
c.execute("UPDATE combos SET data=? WHERE name='leadgen-project-best'", (json.dumps(combo_data),))
conn.commit()
print("Updated leadgen-project-best to just use groq/llama-3.3-70b-versatile.")
