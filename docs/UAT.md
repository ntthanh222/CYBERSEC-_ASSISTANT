# UAT — Phase 2.7A Release Hardening

## What ran, and how

A Playwright E2E suite (`frontend/e2e/`) drives the real containerized
frontend + backend + Postgres (no mocks) in an isolated Docker Compose
project (`cybersec-phase27a-uat`, ports 8102/3102) across 3 device
projects: `desktop` (1440x900), `iphone-14-pro-max`, `ipad-air`.

```bash
cd frontend
npx playwright test e2e/ --project=desktop --project=iphone-14-pro-max --project=ipad-air
```

Authenticated journeys use `backend/scripts/uat_mint_test_session.py` to
mint a test-safe, backend-verifiable session (the repository's own
existing legacy-HS256 verification path) and
`frontend/e2e/helpers/session.ts` injects it into `localStorage` in the
exact shape the Supabase JS SDK persists after a real login — every
journey below runs against real service-layer code, not a stub. See
`PHASE_2_7A_RELEASE_HARDENING_REPORT.md` for why (a real local Supabase
CLI Auth stack was attempted first and crashed unprompted twice on this
host).

## Coverage

| File | What it proves |
|---|---|
| `auth.spec.ts` | Session restore lands on `/dashboard`; no session redirects to `/login`; session survives a full page reload; the access token never appears in visible UI text or console output. |
| `knowledge-base.spec.ts` | Upload → READY → chunk count > 0 → retrieval preview finds the marker text; a MIME-mismatched upload is rejected with no phantom row; an empty file is rejected; delete removes the row. |
| `isolation.spec.ts` | User B never sees user A's documents, scan history, or retrieval/citation content. |
| `chatbot.spec.ts` | RAG answers cite the uploaded document; a no-context question still answers without a crash; a prompt-injection instruction embedded in a document is rendered as inert text, never executed; conversation delete works. |
| `security-tools.spec.ts` | URL scanner, password checker, CVE lookup, scan history — success/invalid-input/reset/clear paths, plus unauthenticated redirect. |
| `responsive.spec.ts` | No horizontal overflow, no uncaught JS errors, across 6 key pages x 3 viewports. |
| `accessibility.spec.ts` | axe-core wcag2a/wcag2aa — zero serious/critical violations across 6 pages x 3 viewports; delete-confirmation dialog is a real `aria-modal` focus context; keyboard-only Tab navigation reaches the upload control. |
| `resilience.spec.ts` | 500/401/429 backend responses degrade to a visible error, not a crash or infinite spinner; an aborted upload creates no orphan row; a real `docker restart` of the backend recovers with session and data intact. |

## What this pass did NOT verify

- The literal register/login HTML-form round-trip against live Supabase
  Auth (GoTrue) — see the honest-gaps section of
  `PHASE_2_7A_RELEASE_HARDENING_REPORT.md`. Already verified against real
  hosted Supabase in Phase 2.5B; not re-verified here in a disposable local
  environment.
- A 30–60 minute soak window (ran 3 minutes, honestly reported).

## Re-running after a code change

The suite is the regression gate for anything touching frontend routing,
auth session handling, the Knowledge Base/chatbot/security-tool API
surface, or `frontend/Dockerfile`/`nginx.conf`. Every spec in it failed
identically (blank page, no JS loaded) before the two Docker/CSP fixes in
this phase — it would catch that class of regression again.
