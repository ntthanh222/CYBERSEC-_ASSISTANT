# Phase 2 Frontend Integration Guide

For Antigravity (or anyone replacing `frontend/src/data/fixture-data-provider.ts`
in the `implement_figma_frontend_ui` branch's UI with real backend calls). Full
endpoint contract: [`PHASE_2_API_CONTRACT.md`](PHASE_2_API_CONTRACT.md).

This backend was **not** built by copying the UI's fixture field names — it
follows the backend's own established conventions (see `docs/API.md`,
`docs/05_DATA_MODEL.md`) and the project's committed API baseline
(`docs/04_API_CONTRACT_BASELINE.md`). Every place that diverges from the
fixture types is listed below explicitly, read-only, without modifying any
frontend file.

## What changed, at a glance

| Fixture provider method | Real endpoint | Method |
|---|---|---|
| `getChatThreads()` | `GET /api/chatbot/conversations` then `GET /api/chatbot/conversations/{id}/messages` per thread | GET |
| `getChatThreadById(id)` | `GET /api/chatbot/conversations/{id}` + `GET /api/chatbot/conversations/{id}/messages` | GET |
| *(no send method existed)* | `POST /api/chatbot/chat` | POST |
| `getUrlScanResult(url)` | `POST /api/tools/url-scan` | POST |
| `getPasswordFeedback(strength)` | `GET /api/tools/password-guidance?strength=...` | GET |
| *(no password-check call existed — UI computes strength locally)* | `POST /api/tools/password-check` (optional server-side confirmation only; the UI's local computation remains correct standalone) | POST |
| `getScanHistory()` | `GET /api/tools/scan-history` | GET |
| *(no CVE fetch existed — `CVELookupView` imports `mockCVEs` directly)* | `GET /api/cves/{cve_id}`, `GET /api/cves/search?q=...` | GET |

## Field-name deltas (fixture type → backend field)

The backend intentionally uses different, more explicit names in several
places. Every adapter function needs a mapping layer — do not assume the
backend echoes the fixture's field names.

### Chat / `AIMessage` → chat response / message record

| Fixture (`AIMessage`) | Backend | Note |
|---|---|---|
| `sender: 'user' \| 'assistant'` | `role: "user" \| "assistant" \| "system"` | Rename. Backend also allows `"system"` (unused by this phase). |
| `timestamp: string` | `created_at: string` | Rename only; both are ISO-8601. |
| `confidence` | *(absent)* | Not modeled — see "What is intentionally not implemented" below. |
| `sources`, `mitre_techniques`, `suggested_actions` | *(absent from the typed response — may appear inside `metadata` in a later phase)* | Do not render these fields against this backend; they will always be empty/undefined. |
| *(none)* | `provider: string` | New. `"local"` when the built-in knowledge base answered — **never render this as "Gemini" or any external brand**; only show a model name when `provider !== "local"`. |
| *(none)* | `intent: string` | New. One of the six enum values in the contract doc. |
| *(none)* | `metadata: object` | New. Contains `mode`, `routing_reason`, `external_provider_configured`, `rag_ready`, `rag_documents`. Use `metadata.external_provider_configured === false` to render the "degraded" (local-knowledge) state distinctly from an error. |

### `ChatSession` / `ChatThread`

`is_pinned` does not exist on the backend (`Conversation` has no such
column) — keep it as client-only local state exactly as the current UI
already does; there is no persistence to wire it to yet.

### `URLScanResult`

| Fixture | Backend | Note |
|---|---|---|
| `domain_age`, `registrar`, `country`, `tls_version`, `tls_issuer` | *(absent)* | Not implemented — this backend does not do WHOIS/registrar/geolocation/TLS-certificate lookups. Render these fields as unavailable/omitted rather than blank; do not fabricate placeholder values. |
| `reputation_sources` (VirusTotal / Google Safe Browsing / etc.) | *(absent)* | No third-party reputation feed is wired in this phase (`VIRUSTOTAL_API_KEY` is declared but unused). |
| `status: 'safe' \| 'suspicious' \| 'critical' \| 'blocked'` | `status: "safe" \| "suspicious" \| "critical" \| "failed"` | **`blocked` does not exist as a status value.** A target the SSRF guard refuses is an HTTP `400` error (`error: "blocked_target"`), not a `200` response with a `blocked` status — render it as an error state, not a result card. `"failed"` (new) means the target was allowed but could not be reached (timeout/DNS/refused) — render this distinctly from both "safe" and an SSRF block. |
| `phishing_indicators: string[]`, `evidence: string[]` | `findings: {code, severity, message, weight}[]` | Structured, not flat strings. `findings.map(f => f.message)` reproduces roughly the old flat-string UI if a quick port is wanted; the structured form (code + severity + weight) is available for a richer render. |
| *(none)* | `id`, `created_at` | New — every scan is now a persisted record with these fields, matching a `ScanHistoryItem`. |
| *(none)* | `reachable: boolean`, `failure_reason: string \| null`, `body_truncated: boolean` | New, needed to render the "failed" status correctly. |

### `PasswordStrengthResult`

The fixture type and the backend's `password-check` response are similar but
not identical:

| Fixture | Backend | Note |
|---|---|---|
| `crack_time: string` | `crack_time: string` | Same name, same purpose. |
| `feedback: string` | *(absent from `password-check`; present on `password-guidance` as `feedback`)* | The check endpoint returns structured facts (`warnings: string[]`, `is_common`, `has_repeated_block`, etc.) instead of one paragraph; the guidance endpoint returns the paragraph. Keep computing strength client-side and call `password-guidance?strength=<bucket>` for the prose, per the existing UI's own "100% client-side" banner and the blueprint's rule that no endpoint receives the password. |
| `strength: 'weak' \| 'medium' \| 'strong' \| 'very_strong'` | same | No change. |
| `score: number // 0-4` | same | No change. |

### `Vulnerability` (CVE)

| Fixture | Backend | Note |
|---|---|---|
| `id: string` (the CVE id) | `cve_id: string` | Rename. |
| `cvss: number` | `cvss_score: number \| null` | Rename, and now nullable — NVD does not always publish a score. |
| `published_date`, `updated_date` | `published_at`, `modified_at` | Rename (`_date` → `_at`), and both nullable now. |
| `remediation?: string` | *(absent)* | Not implemented — no remediation-text generation in this phase. Use `references` (real NVD links) instead of inventing remediation copy. |
| *(none)* | `vector: string \| null` | New — the raw CVSS vector string. |
| *(none)* | `source: "nvd"`, `cached: boolean`, `fetched_at: string` | New — every response names its real source and cache status; never claim "AI scan" or similar per blueprint 16.12. |
| `affected_products: string[]` | same name, different content | Backend returns raw CPE strings (`cpe:2.3:a:apache:log4j:2.14.1:*:*:*:*:*:*:*`), not human product names — the fixture's human-readable strings (`'Apache Log4j 2.x'`) were hand-written, not sourced from NVD. A CPE-to-display-name formatter is a frontend concern if wanted. |

`CVEDetailsCard.tsx` currently hardcodes `'ACTIVE EXPLOITATION'` /
`'PATCHED'` badges by CVE id — **no backend field carries this**; that logic
either needs to be removed or fed from a future exploit/patch-tracking
feature, neither of which exists yet.

### `ScanHistoryItem`

| Fixture | Backend | Note |
|---|---|---|
| `type: 'url' \| 'password' \| 'cve'` | `scan_type: "url_scan" \| "cve_lookup"` | Renamed **and** `'password'` does not exist as a value — password checks are never recorded (stateless by design). Any UI copy implying a password-check history entry should be removed or hidden. |
| `query: string` | `target: string` | Rename. For `cve_lookup` rows this is the CVE id; for `url_scan` rows it is the normalized URL. |
| `result: string` | `summary: string` | Rename, same purpose (one-line human text). |
| `user: string` (a username) | `actor: string \| null` | The backend has no user accounts yet — `actor` is whatever the caller sent in `X-Actor` (or `"anonymous"`), not a real identity. Do not render this as a trusted username. |
| — | — | Everything else (`id`, `severity`, `timestamp`→`created_at`, `status`) maps directly, `status` values (`completed`/`failed`) match exactly. |

### Pagination — the biggest structural change

Every list fixture method (`getChatThreads`, `getScanHistory`) returns a bare
array; **every real list endpoint returns
`{items, total, page, page_size}`**. `ScanHistoryView.tsx`'s client-side
`itemsPerPage`/`totalPages`/`.slice()` logic should be replaced with real
`page`/`page_size` query params and rendering `total` from the server,
rather than fetching everything and paginating in the browser. The existing
`searchQuery`/`typeFilter`/`severityFilter` UI state maps directly onto the
`scan_type`/`status`/`severity` query params (note: fixture used `type`,
backend query param is `scan_type`).

## What is intentionally not implemented (do not stub client-side)

- **RAG / knowledge-base readiness.** `rag_ready` is always `false` and
  `rag_documents` always `0`. If the UI has a "knowledge base" indicator, it
  must render the empty/not-ready state, never a fabricated document count.
- **Reputation feeds, WHOIS, TLS certificate details, remediation text,
  exploit/patch-status badges** for the toolkit — none of these exist on any
  Phase 2 response. Render their absence rather than inventing values.
- **`confidence`, `sources`, `suggested_actions`, `mitre_techniques`** on
  chat messages — not modeled in this phase's response schema.
- **Streaming.** `POST /api/chatbot/chat` is a single request/response; there
  is no SSE/WebSocket streaming endpoint. Do not fake a typing effect that
  implies token-by-token generation from the server, per blueprint 16.12.

## Auth

No auth exists. `AuthContext.tsx`'s `login`/`logout`/session-expiry flow has
nothing to call yet — every endpoint above is reachable with no credentials.
Do not wire login to any Phase 2 endpoint; that remains a future phase.

## Verifying against a live backend

```bash
docker compose up -d --build
curl http://localhost:8000/api/system/ai-health
curl -X POST http://localhost:8000/api/chatbot/chat -H "Content-Type: application/json" -d "{\"message\":\"hello\"}"
curl -X POST http://localhost:8000/api/tools/url-scan -H "Content-Type: application/json" -d "{\"url\":\"https://example.com/\"}"
curl http://localhost:8000/api/cves/CVE-2021-44228
curl http://localhost:8000/api/tools/scan-history
```
Or browse `http://localhost:8000/docs` for interactive Swagger UI with the
live, generated schema — the source of truth if this document and the code
ever disagree.
