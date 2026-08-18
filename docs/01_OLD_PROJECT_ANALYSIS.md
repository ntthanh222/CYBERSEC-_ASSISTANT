# 01 — Phân tích dự án cũ

## Phạm vi đã đọc

Snapshot cũ có khoảng 449 file được đóng gói, gồm backend FastAPI, frontend HTML/JS/CSS, Rasa, crawler, PostgreSQL migrations, Redis, ChromaDB, Docker Compose, test và nhiều báo cáo QA.

Các file cũ quan trọng đã được tách vào:

```text
reference/old_project_key_files/
```

## Kiến trúc cũ đã chứng minh được

Stack canonical cuối của dự án cũ từng có 8 service:

```text
frontend
backend
postgres
redis
chromadb
rasa
rasa-actions
crawler
```

Các luồng đã tồn tại:

- JWT auth và role guard.
- Rasa phân loại intent.
- RAG/ChromaDB và Gemini tùy chọn.
- Crawler Chromium ghi `news_articles` và `crawler_runs`.
- Dashboard probe database, Redis, ChromaDB, Rasa và crawler.
- Playwright kiểm tra user/admin/analyst, SSRF, session và restart.

## Điểm mạnh nên giữ

- Canonical Docker Compose tự chứa.
- External key tùy chọn, có fallback.
- Demo/QA account seed idempotent.
- Acceptance script trả exit code rõ ràng.
- E2E chạy trình duyệt thật.
- Role matrix và audit log.
- Crawler có `completed/partial/failed`.
- Health phải phản ánh dependency thật.
- Dữ liệu giữ sau restart.

## Vấn đề kiến trúc cần tránh

1. Nhiều route/module trùng vai trò như `chat.py` và `chatbot.py`.
2. Cấu hình crawler từng có nhiều nguồn chuẩn.
3. Migrations dựa vào initdb, không tự chạy khi volume đã tồn tại.
4. Cache user trong memory từng làm role/status cũ.
5. Supabase/PostgREST trả kiểu dữ liệu khác local PostgreSQL.
6. `crawler_runs` từng thiếu trong migration.
7. Trạng thái crawler `partial` từng bị hiển thị `unknown`.
8. Một số endpoint health/AI từng còn số hardcode.
9. Frontend từng phụ thuộc CDN/Tailwind runtime.
10. Password checker cũ từng gửi password tới backend/HIBP; bản rebuild không được làm vậy.
11. Port Rasa mặc định từng xung đột reserved TCP range trên Windows.
12. Test có thể PASS trong mock nhưng runtime thật vẫn lỗi.
13. Repo cũ chứa nhiều report/cache/archive; bản rebuild phải có retention rõ.
14. Dự án cũ từng có cả Supabase Cloud và local Postgres path; bản rebuild phải có một canonical DB path.

## Kết luận

Không phục hồi nguyên trạng source cũ. Bản mới giữ chức năng và bài học, nhưng dùng kiến trúc module rõ ràng, một nguồn config, một migration flow, một chatbot orchestrator và một canonical Compose.
