#!/usr/bin/env bash
# check_posting.sh — READ-ONLY: why is LeadGen AI's own automated posting not happening?
set +e
echo "===1. SELF-BRAND CONTENT QUEUE (is content even being GENERATED?)==="
docker exec leadgen_app sh -c 'ls -la data/content_queue/ 2>/dev/null | head -12'
echo "--- self queue line count + last item ---"
docker exec leadgen_app sh -c 'wc -l data/content_queue/leadgenai-self.jsonl 2>/dev/null; tail -1 data/content_queue/leadgenai-self.jsonl 2>/dev/null | head -c 400'; echo

echo "===2. POSTIZ CONFIG (publishing gate)==="
for v in POSTIZ_API_KEY POSTIZ_API_URL POSTIZ_INTEGRATIONS AUTO_SEED_SELF CONTENT_APPROVAL_AUTO SOCIAL_AUTO_PUBLISH; do
  val=$(docker exec leadgen_app printenv "$v" 2>/dev/null)
  if [ -z "$val" ]; then echo "  $v = <unset>"; else
    case "$v" in *KEY*|*TOKEN*) echo "  $v = <set, ${#val} chars>";; *) echo "  $v = $val";; esac
  fi
done

echo "===3. postiz_publish.enabled() live==="
docker exec leadgen_app python3 -c "from app.marketing import postiz_publish as p; print('enabled=', p.enabled()); print('base=', p._base()); print('key_len=', len(p._key() or ''))" 2>&1 | grep -v '"level"'

echo "===4. IS POSTIZ ITSELF REACHABLE?==="
curl -s -o /dev/null -w '  postiz(host 5000?) -> %{http_code}\n' -m 8 http://127.0.0.1:5000 2>/dev/null
docker port leadgen_postiz 2>/dev/null | head -3
docker exec leadgen_app sh -c 'curl -s -o /dev/null -w "  app->postiz:3000 -> %{http_code}\n" -m 8 http://postiz:3000 2>/dev/null'

echo "===5. SCHEDULER JOBS mentioning content/post==="
docker logs --since 24h leadgen_scheduler 2>&1 | grep -oiE "due task [a-z0-9_-]*(content|post|social)[a-z0-9_-]*" | sort | uniq -c | head

echo "===6. ANY PUBLISH ATTEMPTS IN LOGS?==="
docker logs --since 24h leadgen_worker 2>&1 | grep -ciE "postiz|publish"
docker logs --since 24h leadgen_worker 2>&1 | grep -iE "postiz|publish" | tail -4

echo "===7. SELF CLIENT RECORD==="
docker exec leadgen_app python3 -c "
from app.marketing import clients_store
for c in clients_store.list_clients() or []:
    if str(c.get('id'))=='leadgenai-self':
        print({k:c.get(k) for k in ('id','business_name','status','plan','niche','postiz_integrations')})
" 2>&1 | grep -v '"level"'
echo "===POSTING_DONE==="
