# Phase 2 API Contract

Scope: AI Security Assistant + Security Toolkit (URL Scanner, Password
Checker, CVE Lookup, Scan History). This is the contract the Antigravity
frontend should code against; see
[`PHASE_2_FRONTEND_INTEGRATION.md`](PHASE_2_FRONTEND_INTEGRATION.md) for the
exact fixture-to-endpoint mapping and every field-name difference from the
existing UI's fixture types.

Interactive, always-current docs are also live at `GET /docs` (Swagger UI),
`GET /redoc`, and `GET /openapi.json`.

## Conventions (apply to every endpoint below)

- **Base URL**: same origin as Phase 1.5 (`/health`, `/api/system/health`).
  No `/v1` prefix — matches `docs/API.md` / `docs/04_API_CONTRACT_BASELINE.md`.
- **Authentication**: **none**. Every endpoint in this document is
  unprotected in the current phase. An optional `X-Actor: <name>` request
  header (matching `^[A-Za-z0-9_.@-]{1,128}$`) is accepted and echoed back as
  `actor` on records it creates; anything else, or an absent header, resolves
  to `"anonymous"`. This is **not** an authentication mechanism — see
  `docs/SECURITY.md`.
- **Content type**: `application/json` for every request body and response.
- **Timestamps**: ISO-8601, always UTC, always with an explicit offset —
  e.g. `"2026-07-29T02:15:00+00:00"`. Never a bare date, never an epoch
  number.
- **IDs**: UUID v4 strings (`"3f1d2c9a-6b4e-4d7a-9c1f-2b8e5a0d4c31"`).
- **Pagination**: every list endpoint returns
  `{"items": [...], "total": <int>, "page": <int>, "page_size": <int>}`.
  Query params: `page` (default `1`, 1-based), `page_size` (default `20`,
  max `100`). This is a real server-side envelope, not a bare array — see
  the integration guide for what that means for the existing UI code.
- **Error envelope** (identical to Phase 1.5, every non-2xx response):
  ```json
  {"error": "blocked_target", "message": "That target is not allowed to be scanned.", "request_id": "a1b2c3d4-..."}
  ```
  `message` is always safe to display; it never contains a stack trace, a
  secret, or raw upstream text. `error` is a stable machine-readable slug —
  see the per-endpoint tables below for the slugs each route can return.
- **Rate limiting**: fixed-window, per-actor (the `X-Actor` value, or
  `"anonymous"` if every caller omits it — meaning anonymous callers share
  one bucket). A limited request returns `429` with `error: "rate_limited"`.
  Limits: chat 30/min, URL scan 20/min, password check 60/min, CVE
  lookup/search 30/min.
- **Loading / error / empty / degraded states**: the UI should distinguish
  four states per screen, per `docs/07_UI_UX_REQUIREMENTS.md`:
  - **loading** — request in flight.
  - **empty** — `200` with zero items (`total: 0`) or, for the assistant, no
    conversations yet. Not an error.
  - **error** — non-2xx response; render `message` from the error envelope.
  - **degraded** — specific to the assistant: `200` with
    `metadata.external_provider_configured: false` (see below). The request
    succeeded and returned a real answer; it just came from local knowledge,
    not the external provider. Render this distinctly from a hard error.

---

## AI Security Assistant

### `POST /api/chatbot/chat`

Send a message; creates a conversation if `conversation_id` is omitted.

**Request**
```json
{"message": "What is CVE-2021-44228?", "conversation_id": null, "mode": "fast"}
```
| Field | Type | Required | Notes |
|---|---|---|---|
| `message` | string | yes | 1–4000 chars. Never put a real password/token/API key in this field — it is not sent anywhere secret-safe (see `docs/SECURITY.md`). |
| `conversation_id` | UUID \| null | no | Omit to start a new conversation. |
| `mode` | `"fast"` \| `"deep"` | no, default `"fast"` | `fast` never calls an external provider. `deep` uses the configured external provider when one exists; otherwise it silently falls back to local knowledge and reports that honestly in `metadata` — it never claims the external provider ran. |

**Response `200`**
```json
{
  "conversation_id": "3f1d2c9a-6b4e-4d7a-9c1f-2b8e5a0d4c31",
  "message_id": "8c2b1e40-5a77-4a2e-b0d1-9f6c3a5e7b12",
  "role": "assistant",
  "content": "Log4Shell (CVE-2021-44228) is a remote code execution flaw...",
  "provider": "local",
  "intent": "cve_question",
  "created_at": "2026-07-29T02:15:00+00:00",
  "request_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "metadata": {
    "mode": "fast",
    "routing_reason": "fast_mode",
    "external_provider_configured": false,
    "rag_ready": false,
    "rag_documents": 0,
    "source": "local_knowledge"
  }
}
```
`provider` names what **actually** produced `content` — `"local"` means the
built-in knowledge base answered, never an external model wearing that
label. `intent` is one of `greeting` \| `definition` \| `cve_question` \|
`url_question` \| `password_question` \| `general`. A message classified as
`password_question` is **always** answered locally and redirected to the
Password Checker tool, whatever `mode` was requested — it is never forwarded
to an external provider, in case the user pasted a real credential.

**Errors**
| Status | `error` | When |
|---|---|---|
| 400 | `invalid_request` | Empty message (whitespace-only). |
| 404 | `not_found` | `conversation_id` does not exist. |
| 422 | `validation_error` | Message >4000 chars, or malformed JSON/UUID. |
| 429 | `rate_limited` | Local rate limit exceeded. |
| 429 | `provider_rate_limited` | The external provider itself rate-limited the call. |
| 502 | `provider_unavailable` | External provider unreachable or rejected the request. |
| 502 | `upstream_malformed` | External provider returned an unparseable response. |
| 503 | `configuration_missing` | Should not surface in practice — deep mode already falls back to local instead of erroring. |
| 504 | `provider_timeout` | External provider did not respond in time. |

### `GET /api/chatbot/conversations`

Paginated, most-recently-updated first. Query: `page`, `page_size`.

```json
{"items": [{"id": "3f1d2c9a-...", "title": "Log4Shell triage", "actor": "anonymous", "created_at": "...", "updated_at": "..."}], "total": 1, "page": 1, "page_size": 20}
```

### `POST /api/chatbot/conversations`

Create an empty conversation (no messages yet) — useful when the UI wants an
id before the first turn.

**Request**: `{"title": "New conversation"}` (optional, default `"New
conversation"`, max 200 chars). **Response `201`**: same shape as one item
above. **Errors**: `400 invalid_request` (title too long), `422` (schema).

### `GET /api/chatbot/conversations/{conversation_id}`

Single conversation's metadata (no messages — use the endpoint below).
**Errors**: `404 not_found`.

### `DELETE /api/chatbot/conversations/{conversation_id}`

Deletes the conversation and, by cascade, every one of its messages. Returns
`204` with no body. **Errors**: `404 not_found`.

### `GET /api/chatbot/conversations/{conversation_id}/messages`

Paginated, chronological (oldest first). Query: `page`, `page_size`.

```json
{
  "items": [
    {"id": "...", "conversation_id": "...", "role": "user", "content": "What is CVE-2021-44228?", "provider": null, "intent": null, "metadata": null, "created_at": "..."},
    {"id": "...", "conversation_id": "...", "role": "assistant", "content": "...", "provider": "local", "intent": "cve_question", "metadata": {"mode": "fast", "...": "..."}, "created_at": "..."}
  ],
  "total": 2, "page": 1, "page_size": 20
}
```
`role` is `"user"` \| `"assistant"` \| `"system"` (system is reserved, never
produced by this phase). `content` is already redacted of secret-shaped
substrings before it was stored — a pasted API key or JWT will read as
`[REDACTED]` even in the user's own turn. **Errors**: `404 not_found`
(unknown conversation).

### `GET /api/system/ai-health`

Not versioned under `/api/chatbot` — lives alongside the existing
`/api/system/health` per Phase 1.5 convention. No auth, no rate limit.

```json
{
  "status": "degraded",
  "provider": "local",
  "provider_configured": false,
  "fallback_provider": "local",
  "rag_ready": false,
  "rag_documents": 0,
  "detail": "No external AI provider is configured (GEMINI_API_KEY is unset). The assistant answers from its local knowledge base and reports provider=local. No external call is made."
}
```
`status` is `"healthy"` when an external provider is configured and usable,
`"degraded"` otherwise — never `"unavailable"`, because the assistant always
answers from local knowledge at minimum. `rag_ready` is always `false` and
`rag_documents` always `0` in this phase (no vector store exists yet); the
frontend must not render a "knowledge base ready" state from this endpoint.

---

## Security Toolkit — URL Scanner

### `POST /api/tools/url-scan`

**Request**: `{"url": "https://example.com/login"}` (1–2048 chars, http/https
only).

**Response `200`** (target reachable and scanned):
```json
{
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "url": "https://example.com/login",
  "normalized_url": "https://example.com/login",
  "hostname": "example.com",
  "port": 443,
  "scheme": "https",
  "has_https": true,
  "reachable": true,
  "status": "safe",
  "risk_score": 5,
  "severity": "low",
  "http_status": 200,
  "final_url": "https://example.com/login",
  "redirect_chain": [],
  "redirect_count": 0,
  "headers": {"server": "cloudflare", "content-type": "text/html"},
  "body_truncated": false,
  "failure_reason": null,
  "findings": [
    {"code": "no_https", "severity": "medium", "message": "The URL uses plain HTTP...", "weight": 20}
  ],
  "recommendations": ["No specific risk indicators were found. ..."],
  "duration_ms": 184.2,
  "created_at": "2026-07-29T02:15:00+00:00"
}
```
`status` is `"safe"` \| `"suspicious"` \| `"critical"` \| `"failed"` —
**`"failed"` means the target could not be reached** (DNS/timeout/refused
connection), reported as HTTP `200` with `reachable: false` and
`failure_reason` set (`"timeout"` \| `"connection_failed"` \|
`"too_many_redirects"`), exactly like `/api/system/health`'s "never confuse
a transport failure with an API error" convention. `severity` is
`"low"`/`"medium"`/`"high"`/`"critical"`, derived from `risk_score` (0–100).
`findings` is the itemized list `risk_score` is the sum of — always render
these, never just the number, per `docs/05_DATA_MODEL.md`.

A target the SSRF guard refuses (localhost, private/loopback/link-local
ranges, the cloud metadata address, a non-http(s) scheme, an unresolvable
hostname) is a **client error, not a scan result**:

**Error `400`**
```json
{"error": "blocked_target", "message": "That target resolves to an address the scanner is not allowed to reach (loopback). Only public internet hosts can be scanned.", "request_id": "..."}
```
The message never echoes the resolved IP address. `error` is `blocked_target`
for every SSRF refusal and `invalid_request` for a malformed/unparseable URL.
Every scan attempt — reachable, unreachable, or blocked — is written to scan
history.

### `GET /api/tools/scan-history`, `GET /api/tools/scan-history/{id}`, `DELETE /api/tools/scan-history/{id}`

See **Scan History** below — URL scans are one of its two record types.

---

## Security Toolkit — Password Checker

### `POST /api/tools/password-check`

**The password is never persisted, logged, echoed back, or used as a metric
label.** No row is ever written to scan history for a password check — the
`scan_type` enum structurally excludes it.

**Request**: `{"password": "correct horse battery staple"}` (1–256 chars).

**Response `200`**
```json
{
  "strength": "very_strong",
  "score": 4,
  "length": 29,
  "entropy_bits": 155.89,
  "crack_time": "effectively forever at current attack rates",
  "has_lowercase": true, "has_uppercase": false, "has_digits": false, "has_special": false,
  "character_classes": 1,
  "longest_repeat_run": 1,
  "longest_sequential_run": 1,
  "has_repeated_block": false,
  "is_common": false,
  "warnings": [],
  "recommendations": ["Store this in a password manager and never reuse it on another account.", "Enable multi-factor authentication wherever this password is used."]
}
```
`strength` is `"weak"` \| `"medium"` \| `"strong"` \| `"very_strong"`,
`score` is `0`–`4`.

### `GET /api/tools/password-guidance?strength=<bucket>`

Static, canned advice for one of the four strength buckets — never receives a
password. Intended for a **fully client-side** password checker (per the
blueprint's "no endpoint receives the password" rule) that computes strength
locally and only fetches matching advice text by bucket name.

```json
{"strength": "weak", "headline": "This password would not survive an offline attack.", "feedback": "Short, common or highly patterned passwords are recovered in seconds...", "recommendations": ["Use at least 12 characters...", "..."]}
```
`strength` must be exactly one of `weak`/`medium`/`strong`/`very_strong`, or
the request 422s.

---

## CVE Lookup

### `GET /api/cves/{cve_id}`

`cve_id` must match `^CVE-\d{4}-\d{4,}$` (case-insensitive input, normalized
to uppercase in the response).

**Response `200`**
```json
{
  "cve_id": "CVE-2021-44228",
  "description": "Apache Log4j2 2.0-beta9 through 2.15.0 ...",
  "published_at": "2021-12-10T10:15:00+00:00",
  "modified_at": "2023-11-07T03:34:00+00:00",
  "cvss_score": 10.0,
  "severity": "critical",
  "vector": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H",
  "affected_products": ["cpe:2.3:a:apache:log4j:2.14.1:*:*:*:*:*:*:*"],
  "references": ["https://nvd.nist.gov/vuln/detail/CVE-2021-44228"],
  "source": "nvd",
  "cached": false,
  "fetched_at": "2026-07-29T02:15:00+00:00"
}
```
`cached` distinguishes a Redis cache hit (`true`) from a fresh upstream fetch
(`false`) — both return identical data, this field is purely informational
for the UI (e.g. a small "cached" badge). `severity` is
`low`/`medium`/`high`/`critical`, lowercased. Any field the upstream NVD
record did not provide is `null`, never fabricated.

**Errors**
| Status | `error` | When |
|---|---|---|
| 400 | `invalid_request` | `cve_id` fails the format check. |
| 404 | `not_found` | Well-formed id, not found in NVD. |
| 429 | `rate_limited` \| `provider_rate_limited` | Local limit, or NVD's own. |
| 502 | `upstream_malformed` | NVD returned an unparseable response. |
| 502 | `provider_unavailable` | NVD unreachable or returned a 4xx we can't otherwise map. |
| 504 | `provider_timeout` | NVD did not respond in time. |

No provider-not-configured state exists for this endpoint — the NVD API
answers anonymous requests (just at a lower rate limit), so it is always
"configured" whether or not `NIST_NVD_API_KEY` is set.

### `GET /api/cves/search?q=<query>&limit=<n>`

Free-text keyword search against NVD. `q` required (1–200 chars), `limit`
optional (default 10, max 50). **Not cached** — every call reaches upstream.

```json
{"query": "log4j", "results": [{"cve_id": "CVE-2021-44228", "...": "..."}], "count": 1}
```
Each item in `results` has the identical shape as the single-lookup response
above, with `cached: false` always. **Errors**: same table as single lookup,
plus `422` if `q` is missing/empty.

---

## Scan History

Records every URL scan and CVE lookup (**not** password checks — see above).

### `GET /api/tools/scan-history`

Query params: `page`, `page_size`, `scan_type` (`url_scan` \| `cve_lookup`),
`status` (`completed` \| `failed`), `severity`
(`low`/`medium`/`high`/`critical`), `sort` (`asc` \| `desc`, default `desc`
by `created_at`).

```json
{
  "items": [
    {
      "id": "7c9e6679-...", "scan_type": "url_scan", "target": "https://example.com/",
      "status": "completed", "risk_score": 5, "severity": "low",
      "summary": "safe (risk 5)", "actor": "anonymous", "created_at": "..."
    }
  ],
  "total": 1, "page": 1, "page_size": 20
}
```
`target` is a URL for `url_scan` rows and a CVE id for `cve_lookup` rows —
never a password fragment. `summary` is a one-line human string; `actor` is
the caller-supplied `X-Actor` value or `"anonymous"`.

### `GET /api/tools/scan-history/{id}`

Same shape plus `details` (an object): the structured findings/factors
behind the summary (`{"findings": [...], "recommendations": [...]}` for a URL
scan; `{"source": "nvd", "cached": false}` for a CVE lookup). **Errors**:
`404 not_found`.

### `DELETE /api/tools/scan-history/{id}`

Returns `204` with no body. Emits an audit event. **Errors**: `404
not_found`.

---

## Enums (exhaustive, backend-emitted)

| Concept | Values |
|---|---|
| message role | `user`, `assistant`, `system` |
| chat mode | `fast`, `deep` |
| intent | `greeting`, `definition`, `cve_question`, `url_question`, `password_question`, `general` |
| URL scan status | `safe`, `suspicious`, `critical`, `failed` |
| password strength | `weak`, `medium`, `strong`, `very_strong` |
| scan history type | `url_scan`, `cve_lookup` |
| scan history status | `completed`, `failed` |
| severity (URL scan / CVE / scan history) | `low`, `medium`, `high`, `critical` |
| error slugs | `invalid_request`, `not_found`, `rate_limited`, `configuration_missing`, `provider_unavailable`, `provider_timeout`, `provider_rate_limited`, `upstream_malformed`, `blocked_target`, `http_error`, `validation_error`, `internal_server_error` |

## Environment variables this contract depends on

| Var | Effect if unset |
|---|---|
| `GEMINI_API_KEY` | Assistant `deep` mode falls back to local knowledge; `/api/system/ai-health` reports `degraded`. Core stack still runs. |
| `NIST_NVD_API_KEY` | CVE lookup still works (lower anonymous rate limit). |
| `REDIS_URL` unreachable | CVE lookups always miss the cache (still return real data); rate limiting fails open (allows all requests, logs a warning). |

None of these are required for the core stack — matching
`docs/11_ENVIRONMENT_AND_PORTS.md`'s "missing key must not fail the core
stack" rule.
