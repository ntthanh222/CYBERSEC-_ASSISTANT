# 07 — UI/UX requirements

## Giao diện

- Responsive tối thiểu 1920×1080 và 1366×768.
- Không horizontal overflow.
- Navigation rõ theo role.
- Loading, empty, error, degraded là bốn trạng thái khác nhau.
- Dữ liệu stale phải có dấu hiệu.
- Nút mutation có confirmation phù hợp.
- Không hiển thị nút mà backend không hỗ trợ.
- Console sạch, không 404 tài nguyên.

## Trang mục tiêu

```text
login/register
dashboard
assistant/chat
tools: URL Scanner / Password Checker / CVE Lookup
vulnerability center
SOC workspace
digest
news
admin
```

## Dashboard

- Số liệu thật.
- Chart instance được destroy/reuse đúng.
- Không tạo request trùng khi chuyển tab.
- Health ghi rõ `healthy/degraded/unavailable/unknown`.
- Không dùng tỷ lệ hoặc latency giả.

## Chatbot

- Fast/Deep mode rõ ràng.
- Provider/source/confidence trung thực.
- Không giả token streaming bằng hiệu ứng chữ nếu backend không stream.
- Không yêu cầu người dùng nhập mật khẩu thật.
- Link nhanh tới Password Checker.

## Accessibility

- Semantic HTML.
- Label/form errors.
- Keyboard navigation cơ bản.
- Focus state.
- Contrast hợp lý.
- `aria-live` cho trạng thái bất đồng bộ.
