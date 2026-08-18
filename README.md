# 🛡️ CyberSec Assistant

Nền tảng trợ lý an ninh mạng toàn diện, hỗ trợ quản lý tài sản, rà soát lỗ hổng bảo mật (CVE/Vulnerability Management), xử lý sự cố an ninh (Incident Response) và trợ lý ảo thông minh (RAG + AI Assistant).

---

## 🌟 Tính Năng Chính

### 1. 🤖 Trợ Lý Bảo Mật Thông Minh (AI Assistant & RAG)
- Tích hợp mô hình RAG (Retrieval-Augmented Generation) kết hợp Vector Search (`pgvector`) & Full-Text Search.
- Tra cứu cơ sở tri thức an ninh mạng, xử lý ngôn ngữ tự nhiên, phân tích tình huống và khuyến nghị remediation.
- Hỗ trợ mô hình Local LLM / Ollama và Gemini API tùy chọn.

### 2. 🔍 Security Toolkit
- **URL Scanner**: Phân tích URL an toàn, kiểm tra domain/IP, chống SSRF.
- **CVE Lookup & Watchlist**: Tra cứu thông tin lỗ hổng bảo mật NIST NVD, quản lý danh sách theo dõi CVE thời gian thực.
- **Password Checker**: Kiểm tra độ mạnh mật khẩu và chính sách bảo mật ngay tại client.
- **Security News Crawler**: Tự động tổng hợp tin tức an ninh mạng mới nhất.

### 3. 🏢 Quản Lý An Ninh & Phản Ứng Sự Cố
- **Asset & Vulnerability Center**: Quản lý tài sản công nghệ thông tin, theo dõi trạng thái vá lỗ hổng.
- **Incident & Playbook Management**: Quy trình ứng phó sự cố an ninh mạng theo chuẩn chuẩn hóa (Timeline, Incident tracking, Audit log).
- **Attack Graph Visualization**: Trực quan hóa đường đi và nguy cơ tấn công trên hệ thống mạng.

### 4. 🔐 Xác Thực & Quản Trị Hệ Thống
- Phân quyền theo vai trò (RBAC): Admin, Analyst, User.
- Hỗ trợ chế độ **Local Mode** chạy ngay lập tức hoặc kết nối Supabase Cloud.
- Giám sát sức khỏe hệ thống (Health Check, Prometheus Metrics).

---

## 🏗️ Kiến Trúc Hệ Thống & Công Nghệ

- **Frontend**: React, TypeScript, Vite, TailwindCSS / Modern UI Components, Chart.js, Lucide Icons.
- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.0 (Async), Alembic, Pydantic v2.
- **Database & Cache**: PostgreSQL 16 (với extension `pgvector`), Redis 7.
- **Containerization & CI/CD**: Docker, Docker Compose, GitHub Actions, Playwright E2E Testing, Pytest.

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Hệ Thống

### Yêu Cầu Tiên Quyết
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) đã được cài đặt và đang chạy.

### 1. Khởi Chạy Nhanh Bằng Docker Compose

1. Clone repository:
   ```bash
   git clone https://github.com/ntthanh222/CYBERSEC-_ASSISTANT.git
   cd CYBERSEC-_ASSISTANT
   ```

2. Khởi động toàn bộ dịch vụ:
   ```bash
   docker compose up -d --build
   ```

3. Truy cập ứng dụng:
   - **Frontend App**: [http://localhost:3000](http://localhost:3000)
   - **Swagger API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
   - **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
   - **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

4. Đăng nhập:
   - Tại giao diện [http://localhost:3000](http://localhost:3000), bạn có thể nhấn **ENTER LOCAL MODE** để trải nghiệm ngay lập tức mà không cần cấu hình thêm.

---

## ⚙️ Dừng Hệ Thống

```bash
docker compose down
```
*(Dữ liệu được lưu trữ an toàn trong Docker volumes)*

---

## 🧪 Kiểm Thử (Testing)

- **Chạy unit tests Backend**:
  ```bash
  docker compose exec backend pytest
  ```
- **Chạy E2E Tests (Playwright)**:
  ```bash
  cd frontend && npm run test:e2e
  ```

---

## 📄 Bản Quyền & Giấy Phép

Dự án được xây dựng phục vụ nghiên cứu và phát triển giải pháp an ninh mạng.
