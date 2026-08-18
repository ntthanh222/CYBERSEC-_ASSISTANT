# 15 — Risk register

| Risk | Mức | Mitigation |
|---|---|---|
| Scope bùng nổ do build tất cả cùng lúc | Cao | Phase gate và CURRENT_PHASE |
| Copy legacy bugs từ project cũ | Cao | Old-to-new mapping + review độc lập |
| Migration không chạy với volume cũ | Cao | Migration runner + restart test |
| Session bị xóa khi backend tạm lỗi | Cao | 401/403-only invalidation test |
| SSRF qua redirect/DNS | Cao | Resolve/re-resolve + IP policy |
| Password rò qua backend/log | Cao | Client-only + network assertion |
| Role stale do cache | Cao | DB authoritative/invalidation |
| Service health giả | Cao | Real probes + degraded/unknown |
| External API/quota làm core fail | Trung bình | Optional adapter + deterministic fallback |
| Windows port conflict | Trung bình | Preflight excluded-port check |
| Rasa train chậm | Trung bình | Model volume/cache + start period |
| Repo phình bởi report/cache | Trung bình | Retention + gitignore + manifest |
| E2E flaky | Trung bình | No retries, root-cause fix, repeated loops |
