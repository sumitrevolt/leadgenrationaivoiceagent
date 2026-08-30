import sqlite3
import json

conn = sqlite3.connect('omniroute_storage_temp.sqlite')
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Read backup
bak = sqlite3.connect('omniroute_storage_temp.sqlite')  # already has our groq-only edit
# We need the ORIGINAL backup
import shutil
# backup was made at start of session
# Let's check what models the backup had
bak2 = sqlite3.connect('omniroute_storage_temp.sqlite')
bak2.row_factory = sqlite3.Row
c2 = bak2.cursor()
c2.execute("SELECT data FROM combos WHERE name='leadgen-project-best'")
row = c2.fetchone()
combo = json.loads(row['data'])
print(f"Current models count: {len(combo.get('models', []))}")
for m in combo.get('models', []):
    print(f"  {m['model']}")
