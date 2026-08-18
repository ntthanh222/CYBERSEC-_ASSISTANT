# 08 — Test strategy

## Pyramid

1. Unit test.
2. Repository/service integration.
3. API contract/auth/authorization.
4. Docker integration.
5. Browser E2E.
6. Restart/persistence/stability.
7. Security and dependency audit.

## Các matrix bắt buộc cuối dự án

- Register → login → reload → new tab.
- `/api/auth/me` 503 giữ session.
- `/api/auth/me` 401 xóa session.
- Wrong password.
- Disabled account.
- User cannot access admin.
- Analyst read-only.
- Admin cannot alter Super Admin trái policy.
- URL public.
- localhost/127.0.0.1/metadata IP/redirect private.
- Password checker weak/medium/strong và không network request.
- CVE valid/invalid/external API unavailable.
- Asset CRUD/IDOR/import/export.
- Alert → Incident → assignee → playbook → timeline → export.
- Digest raw data và AI unavailable.
- News empty/error/refresh/persistence.
- Crawler completed/partial/failed/stale.
- Responsive, console, network, no duplicate charts.
- Docker restart và data persistence.

## Không che test flaky

Không:

- retry vô hạn;
- sleep tùy tiện;
- tăng timeout mù quáng;
- bỏ assertion;
- skip không có lý do.

## Gate

```text
Backend PASS
Frontend PASS
Rasa PASS
Environment PASS
Playwright PASS
Security checks PASS
Exit code 0
```

Mẫu bằng chứng: `templates/TEST_EVIDENCE_TEMPLATE.md`.
