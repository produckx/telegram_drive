# Rules: FastAPI Project compatible with Cython (.pyd)

## Mục lục
1. [Cấu trúc thư mục](#1-cấu-trúc-thư-mục)
2. [Ý nghĩa các file và thư mục](#2-ý-nghĩa-các-file-và-thư-mục)
3. [Luồng xử lý request](#3-luồng-xử-lý-request)
4. [Mỗi ứng dụng gồm 4 file bắt buộc](#4-mỗi-ứng-dụng-gồm-4-file-bắt-buộc)
5. [Rules cho router (Cython-safe)](#5-rules-cho-router-cython-safe)
6. [Rules cho auth/dependency](#6-rules-cho-authdependency)
7. [Rules cho repo (database)](#7-rules-cho-repo-database)
8. [Rules cho web/FE (Jinja2 templates)](#8-rules-cho-web-fe-jinja2-templates)
9. [Rules cho offline deployment](#9-rules-cho-offline-deployment)
10. [Rules cho main.py + OpenAPI](#10-rules-cho-mainpy--openapi)
11. [Checklist cho project mới](#11-checklist-cho-project-mới)

---

## 1. Cấu trúc thư mục

```
project/
├── main.py                       # Entry point: FastAPI app, middleware, CORS, OpenAPI, mount static
├── requirements.txt
├── __init__.py
│
├── api/                          # Backend API — REST endpoints, pure logic, Cython-safe
│   ├── router.py                 # Router tổng: include tất cả router API con
│   ├── __init__.py
│   │
│   ├── stt/                      # Module: Speech-to-Text
│   │   ├── router.py             #   /api/stt/...
│   │   ├── schema.py             #   Request/response Pydantic models
│   │   ├── service.py            #   Business logic (xử lý audio, gọi model)
│   │   ├── repo.py               #   Model loading, audio I/O
│   │   └── __init__.py
│   │
│   ├── auth/                     # Module: Authentication
│   │   ├── router.py             #   /api/auth/...
│   │   ├── schema.py
│   │   ├── service.py
│   │   ├── repo.py
│   │   └── __init__.py
│   │
│   └── history/                  # Module: Lịch sử transcription
│       ├── router.py             #   /api/history/...
│       ├── schema.py
│       ├── service.py
│       ├── repo.py
│       └── __init__.py
│
├── web/                          # Frontend — FastAPI + Jinja2 (pages, không phải API)
│   ├── router.py                 # Router tổng: include tất cả router FE con
│   ├── templates.py              # Khởi tạo Jinja2Templates共用
│   ├── __init__.py
│   │
│   ├── home/                     # Trang chủ
│   │   ├── router.py             #   GET /, /home
│   │   ├── service.py            #   Chuẩn bị dữ liệu cho template
│   │   ├── templates/
│   │   │   └── index.html
│   │   ├── static/
│   │   │   ├── home.css
│   │   │   └── home.js
│   │   └── __init__.py
│   │
│   ├── stt/                      # Giao diện STT
│   │   ├── router.py             #   GET /stt
│   │   ├── service.py
│   │   ├── templates/
│   │   │   └── index.html
│   │   ├── static/
│   │   │   ├── stt.css
│   │   │   └── stt.js
│   │   └── __init__.py
│   │
│   ├── history/                  # Giao diện lịch sử
│   │   ├── router.py             #   GET /history
│   │   ├── service.py
│   │   ├── templates/
│   │   │   ├── index.html
│   │   │   └── detail.html
│   │   ├── static/
│   │   │   ├── history.css
│   │   │   └── history.js
│   │   └── __init__.py
│   │
│   └── auth/                     # Giao diện đăng nhập
│       ├── router.py             #   GET /login, /register
│       ├── service.py
│       ├── templates/
│       │   └── login.html
│       ├── static/
│       │   ├── auth.css
│       │   └── auth.js
│       └── __init__.py
│
├── templates/                    # Template dùng chung cho toàn bộ FE
│   ├── base.html                 # Layout gốc: <head>, <body>, block content
│   ├── components/
│   │   ├── navbar.html
│   │   ├── sidebar.html
│   │   ├── alert.html
│   │   └── footer.html
│   └── errors/
│       ├── 404.html
│       └── 500.html
│
├── static/                       # Static files dùng chung
│   ├── css/
│   │   ├── app.css               # Global styles
│   │   └── variables.css         # CSS custom properties
│   ├── js/
│   │   ├── app.js                # Global scripts
│   │   ├── api.js                # Fetch wrapper gọi API backend
│   │   └── utils.js              # Utility functions
│   ├── images/
│   └── vendor/                   # Thư viện JS/CSS offline (bootstrap, htmx, ...)
│
├── config/                       # Configuration & cross-cutting concerns
│   ├── auth.py                   # Xác thực API Key: verify_api_key(), resolve_auth
│   ├── database.py               # Kết nối SQLAlchemy: engine, SessionLocal, Base, init_db()
│   ├── settings.py               # App settings: MODE, DEBUG, UPLOAD_DIR, ...
│   ├── logging.py                # Logging configuration
│   └── __init__.py
│
├── core/                         # Core utilities, Cython-safe
│   ├── exceptions.py             # Custom exception classes
│   ├── dependencies.py           # Hàm dùng chung (resolve_db, pagination, ...)
│   ├── responses.py              # Standard response wrappers
│   └── __init__.py
│
├── uploads/                      # File upload runtime (git-ignored)
└── logs/                         # Log runtime (git-ignored)
```

## 2. Ý nghĩa các file và thư mục

### 2a. `api/` — Backend REST API

Chứa toàn bộ logic backend, **không liên quan đến HTML rendering**. Mỗi module con là một ứng dụng độc lập.

| Thư mục | Chức năng |
|---------|-----------|
| `api/stt/` | Nhận file audio → chuyển giọng nói thành văn bản |
| `api/auth/` | Đăng ký, đăng nhập, cấp/token API Key |
| `api/history/` | Lưu và truy vấn lịch sử transcription |

### 2b. `web/` — Frontend (FastAPI + Jinja2)

Chứa toàn bộ giao diện người dùng, render HTML server-side bằng Jinja2.

| Thư mục | Chức năng |
|---------|-----------|
| `web/router.py` | Gom tất cả router FE, mount static files của web |
| `web/templates.py` | Khởi tạo `Jinja2Templates` dùng chung với `auto_reload=False` |
| `web/home/` | Trang chủ, dashboard |
| `web/stt/` | Giao diện upload audio + hiển thị kết quả |
| `web/history/` | Danh sách lịch sử + chi tiết |
| `web/auth/` | Giao diện login/register |

**Mỗi module FE** gồm:
| File | Chức năng |
|------|-----------|
| `router.py` | Định nghĩa route GET, render template |
| `service.py` | Chuẩn bị dữ liệu (gọi API service, query DB) trước khi render |
| `templates/*.html` | Jinja2 templates riêng của module |
| `static/*.css, *.js` | CSS/JS riêng của module |

### 2c. `templates/` — Templates dùng chung

| File | Chức năng |
|------|-----------|
| `base.html` | Layout gốc: `<html>`, `<head>`, `<body>`, block `content`, block `scripts` |
| `components/*` | Component tái sử dụng (navbar, sidebar, alert, footer) |
| `errors/*` | Trang lỗi chuẩn (404, 500) |

### 2d. `static/` — Static files dùng chung

| File | Chức năng |
|------|-----------|
| `css/variables.css` | CSS custom properties: colors, spacing, typography |
| `css/app.css` | Global styles: reset, layout grid, utility classes |
| `js/api.js` | Fetch wrapper: tự động gắn API Key header, xử lý lỗi |
| `js/app.js` | Global scripts: navbar toggle, theme switch |
| `js/utils.js` | Format time, debounce, validate file types |
| `vendor/` | Thư viện third-party offline (bootstrap.css, htmx.js, ...) |

### 2e. `config/` — Configuration

| File | Chức năng |
|------|-----------|
| `auth.py` | `verify_api_key(request)`, `resolve_auth` decorator |
| `database.py` | SQLAlchemy engine, `SessionLocal`, `Base`, `init_db()` |
| `settings.py` | `AppSettings`: MODE, DEBUG, SECRET_KEY, UPLOAD_DIR, MAX_FILE_SIZE, ALLOWED_EXTENSIONS |
| `logging.py` | Log format, file rotation, log level |

### 2f. `core/` — Core utilities (Cython-safe)

| File | Chức năng |
|------|-----------|
| `exceptions.py` | `AppException`, `NotFoundException`, `ValidationError` |
| `dependencies.py` | `resolve_db(request)` → Session, pagination helpers |
| `responses.py` | `ok(data)`, `error(message)` wrapper |

---

## 3. Luồng xử lý request

### 3a. API request (backend)

```
HTTP Request → /api/...
    → main.py (FastAPI app)
        → api/router.py
            → api/stt/router.py
                → schema.py (validate request body)
                → service.py (business logic)
                    → repo.py (database / model)
                → schema.py (format response)
            → HTTP Response (JSON)
```

### 3b. Page request (frontend)

```
HTTP Request → /stt, /history, ...
    → main.py (FastAPI app)
        → web/router.py
            → web/stt/router.py
                → service.py (gọi API backend qua requests, hoặc query DB)
                → templates/stt/index.html (Jinja2 render)
            → HTTP Response (HTML)
```

### 3c. Kết hợp cả hai

```
Trình duyệt
    ↓ GET /stt (HTML page)
    ↓ fetch /api/stt/transcribe (POST JSON)
    ↓ fetch /api/history (GET JSON)
    ↓ JS render kết quả

API backend (api/) ←→ Frontend (web/) ←→ Trình duyệt
```

---

## 4. Mỗi ứng dụng gồm 4 file bắt buộc

### 4a. Backend (api/)

| File | Chức năng |
|------|-----------|
| `schema.py` | Định nghĩa request/response model, validation (Pydantic) |
| `repo.py` | CRUD queries, session get/close, model loading |
| `service.py` | Business logic: nhận request từ router, gọi repo, trả response |
| `router.py` | Định nghĩa endpoint path, method, summary, description, auth |

### 4b. Frontend (web/)

| File | Chức năng |
|------|-----------|
| `router.py` | Định nghĩa GET route, render template |
| `service.py` | Chuẩn bị context data cho template |
| `templates/*.html` | Jinja2 template riêng |
| `static/*.css, *.js` | CSS/JS riêng

### Quy tắc đặt tên API path

**❌ Không được** thêm `/` ở cuối path — áp dụng cho **tất cả method** (GET, POST, PUT, PATCH, DELETE):

```python
@router.get("/")          # ❌ Sai
@router.post("/product/") # ❌ Sai
@router.put("/item/")     # ❌ Sai
@router.patch("/{id}/")   # ❌ Sai
@router.delete("/{id}/")  # ❌ Sai
```

**✅ Phải viết:**

```python
@router.get("")           # ✅ Đúng - GET root
@router.get("/product")   # ✅ Đúng - GET không / cuối
@router.get("/{id}")      # ✅ Đúng - GET path param
@router.post("")          # ✅ Đúng - POST root
@router.post("/product")  # ✅ Đúng - POST không / cuối
@router.put("/product")   # ✅ Đúng - PUT
@router.patch("/{id}")    # ✅ Đúng - PATCH
@router.delete("/{id}")   # ✅ Đúng - DELETE
```

Lý do: FastAPI redirect mặc định `/{path}/` → `/{path}`, gây request phụ không cần thiết.

### Quy tắc summary và description

**Mọi API endpoint đều phải có** `summary` và `description`:

```python
# ❌ Thiếu summary/description
@router.get("")
def list_items(request: Request):
    ...

# ✅ Đúng - có đầy đủ
@router.get("", summary="Danh sách Plan", description="Lấy tất cả Plan trong hệ thống.")
def list_items(request: Request):
    ...
```

Lý do:
- `summary` → hiển thị tên trên Swagger UI (dễ đọc, dễ tìm)
- `description` → mô tả chi tiết, giúp người dùng API biết endpoint đó làm gì
- Swagger/OpenAPI là tài liệu chính cho front-end và bên thứ 3 tích hợp

---

## 5. Rules cho router (Cython-safe)

### ❌ KHÔNG được dùng

```python
# ❌ Cython lỗi: TypeError: Expected str, got Depends
def add_item(db: Session = Depends(get_session), auth: str = Depends(verify_api_key)):
```

```python
# ❌ Cython lỗi: TypeError: Expected str, got Header
def verify_api_key(x_api_key: str = Header(None)):
```

### ✅ Phải dùng

```python
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy.orm import Session
from config.auth import resolve_auth
from api.plan.repo import get_session, close_session

router = APIRouter(prefix="/example", tags=["Example"])


def resolve_db(request: Request) -> Session:
    """Tự tạo session, không dùng Depends."""
    db = get_session()
    request.state.db = db
    return db


@router.post("")
@resolve_auth
def create_item(data: ItemRequest, request: Request):
    # request được FastAPI auto-inject, không cần Depends
    # @resolve_auth tự gọi verify_api_key(request)
    db = resolve_db(request)          # thay cho db: Session = Depends(get_session)
    try:
        result = service.create(db, data)
        if result is None:
            raise HTTPException(status_code=400, detail="Error")
        return result
    finally:
        close_session(db)              # tự đóng session


@router.get("")
def list_items(request: Request):
    # GET không cần auth, vẫn cần request để lấy session
    db = resolve_db(request)
    try:
        return service.list_all(db)
    finally:
        close_session(db)
```

### Các decorator vẫn dùng được bình thường

```python
# ✅ Các tham số này compile được vì không phải default parameter
@router.post("", response_model=MessageResponse, summary="...", description="...")
@router.get("", response_model=list[ItemResponse])
@router.delete("/{id}", response_model=MessageResponse)
```

---

## 6. Rules cho auth/dependency

### ✅ `config/auth.py` (compile được)

```python
from fastapi import Request, HTTPException
from functools import wraps

API_KEY = "your-api-key-here"


def verify_api_key(request: Request):
    """Dùng request thay vì Header(None)."""
    x_api_key = request.headers.get("x-api-key")
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return x_api_key


def resolve_auth(func):
    """Decorator: set __auth_required__ + tự gọi verify_api_key(request)."""
    func.__auth_required__ = True

    @wraps(func)
    def wrapper(*args, **kwargs):
        request = kwargs.get("request")
        if request is None:
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
        if request is not None:
            verify_api_key(request)
        return func(*args, **kwargs)

    return wrapper
```

**Cơ chế:** Decorator `@resolve_auth` chạy ở import time → set `__auth_required__` → `custom_openapi()` đọc attribute đó để thêm ổ khóa vào endpoint tương ứng trên Swagger UI.

Không dùng:
```python
# ❌ Cython lỗi
from fastapi import Header
def verify_api_key(x_api_key: str = Header(None)):
```

---

## 7. Rules cho repo (database)

### ❌ Không dùng generator (yield)

```python
# ❌ Cython có thể lỗi
def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

### ✅ Dùng return + close riêng

```python
from sqlalchemy.orm import Session
from config.database import SessionLocal


def get_session() -> Session:
    return SessionLocal()


def close_session(db: Session):
    db.close()
```

### Các hàm CRUD viết bình thường

```python
def insert_item(db: Session, item: str) -> Plan | None:
    plan = Plan(item=item)
    db.add(plan)
    try:
        db.commit()
        db.refresh(plan)
        return plan
    except Exception:
        db.rollback()
        return None


def select_all(db: Session) -> list[Plan]:
    return db.query(Plan).all()
```

---

## 8. Rules cho web/FE (Jinja2 templates)

### 8a. `web/templates.py` — Khởi tạo Jinja2Templates dùng chung

```python
import os
from jinja2 import Environment, FileSystemLoader
from starlette.templating import Jinja2Templates

templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
jinja_env = Environment(
    loader=FileSystemLoader(templates_dir),
    auto_reload=False,           # tránh lỗi unhashable type: 'dict'
)
templates = Jinja2Templates(directory=templates_dir, env=jinja_env)
```

### 8b. Router FE — không dùng `Depends`, dùng `request`

```python
from fastapi import APIRouter, Request
from starlette.templating import _TemplateResponse
from web.templates import templates

router = APIRouter(prefix="/stt", tags=["STT"])

@router.get("", response_class=_TemplateResponse)
def index(request: Request):
    # Chuẩn bị context
    context = {"request": request, "title": "STT"}
    return templates.TemplateResponse("stt/index.html", context)
```

### 8c. Template kế thừa `base.html`

```html
{% extends "base.html" %}

{% block content %}
<div class="stt-page">
    <h1>Speech to Text</h1>
    <!-- nội dung riêng -->
</div>
{% endblock %}

{% block scripts %}
<script src="/static/js/stt/stt.js"></script>
{% endblock %}
```

### 8d. Static files — mount đúng cách

Trong `web/router.py`:

```python
from fastapi.staticfiles import StaticFiles

# Mount static của từng module FE
router.mount("/static/stt", StaticFiles(directory="web/stt/static"), name="stt-static")
router.mount("/static/history", StaticFiles(directory="web/history/static"), name="history-static")
```

Static dùng chung mount ở `main.py`:

```python
app.mount("/static", StaticFiles(directory="static"), name="static")
```

### 8e. JS fetch API — gọi backend từ trình duyệt

Trong `static/js/api.js`:

```javascript
const API_BASE = "/api";

async function apiRequest(method, path, options = {}) {
    const headers = { "x-api-key": localStorage.getItem("api_key") || "" };
    const response = await fetch(`${API_BASE}${path}`, { method, headers, ...options });
    if (!response.ok) throw await response.json();
    return response.json();
}
```

### 8f. Vendor files offline

Tất cả thư viện JS/CSS (bootstrap, htmx, alpine.js, ...) phải được tải về và đặt trong `static/vendor/`, **không dùng CDN**:

```html
<!-- ✅ Đúng - local -->
<link rel="stylesheet" href="/static/vendor/bootstrap/bootstrap.min.css">
<script src="/static/vendor/htmx/htmx.min.js"></script>

<!-- ❌ Sai - CDN -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/...">
```

---

## 9. Rules cho offline deployment

Dự án FastAPI này **chạy hoàn toàn offline (không có internet)**. Mọi thư viện và tài nguyên phải được tải về trước và bundle sẵn.

### 5a. Thư viện Python phải có sẵn trong `requirements.txt`

Tất cả thư viện dùng trong dự án phải được liệt kê trong `requirements.txt` và cài đặt sẵn `pip install -r requirements.txt` trước khi deploy:

```
fastapi
uvicorn
sqlalchemy
alembic
pydantic
uuid6
jinja2
swagger-ui-bundle  # local Swagger UI, không cần CDN
```

Không dùng thư viện nào require internet ở runtime (ví dụ: `requests` gọi API ngoài, `httpx` fetch external resources).

### 5b. Swagger UI local (không CDN)

**Không được** dùng Swagger UI từ CDN — phải dùng file local từ package `swagger-ui-bundle`:

```python
from fastapi.staticfiles import StaticFiles
import swagger_ui_bundle
import os

swagger_ui_path = os.path.join(
    os.path.dirname(swagger_ui_bundle.__file__),
    "vendor",
    "swagger-ui-4.15.5"
)
app.mount("/swagger-ui", StaticFiles(directory=swagger_ui_path), name="swagger-ui")
```

Khi gọi `get_swagger_ui_html()`, phải truyền `swagger_js_url` và `swagger_css_url` trỏ về local:

```python
from fastapi.openapi.docs import get_swagger_ui_html

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="My API",
        swagger_js_url="/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/swagger-ui/swagger-ui.css",
    )
```

**Phải set `docs_url=None, redoc_url=None`** khi tạo `FastAPI()` để tắt route mặc định (vốn dùng CDN).

### 5c. OpenAPI version tương thích với Swagger UI local

Swagger UI bản cũ (4.x) không hỗ trợ OpenAPI 3.1.0. Phải force về 3.0.x trong `custom_openapi()`:

```python
openapi_schema = get_openapi(
    ...
    openapi_version="3.0.3",
    ...
)
```

### 5d. Template rendering (Jinja2)

Template được render bằng Jinja2, không dùng internet. Cấu hình:

```python
from jinja2 import Environment, FileSystemLoader

templates_dir = os.path.join(os.path.dirname(__file__), "templates")
jinja_env = Environment(loader=FileSystemLoader(templates_dir), auto_reload=False)
```

Lý do `auto_reload=False`: tránh lỗi `unhashable type: 'dict'` với Jinja2 3.1.6 khi cache template.

---

## 10. Rules cho main.py + OpenAPI

### `main.py` giữ nguyên .py (không compile)

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute, _IncludedRouter
from api.router import router as api_router
from web.router import router as web_router
from config.database import init_db

app = FastAPI(title="API", version="1.0.0", docs_url=None, redoc_url=None)

# Mount static dùng chung
app.mount("/static", StaticFiles(directory="static"), name="static")

# Swagger UI local (không CDN)
import swagger_ui_bundle
import os
swagger_ui_path = os.path.join(
    os.path.dirname(swagger_ui_bundle.__file__),
    "vendor", "swagger-ui-4.15.5"
)
app.mount("/swagger-ui", StaticFiles(directory=swagger_ui_path), name="swagger-ui")


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        openapi_version="3.0.3",
    )
    openapi_schema["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "x-api-key",
        }
    }
    for route in app.routes:
        if isinstance(route, _IncludedRouter):
            for ctx in route.effective_route_contexts():
                if getattr(ctx.endpoint, "__auth_required__", False):
                    path_item = openapi_schema["paths"].get(ctx.path_format)
                    if path_item:
                        for method in ctx.methods:
                            if method.lower() in path_item:
                                path_item[method.lower()].setdefault("security", []).append({"ApiKeyAuth": []})
        elif isinstance(route, APIRoute):
            if getattr(route.endpoint, "__auth_required__", False):
                path_item = openapi_schema["paths"].get(route.path)
                if path_item:
                    for method in route.methods:
                        if method.lower() in path_item:
                            path_item[method.lower()].setdefault("security", []).append({"ApiKeyAuth": []})
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi
app.include_router(api_router)   # Backend API: /api/*
app.include_router(web_router)   # Frontend pages: /*


@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="API Docs",
        swagger_js_url="/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/swagger-ui/swagger-ui.css",
    )


@app.on_event("startup")
def startup():
    init_db()
```

---

## 11. Checklist cho project mới

| # | Rule | Áp dụng cho |
|---|------|-------------|
| # | Rule | Áp dụng cho |
|---|------|-------------|
| 1 | Không dùng `= Depends()` trong function signature | router.py (api & web) |
| 2 | Dùng `request: Request` auto-inject thay thế | router.py (api & web) |
| 3 | Dùng decorator `@resolve_auth` (từ `config.auth`) thay `auth: str = Depends(...)` | api/router.py |
| 4 | Tự `get_session()` + `close_session()` thay `db: Session = Depends(...)` | api/router.py |
| 5 | `get_session()` return session, không yield | repo.py |
| 6 | Auth function dùng `request: Request`, không `Header(None)` | config/auth.py |
| 7 | Giữ `main.py` là `.py`, không compile | main.py |
| 8 | Giữ `alembic/` là `.py`, không compile | alembic/ |
| 9 | Thêm `custom_openapi()` kiểm tra `__auth_required__` để Swagger hiển thị security | main.py |
| 10 | Dùng `@resolve_auth` decorator — tất cả đều compile được | toàn bộ api/ |
| 11 | `swagger-ui-bundle` thay vì CDN cho Swagger UI | main.py |
| 12 | Force `openapi_version="3.0.3"` tương thích Swagger 4.x | main.py (custom_openapi) |
| 13 | `docs_url=None, redoc_url=None` khi tạo FastAPI() | main.py |
| 14 | Jinja2 dùng `auto_reload=False` tránh lỗi cache | web/templates.py |
| 15 | `vendor/` chứa thư viện offline, không dùng CDN | web/*/templates/*.html |
| 16 | JS fetch gọi API backend qua `/api/...`, không gọi trực tiếp | static/js/api.js |
| 17 | Mỗi module FE có `templates/` và `static/` riêng | web/*/ |
| 18 | `web/templates.py` khởi tạo `Jinja2Templates` tập trung | web/ |
| 19 | Tất cả thư viện trong `requirements.txt`, không runtime internet | requirements.txt |
