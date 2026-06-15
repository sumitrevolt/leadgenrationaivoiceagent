// =============================================================================
// smoke.js — k6 smoke test (1-2 VUs, ~30s). Quick "kuch toot to nahi gaya"
// sanity check. Sirf SAFE, read-only, no-LLM GET endpoints (koi side-effect ya
// free-LLM quota burn nahi). Staging pe chalao (run.sh default :8001).
//
//   BASE_URL=http://localhost:8000 k6 run smoke.js
//   (ya:)  bash tests/load/run.sh smoke
// =============================================================================
import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";

// Naye endpoint add karne ho to yahan daalo (sirf read-only/no-LLM rakhna).
const ENDPOINTS = [
  "/health", // liveness (no deps)
  "/health/ready", // readiness -> DB + Redis (pool ko bhi chhuata)
  "/api/data/niches?tier=A", // DB/static read
  "/robots.txt", // SEO static
  "/sitemap.xml", // SEO static
];

export const options = {
  vus: Number(__ENV.VUS || 2),
  duration: __ENV.DURATION || "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"], // <1% errors warna RED
    "http_req_duration{kind:health}": ["p(95)<500"],
    http_req_duration: ["p(95)<800"],
  },
};

export default function () {
  for (const path of ENDPOINTS) {
    const tags = { ep: path, kind: path.startsWith("/health") ? "health" : "page" };
    const res = http.get(`${BASE_URL}${path}`, { tags });
    check(res, {
      [`${path} -> status<400`]: (r) => r.status > 0 && r.status < 400,
    });
  }
  sleep(1);
}
