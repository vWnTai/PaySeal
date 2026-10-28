from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings
from app.services.runtime import root_authority


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            },
            ensure_ascii=False,
        )


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
logger = logging.getLogger("payseal")


@asynccontextmanager
async def lifespan(_: FastAPI):
    root_authority().ensure()
    yield


app = FastAPI(
    title="PaySeal API",
    version="1.0.0",
    description="Signed payment verification, business review and guarded payment-provider integration.",
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)


@app.exception_handler(RequestValidationError)
async def safe_validation_error(_: Request, error: RequestValidationError):
    # Pydantic's default error response includes raw input, including failed API-key fields.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {"loc": list(item["loc"]), "msg": item["msg"], "type": item["type"]}
                for item in error.errors()
            ]
        },
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Organization-ID",
        "X-CSRF-Token",
        "X-Correlation-ID",
        "Idempotency-Key",
    ],
)

rate_buckets: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def request_security(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID", "")
    try:
        uuid.UUID(correlation_id)
    except ValueError:
        correlation_id = str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    path = request.url.path
    limit, window = (
        (10, 60)
        if path.startswith("/api/v1/auth/")
        else ((60, 60) if path.startswith("/api/v1/public/verify/") else (0, 0))
    )
    if limit:
        forwarded_for = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        client_ip = forwarded_for or (request.client.host if request.client else "unknown")
        key = f"{client_ip}:{'auth' if '/auth/' in path else 'verify'}"
        now = time.monotonic()
        bucket = rate_buckets[key]
        while bucket and bucket[0] <= now - window:
            bucket.popleft()
        if len(bucket) >= limit:
            return JSONResponse(
                {"detail": "Rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": "60", "X-Correlation-ID": correlation_id},
            )
        bucket.append(now)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled request error correlation_id=%s path=%s", correlation_id, path)
        if settings.environment == "production":
            response = JSONResponse(
                {"detail": "Internal server error", "correlation_id": correlation_id},
                status_code=500,
            )
        else:
            raise
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if path.startswith("/api/"):
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    elif path.startswith("/docs"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self' https://cdn.jsdelivr.net; script-src 'self' https://cdn.jsdelivr.net; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:"
        )
    logger.info(
        "request correlation_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        correlation_id,
        request.method,
        path,
        response.status_code,
        (time.perf_counter() - started) * 1000,
    )
    return response


app.include_router(api_router, prefix="/api/v1")


@app.get("/healthz", tags=["Operations"])
def healthz():
    return {"status": "ok"}
