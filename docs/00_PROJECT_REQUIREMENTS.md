# 00 — Yêu cầu dự án

## Mục tiêu

Xây dựng hệ thống trợ lý an toàn thông tin tích hợp chatbot, phân tích URL, tra cứu CVE, quản lý tài sản/lỗ hổng và hỗ trợ ứng cứu sự cố.

## Nhóm người dùng

- `user`
- `security_analyst`
- `admin`
- `super_admin`
- tài khoản `disabled`

## Khối chức năng

1. Auth, session và RBAC.
2. Dashboard dữ liệu thật.
3. Chatbot Fast/Deep mode.
4. Rasa + RAG + Gemini tùy chọn.
5. URL Scanner.
6. Password Checker local-first.
7. CVE Lookup và Watchlist.
8. Asset/Vulnerability Center.
9. Alert/Incident/Playbook/Timeline.
10. Smart Digest.
11. News/Crawler.
12. Admin, health, audit và monitoring.
13. Report/export.
14. Security hardening.
15. Unit, integration, Playwright, restart và persistence.

## Nguyên tắc sản phẩm

- Không fake data.
- Không fake provider.
- Không fake health.
- Không gửi mật khẩu thật về server.
- Không biến lỗi backend thành empty state.
- Không chỉ bảo mật bằng cách ẩn nút.
- Không xóa phiên khi lỗi tạm thời.
- Không tuyên bố hoàn thành khi acceptance exit code khác `0`.
