from app.platform.reply_agent import hot_queue, make_hq_done_token, mark_handled
rows = hot_queue(limit=3, scope='boss')
print('Total:', len(rows))
for i, r in enumerate(rows):
    hq_id = r['hq_id']
    print(f'{i+1}. HQ_ID: {hq_id}')
    token = make_hq_done_token(hq_id)
    ok = mark_handled(hq_id)
    print(f'   mark_handled: {ok}')
    print(f'   Quick-done URL: https://leadsgenai.in/api/growth/reply/hot-queue/quick-done/{token}')
# Check remaining
rows2 = hot_queue(limit=5, scope='boss')
print('After marking 3 done, remaining:', len(rows2))