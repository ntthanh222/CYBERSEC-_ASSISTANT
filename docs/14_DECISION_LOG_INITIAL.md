# 14 — Initial decision log

## ADR-001 — Single physical project root

Không worktree, không project copy. Mọi AI dùng cùng folder.

## ADR-002 — Phase-gated rebuild

Full roadmap được lưu, nhưng chỉ triển khai Phase 0 + 1 ở lần đầu.

## ADR-003 — Local-first canonical runtime

Core demo phải chạy không cần Supabase/Gemini/VirusTotal.

## ADR-004 — Password privacy

Password Checker không có backend request chứa password.

## ADR-005 — Honest observability

Unknown/degraded được chấp nhận; fake healthy không được chấp nhận.

## ADR-006 — Old project is evidence, not source-of-truth

Chỉ tái sử dụng ý tưởng/test case có chọn lọc; không copy nguyên kiến trúc legacy.
