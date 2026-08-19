# Telegram Drive 

Port của [Telegram Drive](https://github.com/caamer20/Telegram-Drive) từ Rust/Tauri sang **Python (FastAPI + Telethon)** với Flutter frontend. Toàn bộ logic giữ nguyên Old_Project, chỉ đổi ngôn ngữ lập trình.

Sử dụng tài khoản Telegram cá nhân làm ổ đĩa đám mây:
- **Saved Messages** = thư mục gốc (home)
- **Kênh Telegram có hậu tố `[TD]`** = các thư mục con
- File tải lên được gửi trực tiếp lên server Telegram (không tốn dung lượng máy chủ)

## Kiến trúc

```
Telegram MTProto ──► Telethon (Python) ──► FastAPI BE (port 8000)
                                              ├── Web UI (Jinja2): /
                                              ├── Swagger API: /docs
                                              ├── Share Links: /d/{token}
                                              └── WebDAV: /webdav/{token}/
└── Flutter App (Desktop / Android / Web) ──► FastAPI BE 
```

## Cấu trúc thư mục

```
New_Project/
├── Web/                          # FastAPI Backend + Web UI (Jinja2)
│   ├── main.py                   # Entry point
│   ├── config/                   # settings, database, auth, logging
│   ├── core/                     # telegram_client, streaming, webdav
│   ├── api/
│   │   ├── auth/                 # Đăng nhập Telegram: phone/OTP/2FA/QR
│   │   ├── files/                # List/Upload/Download/Rename/Move/Delete
│   │   ├── folders/              # Tạo/quản lý kênh [TD]
│   │   ├── storage/              # Thống kê dung lượng, file trùng lặp
│   │   └── shares/               # Link chia sẻ (password/expiry)
│   ├── web/                      # Web UI (Jinja2 pages)
│   ├── templates/                # HTML templates
│   ├── static/                   # CSS/JS
│   ├── alembic/                  # Database migrations
│   └── requirements.txt
└── App_Flutter/                  # Flutter App (Desktop/Android/Web)
    ├── lib/
    │   ├── services/             # api_service.dart (gọi FastAPI)
    │   ├── providers/            # auth, files, folders, storage, theme
    │   ├── screens/              # login (Telegram), home, files, folders...
    │   └── widgets/
    └── pubspec.yaml
```

## Cài đặt & chạy Backend

### 1. Chuẩn bị PostgreSQL
- Database: `drive`
- User: `admin`
- Password: `Password@123`
- Host: `localhost:5432`

### 2. Cấu hình Telegram API + Admin
1. Truy cập https://my.telegram.org → **API development tools**
2. Lấy `api_id` và `api_hash`
3. Điền vào `New_Project/Web/.env`:
```env
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=your_api_hash_here

# Tài khoản admin đầu tiên (tự tạo khi bảng users rỗng)
INITIAL_ADMIN_EMAIL=admin@example.com
INITIAL_ADMIN_PASSWORD=admin_password
```
Nếu để trống API ID/Hash, người dùng có thể nhập trực tiếp trên màn hình kết nối (giống Old_Project).

### 3. Cài dependencies & chạy migrations
```powershell
cd New_Project/Web
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Tạo database schema (PostgreSQL)
alembic upgrade head
```

### 4. Chạy server
```powershell
.\venv\Scripts\python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Truy cập:
- Web UI: http://localhost:8000
- Swagger API: http://localhost:8000/docs

### 5. Luồng sử dụng (đa người dùng)

Hệ thống có **tài khoản người dùng** lưu trong PostgreSQL + **kết nối Telegram riêng cho từng user**:

1. **Admin ban đầu**: được tự động tạo từ `.env` (`INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD`) khi bảng `users` rỗng.
2. **Đăng ký**: `POST /api/auth/register` (hoặc trang `/auth/register`) — tài khoản mới **mặc định bị disable**.
3. **Admin kích hoạt**: admin vào `/admin/users` → bấm **"Kích hoạt"** (hoặc `PATCH /api/auth/users/{id}`).
4. **Đăng nhập tài khoản**: `POST /api/auth/login` bằng email/mật khẩu (tài khoản chưa enable bị từ chối 403).
5. **Kết nối Telegram**: sau khi đăng nhập tài khoản, vào `/auth/tg-connect` nhập số điện thoại → OTP → 2FA. Mỗi user có **StringSession Telegram riêng** trong PostgreSQL (`tg_sessions`) → mỗi người dùng **drive riêng**, tách biệt hoàn toàn.

**Bảo vệ:**
- Trang web (`/`, `/files`, `/folders`, `/storage`, `/admin/*`) → redirect `/auth/login` nếu chưa đăng nhập.
- API (`/api/files`, `/api/folders`, `/api/storage`, `/api/shares`) → `401` nếu thiếu token.
- Quản lý tài khoản (`/admin/users`) → chỉ admin (superuser) truy cập.

## Cài đặt & chạy Flutter App
- [Link App Project](https://github.com/produckx/teledrive_app)

```powershell
cd New_Project/App_Flutter
flutter pub get

# Chạy trên Desktop (Windows)
flutter run -d windows

# Chạy trên Web
flutter run -d chrome

# Build Android APK
flutter build apk --release
```

### Cấu hình server URL trong app
Màn hình đăng nhập có ô **API Server URL** — mặc định `http://localhost:8000`.
- **Android emulator**: dùng `http://10.0.2.2:8000`
- **Android thiết bị thật**: dùng IP máy tính (vd `http://192.168.1.5:8000`)

## API Endpoints chính

| Method | Path | Mô tả | Auth |
|--------|------|-------|------|
| POST | `/api/auth/register` | Đăng ký tài khoản (mặc định **disable**, tối đa 50 tài khoản/IP) | Public |
| POST | `/api/auth/login` | Đăng nhập tài khoản (cần được admin kích hoạt) | Public |
| GET | `/api/auth/me` | Thông tin tài khoản hiện tại | ✅ JWT |
| GET | `/api/auth/users` | Danh sách tài khoản (chỉ admin) | ✅ JWT |
| PATCH | `/api/auth/users/{id}` | Kích hoạt/vô hiệu hóa/nâng admin (chỉ admin) | ✅ JWT |
| POST | `/api/auth/logout` | Đăng xuất (tài khoản + Telegram) | ✅ JWT |
| POST | `/api/auth/send-code` | Gửi mã OTP đến số điện thoại Telegram | ✅ JWT |
| POST | `/api/auth/sign-in` | Xác thực mã OTP | ✅ JWT |
| POST | `/api/auth/check-password` | Xác thực mật khẩu 2FA | ✅ JWT |
| POST | `/api/auth/qr/start` | Tạo URL mã QR đăng nhập | ✅ JWT |
| GET | `/api/auth/qr/poll` | Poll trạng thái quét QR | ✅ JWT |
| GET | `/api/auth/status` | Trạng thái tài khoản hiện tại + kết nối Telegram | Public |
| GET | `/api/files` | Danh sách file (trả về **toàn bộ file**, không phân trang) | ✅ JWT |
| POST | `/api/files` | Upload file lên Telegram | ✅ JWT |
| GET | `/api/files/{id}/download` | Download / Stream video (hỗ trợ HTTP 206 Range) | ✅ JWT |
| PATCH | `/api/files/{id}` | Đổi tên file | ✅ JWT |
| POST | `/api/files/{id}/move` | Di chuyển file giữa các thư mục | ✅ JWT |
| DELETE | `/api/files/{id}` | Xóa file | ✅ JWT |
| GET | `/api/folders` | Danh sách thư mục (kênh [TD]) | ✅ JWT |
| POST | `/api/folders` | Tạo thư mục mới | ✅ JWT |
| PATCH | `/api/folders/{id}` | Đổi tên thư mục | ✅ JWT |
| DELETE | `/api/folders/{id}` | Xóa thư mục | ✅ JWT |
| GET | `/api/storage/stats` | Thống kê dung lượng, phân bố theo MIME | ✅ JWT |
| GET | `/api/storage/duplicates` | Tìm file trùng lặp | ✅ JWT |
| POST | `/api/shares` | Tạo link chia sẻ (password/expiry) | ✅ JWT |
| GET | `/d/{token}` | Trang chia sẻ file công khai | Public |
| OPTIONS/PROPFIND/GET/PUT/DELETE | `/webdav/{token}/...` | WebDAV access | Token |
| GET | `/admin/users` | Trang quản lý tài khoản | Admin |

**Ghi chú:**
- ✅ JWT: Yêu cầu truyền token trong header `Authorization: Bearer <token>` hoặc cookie `tdrive_token`
- Lock icon (🔒) trên Swagger UI xác định endpoint yêu cầu xác thực
- Rate limit: 20 requests/giây/người dùng (chưa login thì tính theo IP)

## Tính năng bảo mật

- **Xác thực JWT**: Token dùng cho mọi API yêu cầu login (header `Authorization: Bearer <token>` hoặc cookie `tdrive_token`)
- **Lock icon (🔒)**: Trên Swagger UI, các endpoint có ổ khóa là endpoint yêu cầu xác thực
- **Rate limiting**: 20 requests/giây/người dùng (chưa login thì tính theo IP công cộng)
- **Brute-force protection**: 5 lần đăng nhập sai → khóa 15 phút theo email+IP
- **Registration limit**: Tối đa 50 tài kản được đăng ký từ cùng một IP công cộng
- **SQL Injection**: Sử dụng SQLAlchemy ORM (tránh raw SQL)
- **Password hashing**: bcrypt với work factor 12
- **Session tách biệt**: Mỗi user có StringSession Telegram riêng → bảo vệ quyền riêng tư

## Tính năng đã port từ Old_Project

- ✅ **Tài khoản đa người dùng**: register/login PostgreSQL, mặc định disable, admin kích hoạt
- ✅ Đăng nhập Telegram: Số điện thoại → OTP → 2FA → QR (**riêng cho từng user**)
- ✅ Lưu trữ trên Saved Messages + kênh `[TD]`
- ✅ Upload / Download / Stream file (HTTP 206 Range + CDN alignment fix)
- ✅ Đổi tên (EditMessage caption), Di chuyển (Forward + Delete), Xóa
- ✅ Tạo / Đổi tên / Xóa thư mục (kênh Telegram)
- ✅ Thống kê dung lượng + file trùng lặp
- ✅ Link chia sẻ công khai (password, expiry, revoke)
- ✅ WebDAV access (read/write)
- ✅ Flutter app: Desktop, Android, Web

## Tính năng chưa port (có thể thêm sau)

- 🔒 Mã hóa TDENC2 (XChaCha20-Poly1305 vault + file passphrase)
- 📺 Transcode HLS / fMP4 remux (hiện stream gốc MP4 hỗ trợ Range)
- 🌐 Đa ngôn ngữ (i18n)
