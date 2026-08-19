import os
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute
from fastapi.middleware.cors import CORSMiddleware

from api.router import router as api_router
from web.router import router as web_router
from core.webdav import router as webdav_router
from config.database import init_db
from config.settings import settings
from config.logging import setup_logging
from config.rate_limit import rate_limiter, get_client_ip

# Setup logging
setup_logging()

# Create FastAPI app
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url=None,
    redoc_url=None,
)

# CORS middleware
origins = [origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def rate_limit_middleware(request, call_next):
    """Giới hạn số lần gọi API: 20 request/giây/account (chưa đăng nhập thì tính theo IP).

    Đây là giới hạn SỐ LẦN GỌI API, không phải giới hạn số item trả về.
    Các endpoint danh sách (files/folders/users...) trả về toàn bộ dữ liệu.
    Đăng ký tài khoản được giới hạn riêng: tối đa 50 tài khoản / IP công cộng
    (kiểm tra trong endpoint /api/auth/register).
    """
    path = request.url.path

    # Chỉ áp dụng cho API endpoints
    if not path.startswith("/api/"):
        return await call_next(request)

    # Xác định account: user đã đăng nhập, nếu chưa thì tính theo IP
    user = getattr(request.state, "current_user", None)
    if user is not None:
        key = f"api:user:{user.id}"
    else:
        key = f"api:ip:{get_client_ip(request)}"

    window = settings.RATE_LIMIT_ACCOUNT_WINDOW
    max_req = settings.RATE_LIMIT_PER_ACCOUNT
    if not rate_limiter.allow(key, max_req, window):
        from starlette.responses import JSONResponse
        retry = rate_limiter.retry_after(key, window)
        return JSONResponse(
            status_code=429,
            content={"detail": f"Quá nhiều yêu cầu. Vui lòng thử lại sau {retry} giây."},
            headers={"Retry-After": str(retry)},
        )

    return await call_next(request)


@app.middleware("http")
async def attach_current_user(request, call_next):
    """Gắn user hiện tại vào request.state để các trang web/template sử dụng."""
    from config.auth import get_current_user
    request.state.current_user = get_current_user(request)
    response = await call_next(request)
    return response

# Mount shared static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Mount uploads directory for serving uploaded files
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Local Swagger UI (Offline support)
try:
    import swagger_ui_bundle
    swagger_ui_path = os.path.join(
        os.path.dirname(swagger_ui_bundle.__file__),
        "vendor", "swagger-ui-3.52.0"
    )
    app.mount("/swagger-ui", StaticFiles(directory=swagger_ui_path), name="swagger-ui")
except ImportError:
    pass


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description="REST API for Telegram Drive personal cloud storage",
        routes=app.routes,
        openapi_version="3.0.3",
    )

    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Token JWT từ /api/auth/login hoặc cookie tdrive_token.",
        }
    }

    PUBLIC_ENDPOINTS = {
        ("POST", "/api/auth/register"),
        ("POST", "/api/auth/login"),
        ("GET", "/api/auth/status"),
    }

    def _endpoint_requires_auth(route, src: str) -> bool:
        """Xác định endpoint yêu cầu xác thực.

        - Có __auth_required__ (decorator @require_auth) → YÊU CẦU
        - Source gọi require_user() hoặc require_superuser() → YÊU CẦU
        - Endpoint thuộc PUBLIC_ENDPOINTS → KHÔNG
        """
        for method in route.methods:
            if method == "OPTIONS":
                continue
            if (method, route.path) in PUBLIC_ENDPOINTS:
                return False
        if getattr(route.endpoint, "__auth_required__", False):
            return True
        if "require_user(" in src or "require_superuser(" in src:
            return True
        return False

    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/"):
            import inspect
            try:
                src = inspect.getsource(route.endpoint)
            except (OSError, TypeError):
                continue

            if _endpoint_requires_auth(route, src):
                path_item = openapi_schema["paths"].get(route.path)
                if path_item:
                    for method in route.methods:
                        if method == "OPTIONS":
                            continue
                        if method.lower() in path_item:
                            path_item[method.lower()].setdefault("security", []).append({"BearerAuth": []})

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi

# Include routers
app.include_router(api_router)   # Backend REST API: /api/*
app.include_router(web_router)   # Frontend Jinja2 Pages: /*
app.include_router(webdav_router) # WebDAV Protocol: /webdav/*


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return FileResponse("favicon.ico")

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{settings.APP_NAME} - Swagger UI",
        swagger_js_url="/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/swagger-ui/swagger-ui.css",
    )


@app.on_event("startup")
def startup():
    """Application startup event."""
    init_db()
    # Tạo admin đầu tiên từ .env nếu bảng users rỗng
    from config.database import get_session, close_session
    from api.auth.service import bootstrap_initial_admin
    db = get_session()
    try:
        bootstrap_initial_admin(db)
    finally:
        close_session(db)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)