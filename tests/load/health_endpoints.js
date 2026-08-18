// k6 load test for the two health endpoints.
//
// Usage (via the official k6 Docker image, no local k6 install needed):
//   docker run --rm --network=host -e BASE_URL=http://localhost:8000 \
//     -e K6_SCENARIO=smoke -v "$(pwd)/tests/load:/scripts" \
//     grafana/k6 run /scripts/health_endpoints.js
//
// K6_SCENARIO selects the stage profile: smoke | vus50 | vus100 | vus200.
// BASE_URL defaults to http://localhost:8000 (the backend, not the nginx
// proxy) so results reflect the backend directly.
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const SCENARIO = __ENV.K6_SCENARIO || "smoke";

// /api/system/health does real dependency probes (Postgres + Redis round
// trips) on every call, so it is expected to be meaningfully slower than
// the dependency-free /health liveness probe — the threshold reflects the
// design, not a bug. Widening this further would hide a real regression.
const healthDuration = new Trend("health_duration_ms", true);
const systemHealthDuration = new Trend("system_health_duration_ms", true);
const healthFailRate = new Rate("health_failed");
const systemHealthFailRate = new Rate("system_health_failed");

const STAGE_PROFILES = {
  smoke: [
    { duration: "10s", target: 2 },
    { duration: "10s", target: 2 },
    { duration: "5s", target: 0 },
  ],
  vus50: [
    { duration: "15s", target: 50 },
    { duration: "30s", target: 50 },
    { duration: "15s", target: 0 },
  ],
  vus100: [
    { duration: "20s", target: 100 },
    { duration: "40s", target: 100 },
    { duration: "20s", target: 0 },
  ],
  vus200: [
    { duration: "30s", target: 200 },
    { duration: "45s", target: 200 },
    { duration: "30s", target: 0 },
  ],
};

export const options = {
  stages: STAGE_PROFILES[SCENARIO],
  thresholds: {
    "health_failed": ["rate<0.01"],
    "health_duration_ms": ["p(95)<500"],
    "system_health_failed": ["rate<0.05"],
    "system_health_duration_ms": ["p(95)<1500"],
  },
};

export default function () {
  const healthRes = http.get(`${BASE_URL}/health`, { tags: { endpoint: "health" } });
  healthDuration.add(healthRes.timings.duration);
  healthFailRate.add(healthRes.status !== 200);
  check(healthRes, { "health: status 200": (r) => r.status === 200 });

  const systemRes = http.get(`${BASE_URL}/api/system/health`, {
    tags: { endpoint: "system_health" },
  });
  systemHealthDuration.add(systemRes.timings.duration);
  systemHealthFailRate.add(systemRes.status !== 200);
  check(systemRes, { "system health: status 200": (r) => r.status === 200 });

  sleep(0.2);
}
