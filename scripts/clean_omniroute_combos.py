import subprocess
import json

js_script = """
const { DatabaseSync } = require('node:sqlite');
const db = new DatabaseSync('/app/data/storage.sqlite');

const canonical = [
  'leadsgen combo 1',
  'leadsgen combo 2',
  'leadsgen combo 3',
  'leadsgen combo 4',
  'leadsgen combo 5',
  'leadsgen combo 6',
  'leadsgen combo 7',
  'leadsgen combo 8',
  'leadsgen combo 9',
  'leadsgen combo 10',
  'leadsgen combo 11',
  'leadsgen combo 12',
  'leadsgen combo 13',
  'leadsgen combo 14'
];

const placeholders = canonical.map(() => '?').join(',');
const before = db.prepare('SELECT count(*) as c FROM combos').get();
console.log('Combos before cleanup:', before.c);

// Delete all combos that are not the 14 canonical ones
const stmt = db.prepare(`DELETE FROM combos WHERE name NOT IN (${placeholders})`);
stmt.run(...canonical);

const after = db.prepare('SELECT count(*) as c FROM combos').get();
console.log('Combos after cleanup (target: 14):', after.c);

const rows = db.prepare('SELECT name FROM combos ORDER BY name').all();
console.log('Clean active combos in OmniRoute:');
rows.forEach((r, idx) => console.log(`  ${idx + 1}. ${r.name}`));

db.close();
"""

with open("temp_clean.js", "w", encoding="utf-8") as f:
    f.write(js_script)

res_cp = subprocess.run(["docker", "cp", "temp_clean.js", "leadgen_omniroute:/tmp/clean.js"], capture_output=True, text=True)
res_exec = subprocess.run(["docker", "exec", "leadgen_omniroute", "node", "/tmp/clean.js"], capture_output=True, text=True)
print(res_exec.stdout)
if res_exec.stderr:
    print("Error:", res_exec.stderr)

import os
if os.path.exists("temp_clean.js"):
    os.remove("temp_clean.js")
