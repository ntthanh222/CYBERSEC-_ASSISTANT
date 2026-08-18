# 02 — Kiến trúc mục tiêu

## Canonical runtime cuối

```text
Browser
  │
  ▼
Frontend (Nginx + HTML/CSS/Vanilla JS)
  │ REST
  ▼
FastAPI Backend
  ├── Auth/RBAC
  ├── Dashboard/Health
  ├── Chatbot Orchestrator
  ├── URL/CVE/Asset/Vulnerability
  ├── Alert/Incident/Playbook
  ├── Digest/News/Admin/Reports
  ├── PostgreSQL + pgvector
  ├── Redis
  ├── ChromaDB
  ├── Rasa ── Rasa Actions
  └── Crawler
```

## Quy tắc kiến trúc

- Một `application` layer chứa use case.
- API route chỉ validate, authorize và gọi service.
- Repository chịu trách nhiệm persistence.
- Schema Pydantic tách request/response.
- Không để response model làm mất field mới.
- Một chatbot orchestrator dùng chung cho POST và streaming.
- Một nguồn crawler config.
- Một canonical Docker Compose.
- Alembic/migration runner cho volume đã tồn tại.
- Request ID xuyên suốt frontend → backend → log/audit.
- Health đơn giản cho Docker; health chi tiết cho admin.
- External providers qua adapter, timeout, circuit breaker và honest metadata.

## Phase 1

Chỉ gồm:

```text
frontend
backend
postgres
redis
```

Các service Rasa/ChromaDB/crawler chỉ được thêm đúng phase.
