// =============================================================================
// load.js — k6 ramping load test = CAPACITY BASELINE.
// Voice scale-up + "distributed call-admission counter" sizing se PEHLE yeh
// numbers chahiye. /health/ready ko zyada weight diya kyunki woh DB+Redis pool
// ko hit karta -> asli capacity bottleneck wahi dikhta.
//
// Sirf SAFE read-only/no-LLM endpoints. STAGING pe chalao (prod nahi).
//   MAX_VUS=80 SUSTAIN=5m BASE_URL=http://localhost:8001 k6 run load.js
//   (ya:)  MAX_VUS=80 bash tests/load/run.sh load
// =============================================================================
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const MAX_VUS = Number(__ENV.MAX_VUS || 50);

const endpointErrors = new Rate("endpoint_errors");

// weight = relative hit frequency.
const ENDPOINTS = [
  { path: "/health/ready", weight: 3 }, // DB+Redis pool stress (key signal)
  { path: "/api/data/niches?tier=A", weight: 2 },
  { path: "/health", weight: 1 },
  { path: "/robots.txt", weight: 1 },
  { path: "/sitemap.xml", weight: 1 },
];
const POOL = [];
for (const e of ENDPOINTS) for (let i = 0; i < e.weight; i++) POOL.push(e.path);

export const options = {
  scenarios: {
    ramp: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: __ENV.RAMP || "1m", target: MAX_VUS }, // warm up
        { duration: __ENV.SUSTAIN || "3m", target: MAX_VUS }, // sustained peak
        { duration: "30s", target: 0 }, // ramp down
      ],
      gracefulRampDown: "15s",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.02"], // <2% errors
    http_req_duration: ["p(95)<1500", "p(99)<3000"],
    endpoint_errors: ["rate<0.02"],
  },
};

export default function () {
  const path = POOL[Math.floor(Math.random() * POOL.length)];
  const res = http.get(`${BASE_URL}${path}`, { tags: { ep: path } });
  const ok = check(res, { "status<400": (r) => r.status > 0 && r.status < 400 });
  endpointErrors.add(!ok);
  sleep(Math.random() * 0.5 + 0.2); // 0.2-0.7s think-time
}
