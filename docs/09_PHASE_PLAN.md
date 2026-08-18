# 09 — Phase plan

## Phase 0 — Chuẩn bị

Repo, README, env example, Compose, CI, conventions, acceptance checklist.

## Phase 1 — Skeleton

Frontend static, FastAPI, PostgreSQL, Redis, health, logging, request ID, Docker.

## Phase 2 — Auth + RBAC

User model, password hashing, JWT, register/login/me, roles, demo accounts, unit/E2E.

## Phase 3 — Dashboard

Stats API, charts, responsive, honest data, no duplicate chart.

## Phase 4 — Tools

URL Scanner, SSRF defense, Password Checker local, CVE Lookup, tab UI.

## Phase 5 — Chatbot

Rasa, one orchestrator, Fast/Deep, RAG, Gemini optional, memory, summary, cache.

## Phase 6 — Vulnerability Center

Asset CRUD, Asset-CVE, Watchlist, risk score, patch status, exploit evidence, import/export.

## Phase 7 — SOC

Alert, Incident, assignment, Playbook, Timeline, export, audit.

## Phase 8 — Digest

6-section aggregation, AI rewrite optional, error/empty states.

## Phase 9 — News/Crawler

One config, scheduler, real crawler, cache, admin controls, health.

## Phase 10 — Security hardening

Rate limit, CORS, IDOR, SSRF, headers, secrets, dependency audit, audit logs.

## Phase 11 — Verification

Unit/integration/E2E, stability loops, responsive, console/network, restart, persistence, cleanup, tag.

## Quy tắc

Chỉ một phase active. Phase tiếp theo không bắt đầu nếu phase hiện tại chưa có report, test evidence, clean commit và acceptance exit `0`.
