# 06 — Security requirements

## Auth/RBAC

- Password hash bằng thuật toán hiện đại.
- JWT có expiration và secret mạnh.
- Kiểm tra `is_active` và role ở backend.
- Admin không được sửa/hạ quyền Super Admin trái policy.
- User/analyst mutation phải bị backend trả 403.
- Không dùng query string cho token.
- Streaming dùng short-lived ticket khi cần.

## SSRF

- Chỉ `http/https`.
- Resolve toàn bộ IP.
- Chặn private, loopback, link-local, multicast, metadata.
- Re-resolve sau redirect.
- Chặn redirect vào nội bộ.
- Chống DNS rebinding.
- Timeout, giới hạn response size và số redirect.
- Không tin hostname chỉ vì chuỗi trông công khai.

## Frontend

- Escape dữ liệu server.
- DOMPurify khi render HTML.
- Không `innerHTML` với dữ liệu chưa sanitize.
- Không lưu password.
- Password Checker local-only.
- Không gửi secret/API key xuống client.
- Auth state không bị xóa khi 500/503/network timeout.

## Headers/CORS

- CSP phù hợp.
- `X-Content-Type-Options`.
- `Referrer-Policy`.
- `frame-ancestors` hoặc `X-Frame-Options`.
- `Permissions-Policy`.
- CORS allowlist; không `*` với credentials.

## Logging/Observability

- Redact password, token, Authorization, cookie, API key.
- Request ID.
- Audit log riêng.
- Không trả exception raw cho client.

## Dependency

- `pip-audit`, `npm audit`, `pip check`.
- Pin version.
- Không bật `trust_remote_code`.
- Không public ChromaDB/Redis/Postgres nếu không cần.
