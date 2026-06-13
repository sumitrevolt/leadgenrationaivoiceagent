/**
 * loadtest_k6.js — k6 load test for leadsgenai.in
 *
 * HOW TO RUN (VPS ya local dono se):
 *   k6 run scripts/loadtest_k6.js
 *   k6 run -e BASE_URL=http://127.0.0.1:8000 scripts/loadtest_k6.js   # internal VPS
 *   k6 run -e BASE_URL=https://leadsgenai.in scripts/loadtest_k6.js    # external prod
 *
 * Install k6:  https://k6.io/docs/getting-started/installation/
 *   Linux/VPS:  sudo apt install k6  OR  snap install k6
 *   Windows:    winget install k6
 *
 * Output: terminal summary + optional InfluxDB/Grafana (k6 run --out influxdb=...)
 *
 * Thresholds (FAIL agar in se zyada):
 *   - p(95) response time < 1500ms
 *   - error rate < 2%
 *
 * Ramp plan: 0 -> 50 VUs in 30s, hold 60s, ramp down 30s (~2 min total)
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const BASE_URL = __ENV.BASE_URL || "https://leadsgenai.in";

// Custom metrics — endpoint-wise latency breakdown ke liye
const healthLatency  = new Trend("latency_health",  true);
const nichesLatency  = new Trend("latency_niches",  true);
const auditLatency   = new Trend("latency_audit",   true);
const homeLatency    = new Trend("latency_home",    true);
const errorRate      = new Rate("custom_error_rate");

// ---------------------------------------------------------------------------
// k6 options — ramp 0→50→0 over ~2 min
// ---------------------------------------------------------------------------
export const options = {
  stages: [
    { duration: "30s", target: 50 },  // ramp up
    { duration: "60s", target: 50 },  // sustain load
    { duration: "30s", target: 0  },  // ramp down
  ],
  thresholds: {
    // SLA: 95th percentile < 1.5s, error rate < 2%
    http_req_duration: ["p(95)<1500"],
    http_req_failed:   ["rate<0.02"],
    // Agar custom_error_rate bhi track karna ho:
    custom_error_rate: ["rate<0.02"],
  },
};

// ---------------------------------------------------------------------------
// Default function — har VU har iteration me yeh chalata hai
// ---------------------------------------------------------------------------
export default function () {
  const params = {
    headers: { "Accept": "text/html,application/json" },
    timeout: "10s",
  };

  // 1. GET /health — lightest endpoint, hamesha sabse fast hona chahiye
  {
    const res = http.get(`${BASE_URL}/health`, params);
    healthLatency.add(res.timings.duration);
    const ok = check(res, {
      "/health status 200": (r) => r.status === 200,
    });
    errorRate.add(!ok);
  }

  sleep(0.2);  // slight jitter between requests within same VU

  // 2. GET /api/data/niches — DB-backed JSON, common dashboard call
  {
    const res = http.get(`${BASE_URL}/api/data/niches`, params);
    nichesLatency.add(res.timings.duration);
    const ok = check(res, {
      "/api/data/niches status 2xx": (r) => r.status >= 200 && r.status < 300,
      "/api/data/niches has json body": (r) => r.body && r.body.length > 2,
    });
    errorRate.add(!ok);
  }

  sleep(0.2);

  // 3. GET /audit — public lead-magnet page (HTML render)
  {
    const res = http.get(`${BASE_URL}/audit`, params);
    auditLatency.add(res.timings.duration);
    const ok = check(res, {
      "/audit status 200": (r) => r.status === 200,
    });
    errorRate.add(!ok);
  }

  sleep(0.2);

  // 4. GET / — landing page (static-ish, heaviest HTML)
  {
    const res = http.get(`${BASE_URL}/`, params);
    homeLatency.add(res.timings.duration);
    const ok = check(res, {
      "/ status 200": (r) => r.status === 200,
    });
    errorRate.add(!ok);
  }

  // VU ke beech random think-time (realistic user pacing)
  sleep(Math.random() * 1 + 0.5);  // 0.5s–1.5s
}

// ---------------------------------------------------------------------------
// handleSummary — test ke baad terminal me clean summary
// ---------------------------------------------------------------------------
export function handleSummary(data) {
  const p95     = (data.metrics.http_req_duration?.values?.["p(95)"] || 0).toFixed(0);
  const errRate = ((data.metrics.http_req_failed?.values?.rate || 0) * 100).toFixed(2);
  const reqs    = data.metrics.http_reqs?.values?.count || 0;
  const passed  = data.state?.testRunDurationMs
    ? data.metrics.http_req_duration?.values?.["p(95)"] < 1500 && data.metrics.http_req_failed?.values?.rate < 0.02
    : "unknown";

  console.log("\n========== LOAD TEST SUMMARY ==========");
  console.log(`BASE_URL       : ${BASE_URL}`);
  console.log(`Total requests : ${reqs}`);
  console.log(`p95 latency    : ${p95}ms  (threshold <1500ms)`);
  console.log(`Error rate     : ${errRate}%  (threshold <2%)`);
  console.log(`RESULT         : ${passed === true ? "PASS ✓" : passed === false ? "FAIL ✗" : "see thresholds above"}`);
  console.log("========================================\n");

  // JSON output bhi chahiye to:  k6 run --summary-export=scripts/loadtest_results.json ...
  return {};
}
