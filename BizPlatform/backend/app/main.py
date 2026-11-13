import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import Base, engine
from .routers import auth, inventory, invoices, people, reports, users

settings = get_settings()
log = logging.getLogger("bizplatform")



@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="BizPlatform API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs" if settings.is_dev else None,
              redoc_url=None, openapi_url="/api/openapi.json" if settings.is_dev else None)

SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
MAX_BODY = 1_000_000  # 1 MB – no endpoint needs more


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_BODY:
        return JSONResponse({"detail": "הבקשה גדולה מדי"}, status_code=413)
    try:
        response = await call_next(request)
    except Exception:  # never leak stack traces to clients
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        response = JSONResponse({"detail": "שגיאת שרת פנימית"}, status_code=500)
    for k, v in SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]), "msg": e["msg"]} for e in exc.errors()]
    return JSONResponse({"detail": "נתונים לא תקינים", "errors": errors}, status_code=422)


@app.get("/api/health")
def health():
    return {"status": "ok"}


for r in (auth.router, users.router, people.suppliers_router, people.customers_router, people.warehouses_router,
          people.departments_router, people.employees_router, people.assets_router, inventory.products_router,
          inventory.stock_router, invoices.router, reports.router):
    app.include_router(r)


