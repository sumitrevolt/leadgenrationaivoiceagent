import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sqlite3

from app.admin.services import task_ledger as tl

c = sqlite3.connect(str(tl.DB_PATH))
print("=== 1CR rows and the over-length row ===")
for tid, tl_ in c.execute(
    "select id, length(title) from tasks where length(title) > 470 order by length(title) desc"
):
    print(f"  id={tid} title_len={tl_}")

print("\n=== all 1CR rows ===")
for tid, title, status in c.execute(
    "select id, title, status from tasks where title like '1CR-BLK-%' order by id"
):
    print(f"  {tid} [{status}] {title[:86]}")
