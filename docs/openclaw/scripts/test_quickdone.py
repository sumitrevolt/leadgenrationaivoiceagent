from app.platform.reply_agent import hot_queue, make_hq_done_token
rows = hot_queue(limit=5, scope='boss')
print('Total:', len(rows))
r = rows[0]
hq_id = r['hq_id']
print('HQ_ID:', hq_id)
token = make_hq_done_token(hq_id)
print('Token:', token)
print('Quick-done URL: https://leadsgenai.in/api/growth/reply/hot-queue/quick-done/' + token)