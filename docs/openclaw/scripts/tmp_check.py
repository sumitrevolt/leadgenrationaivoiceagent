import json
from app.platform.reply_agent import hot_queue
r = hot_queue(scope='boss')
print(json.dumps(r[:10], indent=2, default=str))
print(f"TOTAL: {len(r)}")
