// 30-minute soak test for the local-final-hardening acceptance bar (Section
// XIV): a light, steady, realistic mix of read/write endpoints against a
// single already-authenticated local session, run once and left alone -
// no container restarts, no concurrent Playwright resilience run, no new
// per-iteration documents/conversations (that would itself create "orphan"
// looking data over a 30-minute run; this reuses one conversation and one
// document for the whole soak instead).
//
// Usage (k6 Docker image, no local k6 install needed):
//   docker run --rm --network=host -e BASE_URL=http://localhost:8102 \
//     -v "$(pwd)/tests/load:/scripts" grafana/k6 run /scripts/soak_mixed.js
import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const DURATION = __ENV.SOAK_DURATION || "30m";
const VUS = Number(__ENV.SOAK_VUS || 3);

const reqDuration = new Trend("soak_request_duration_ms", true);
const reqFailRate = new Rate("soak_request_failed");
const requestCount = new Counter("soak_requests_total");

export const options = {
  scenarios: {
    soak: {
      executor: "constant-vus",
      vus: VUS,
      duration: DURATION,
    },
  },
  thresholds: {
    soak_request_failed: ["rate<0.01"],
  },
};

let conversationId = null;
let documentTitle = null;

export function setup() {
  // POST /api/auth/local-session (the anonymous zero-credential session)
  // now 404s by design once Demo Mode is active - see
  // backend/config/settings.py::allow_local_mode. Log in as the real
  // seeded demo_user account instead, same as every other final-hardening
  // gate now does.
  const demoPassword = __ENV.DEMO_USER_PASSWORD;
  if (!demoPassword) {
    throw new Error("FAIL_CONFIG: DEMO_USER_PASSWORD env var not provided to the soak runner.");
  }
  const sessionRes = http.post(
    `${BASE_URL}/api/auth/local-login`,
    JSON.stringify({ username: "demo_user", password: demoPassword }),
    { headers: { "Content-Type": "application/json" } },
  );
  if (sessionRes.status !== 200) {
    throw new Error(`local-login failed: ${sessionRes.status} ${sessionRes.body}`);
  }
  const token = sessionRes.json("access_token");
  const authHeaders = { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };

  const marker = `soak-${Date.now()}`;
  const uploadRes = http.post(
    `${BASE_URL}/api/knowledge/documents`,
    {
      file: http.file(
        `Soak test marker document. Unique id: ${marker}. Long enough to chunk and embed for retrieval during the soak.`,
        `${marker}.txt`,
        "text/plain",
      ),
    },
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (uploadRes.status !== 201) {
    throw new Error(`seed upload failed: ${uploadRes.status} ${uploadRes.body}`);
  }
  const title = uploadRes.json("document.title");

  const convRes = http.post(
    `${BASE_URL}/api/chatbot/conversations`,
    JSON.stringify({ title: "soak-conversation" }),
    { headers: authHeaders },
  );
  if (convRes.status !== 201) {
    throw new Error(`seed conversation failed: ${convRes.status} ${convRes.body}`);
  }

  return { token, conversationId: convRes.json("id"), marker, documentTitle: title };
}

export default function (data) {
  const headers = { Authorization: `Bearer ${data.token}`, "Content-Type": "application/json" };

  const calls = [
    () => http.get(`${BASE_URL}/health`, { tags: { endpoint: "health" } }),
    () => http.get(`${BASE_URL}/api/system/health`, { tags: { endpoint: "system_health" } }),
    () =>
      http.get(`${BASE_URL}/api/knowledge/documents`, {
        headers,
        tags: { endpoint: "list_documents" },
      }),
    () =>
      http.get(`${BASE_URL}/api/chatbot/conversations`, {
        headers,
        tags: { endpoint: "list_conversations" },
      }),
    () =>
      http.get(
        `${BASE_URL}/api/chatbot/conversations/${data.conversationId}/messages`,
        { headers, tags: { endpoint: "get_messages" } },
      ),
    () =>
      http.post(
        `${BASE_URL}/api/chatbot/chat`,
        JSON.stringify({
          conversation_id: data.conversationId,
          message: `soak check - what is the marker ${data.marker}?`,
        }),
        { headers, tags: { endpoint: "chat" } },
      ),
    () =>
      http.post(
        `${BASE_URL}/api/tools/url-scan`,
        JSON.stringify({ url: "https://example.com" }),
        { headers, tags: { endpoint: "url_scan" } },
      ),
    () =>
      http.post(
        `${BASE_URL}/api/tools/password-check`,
        JSON.stringify({ password: "Soak-Test-Passw0rd!" }),
        { headers, tags: { endpoint: "password_check" } },
      ),
  ];

  const call = calls[Math.floor(Math.random() * calls.length)];
  const res = call();

  requestCount.add(1);
  reqDuration.add(res.timings.duration);
  const ok = res.status >= 200 && res.status < 300;
  reqFailRate.add(!ok);
  check(res, { "status is 2xx": () => ok });

  sleep(1 + Math.random() * 2);
}
