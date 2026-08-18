# 04 — API contract baseline

Tên route có thể điều chỉnh, nhưng semantics, authorization và test không được thay đổi tùy tiện.

## Auth

```text
POST /api/auth/register
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
```

## Admin users/audit

```text
GET   /api/admin/users
PATCH /api/admin/users/{id}/role
PATCH /api/admin/users/{id}/status
GET   /api/admin/audit-logs
```

## Chatbot

```text
POST /api/chatbot/chat
POST /api/chatbot/deep-analysis
GET  /api/chatbot/history
GET  /api/system/ai-health
```

## Tools/CVE

```text
POST   /api/tools/url-scan
GET    /api/cves/{cve_id}
GET    /api/cves/watchlist
POST   /api/cves/watchlist
DELETE /api/cves/watchlist/{id}
```

Password Checker không có endpoint nhận mật khẩu.

## Assets

```text
GET    /api/assets
POST   /api/assets
GET    /api/assets/{id}
PATCH  /api/assets/{id}
DELETE /api/assets/{id}
```

## Alerts/Incidents

```text
GET   /api/alerts
POST  /api/alerts
PATCH /api/alerts/{id}
POST  /api/alerts/{id}/convert-to-incident

GET   /api/incidents
POST  /api/incidents
GET   /api/incidents/{id}
PATCH /api/incidents/{id}
PATCH /api/incidents/{id}/assignee
POST  /api/incidents/{id}/playbooks
GET   /api/incidents/{id}/timeline
GET   /api/incidents/{id}/export/json
GET   /api/incidents/{id}/export/html
```

## Digest/News/Crawler/System

```text
GET  /api/digest
POST /api/digest/ai-rewrite
GET  /api/news
POST /api/admin/crawler/trigger
GET  /api/admin/crawler/status
PATCH /api/admin/crawler/config

GET /health
GET /api/system/health
GET /api/system/ai-health
GET /api/system/crawler-health
```

## Semantics bắt buộc

- `401`: không xác thực/token không hợp lệ.
- `403`: đã xác thực nhưng không đủ quyền hoặc disabled.
- `404`: resource không tồn tại hoặc không được phép biết sự tồn tại theo policy.
- `409`: xung đột như duplicate registration.
- `422`: validation.
- `429`: rate limit.
- `500/503`: lỗi hệ thống tạm thời; frontend không tự xóa session.
- Mọi response lỗi có `request_id`, message an toàn và không lộ stack/secret.

Danh sách route cũ để tham khảo nằm tại `reference/OLD_PROJECT_API_ROUTES.csv`.
