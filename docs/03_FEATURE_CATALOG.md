# 03 — Danh mục chức năng mục tiêu

| ID | Chức năng | Vai trò chính | Phase |
|---|---|---|---|
| AUTH-001 | Register/login/logout/me/session | all | 2 |
| AUTH-002 | RBAC + disabled account | all | 2 |
| DASH-001 | Dashboard số liệu thật | authorized | 3 |
| TOOL-URL-001 | URL Scanner + SSRF defense | user | 4 |
| TOOL-PASS-001 | Password Checker trong browser | user | 4 |
| CVE-001 | CVE Lookup | user | 4 |
| CVE-002 | CVE Watchlist | user | 6 |
| AI-001 | Rasa intent routing | user | 5 |
| AI-002 | RAG/ChromaDB | user/admin | 5 |
| AI-003 | Gemini optional + honest metadata | user | 5 |
| ASSET-001 | Asset CRUD/import/export | analyst/admin | 6 |
| VULN-001 | Asset-CVE/risk/patch/exploit evidence | analyst/admin | 6 |
| ALERT-001 | Alert lifecycle | analyst/admin | 7 |
| INCIDENT-001 | Incident/assignment/timeline | analyst/admin | 7 |
| PLAYBOOK-001 | Incident playbooks | analyst/admin | 7 |
| DIGEST-001 | 6-section digest | authorized | 8 |
| NEWS-001 | News list/search/filter | user | 9 |
| CRAWLER-001 | Crawl/schedule/config/status | admin | 9 |
| ADMIN-001 | User/crawler/RAG/system/audit | admin | 2–9 |
| SEC-001 | Rate limit/CORS/IDOR/headers/secrets | all | 10 |
| VERIFY-001 | Unit/integration/E2E/restart/persistence | all | 11 |

Mỗi ID phải được liên kết với API, UI, dữ liệu, test và Definition of Done.
