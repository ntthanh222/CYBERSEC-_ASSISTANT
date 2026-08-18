# 05 — Data model mục tiêu

## Bảng cốt lõi

```text
users
profiles
assets
cves
asset_cves
cve_watchlist
alerts
incidents
playbooks
incident_playbooks
incident_timeline
news
crawler_runs
audit_logs
api_usage_tracking
chatbot_history
rag_documents
```

## Quy tắc

- UUID nhất quán.
- Tất cả timestamp dùng timezone.
- Migration idempotent ở mức phù hợp nhưng phải có version.
- Không dựa chỉ vào `/docker-entrypoint-initdb.d`.
- Dùng migration runner/Alembic sau khi service database healthy.
- Foreign key và index cho đường truy vấn chính.
- JSON chỉ dùng cho metadata linh hoạt; field nghiệp vụ quan trọng phải có cột rõ.
- Không lưu password, token, API key hoặc secret vào history/audit.
- Chat content phải redacted trước khi lưu.
- Risk score phải lưu cả score và factors/explanation.
- `crawler_runs` phải hỗ trợ `running/completed/partial/failed`.
- Audit log lưu actor, action, target, before/after, request ID và timestamp.

## Nguồn cũ

Schema cũ có giá trị tham khảo trong:

```text
reference/old_project_key_files/backend/database/models.py
reference/OLD_PROJECT_REPOMIX.md
```

Không copy nguyên migrations cũ vì có legacy Supabase/RLS assumptions.
