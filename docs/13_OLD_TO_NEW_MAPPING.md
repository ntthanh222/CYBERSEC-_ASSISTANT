# 13 — Mapping dự án cũ sang bản mới

| Thành phần cũ | Quyết định mới | Lý do |
|---|---|---|
| Supabase Cloud + local Postgres song song | Local PostgreSQL canonical; provider ngoài chỉ adapter tùy chọn | Tránh hai nguồn dữ liệu và demo phụ thuộc cloud |
| `chat.py` + `chatbot.py` + nhiều flow | Một chatbot orchestrator | Tránh logic POST/SSE/fallback khác nhau |
| Password endpoint + HIBP | Password Checker 100% client-side | Blueprint cấm gửi password về backend |
| `docker-entrypoint-initdb.d` là migration chính | Alembic/migration runner | Init scripts không chạy lại với volume cũ |
| In-memory user cache | DB-authoritative hoặc cache có invalidation/version | Tránh role/status stale |
| Crawler config/scheduler trùng | Một config + một scheduler + một service | Tránh trạng thái giả/chạy lệch |
| Health có field hardcode | Probe thật + unknown/degraded | Trung thực với runtime |
| Tailwind CDN runtime | CSS local/build artifact | Tránh CDN chết và CSP phức tạp |
| Prometheus/Grafana canonical | Deferred/optional | Không tăng service trước khi core ổn |
| Chroma image `latest` | Pin version đã test | Reproducible |
| Supabase RLS shim | Schema và authorization native cho local Postgres | Giảm legacy coupling |
| Debug reports tích lũy | Retention/archive manifest | Repo gọn, không mất bằng chứng |
| Direct SQL role seed | API/admin service hoặc guarded bootstrap | Cache/audit/validation nhất quán |
| Crawler container healthy = crawler healthy | Dùng `crawler_runs` + last success | Container sống không chứng minh crawl thành công |

Blueprint mới thắng khi có xung đột với snapshot cũ.
