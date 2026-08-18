# 11 — Environment và ports

## Mục tiêu canonical

| Service | Internal | Host mặc định |
|---|---:|---:|
| frontend | 80 | 3000 |
| backend | 8000 | 8000 |
| postgres | 5432 | không public mặc định |
| redis | 6379 | không public mặc định |
| chromadb | 8000 | không public |
| rasa | 5005 | chỉ public khi cần debug |
| rasa-actions | 5055 | không public |
| crawler | 8090 | chỉ public khi cần admin/debug |

## Windows

Dự án cũ từng gặp reserved port với 5005/5055. Trước khi public host port Rasa:

```powershell
netsh interface ipv4 show excludedportrange protocol=tcp
```

Có thể map host sang 15005/15055, giữ internal 5005/5055.

## Environment rules

- `.env` local, gitignored.
- `.env.example` không có secret thật.
- External key tùy chọn:
  - `GEMINI_API_KEY`
  - `VIRUSTOTAL_API_KEY`
  - `NIST_NVD_API_KEY`
- Thiếu key không làm core stack fail.
- Production từ chối secret mặc định.
- Không in secret ra log.
