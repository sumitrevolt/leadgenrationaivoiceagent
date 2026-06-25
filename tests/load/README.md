# Load & Chaos Harness (k6 + Pumba)

Free, self-hosted performance + resilience testing. Yeh `SAAS_INFRA_TRUTH_AND_GAPS_2026_06_15.md`
(Appendix B — folded Scale_Reliability_Audit) ke flagged gaps bharta: **load test (R8#7), perf budget (R9#2), chaos (R9#3), automated
capacity baselines (R10#6)**. Iske numbers ke bina voice scale-up aur
**distributed call-admission counter** ki sizing andheme mein hai.

> **Rule:** hamesha **staging** pe chalao (`:8001`), prod pe nahi. `run.sh` mein
> prod-guard hai (leadsgenai.in / VPS IP pe refuse karta jab tak `CONFIRM_PROD=1`).
> Sirf read-only, no-LLM GET endpoints hit hote — koi side-effect ya free-LLM burn nahi.

## Files
- `smoke.js` — 1-2 VUs, ~30s. Quick sanity (sab endpoint 200, p95 theek).
- `load.js` — ramping VUs (capacity baseline). `/health/ready` zyada weight (DB+Redis pool = asli bottleneck).
- `run.sh` — Docker se k6 chalata (local install nahi chahiye) + prod-guard.

## Chalao (Docker — kuch install nahi karna)
```bash
# staging smoke
bash tests/load/run.sh smoke

# staging capacity test (80 concurrent, 5 min sustain)
MAX_VUS=80 SUSTAIN=5m bash tests/load/run.sh load
```
Summary `tests/load/last-<script>-summary.json` mein save hota (trend ke liye rakh sakta; gitignore karna ho to `tests/load/last-*-summary.json`).

### Bina Docker (local k6)
```bash
# install: https://k6.io/docs/get-started/installation/
BASE_URL=http://localhost:8001 MAX_VUS=80 k6 run tests/load/load.js
```

## Perf budgets (thresholds) — fail = non-zero exit (CI-gate ready)
`load.js` mein: `http_req_failed < 2%`, `p95 < 1500ms`, `p99 < 3000ms`, `endpoint_errors < 2%`.
Apne SLO ke hisaab se adjust karo. Threshold breach = k6 exit-code 99 -> CI/script RED.

## Grafana mein live dekhna (optional — teri existing Prometheus se)
k6 ka experimental Prometheus remote-write output use karo:
```bash
# Prometheus pe remote-write receiver enable karna padega:
#   prometheus --web.enable-remote-write-receiver   (ya config flag)
K6_PROMETHEUS_RW_SERVER_URL=http://host.docker.internal:9090/api/v1/write \
  k6 run --out experimental-prometheus-rw tests/load/load.js
```
Phir Grafana mein k6 dashboard import karke live RPS/latency/error dekho.

## Chaos game-day (Pumba — manual, STAGING pe)
Self-heal cron + dead-man trio actually kaam karte ya nahi — yeh test karta. **Destructive hai, sirf staging pe, manually chalao** (auto kabhi nahi).
```bash
# DB ko 20s pause -> /health/ready degrade + recovery dekho
docker run -d --rm -v /var/run/docker.sock:/var/run/docker.sock \
  gaiaadm/pumba --random --interval 30s pause --duration 20s "re2:leadgen_db"

# app pe 200ms network latency 60s
docker run -d --rm -v /var/run/docker.sock:/var/run/docker.sock \
  gaiaadm/pumba netem --duration 60s delay --time 200 "re2:leadgen_app"

# cache redis kill -> self-heal recreate verify
docker run -d --rm -v /var/run/docker.sock:/var/run/docker.sock \
  gaiaadm/pumba --random kill "re2:leadgen_redis_cache"
```
Best workflow: ek terminal mein `run.sh load` chala, doosre mein Pumba fault inject karo, phir Grafana/`/health/ready` pe recovery dekho.

## Kya target hota hai (safe endpoints)
`/health`, `/health/ready`, `/api/data/niches?tier=A`, `/robots.txt`, `/sitemap.xml`.
Naye add karne ho (e.g. `/pricing`, `/`) to `ENDPOINTS` array edit karo — **POST / auth / LLM / email-trigger endpoints kabhi mat daalo**.
