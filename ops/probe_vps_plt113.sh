#!/usr/bin/env bash
set -u
DB=/opt/leadgen/data/admin_tasks.db
echo "=== tables ==="
sqlite3 "$DB" ".tables" 2>&1 | head -c 300
echo
echo "=== PLT-113 rows ==="
sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table';" 2>/dev/null
for t in $(sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table';" 2>/dev/null); do
  cols=$(sqlite3 "$DB" "PRAGMA table_info($t);" 2>/dev/null | awk -F'|' '{print $2}' | tr '\n' ',' )
  echo "TABLE $t cols: $cols"
  if echo "$cols" | grep -qiE 'id|name|status|task'; then
    sqlite3 -header "$DB" "SELECT * FROM $t WHERE 1=1 LIMIT 3;" 2>/dev/null | grep -iE 'PLT-113|jiya' | head -5
  fi
done
echo "=== direct PLT-113 grep across tables ==="
sqlite3 "$DB" "SELECT 'tasks:' , COUNT(*) FROM tasks WHERE id LIKE 'PLT-113%' OR name LIKE '%JIYA%';" 2>/dev/null
echo "=== jiya customer rows (billing/customers) ==="
sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table';" 2>/dev/null
