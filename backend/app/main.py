"""FastAPI application entry point."""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.exceptions import AppException, app_exception_handler
from app.core.logging_config import setup_logging, trace_id_var

# Apply structured JSON logging before anything else logs.
setup_logging(settings.LOG_LEVEL)

# Ensure all models are registered with SQLAlchemy
import app.models  # noqa: F401

logger = logging.getLogger("skdy.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期。POC 流程不需要后台 SLA 扫描任务。"""
    yield


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Generate/read trace_id and log one line per request."""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("x-trace-id") or str(uuid.uuid4())
        trace_id_var.set(trace_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.exception(
                "request failed",
                extra={
                    "trace_id": trace_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration_ms, 2),
                    "client_ip": request.client.host if request.client else None,
                },
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000

        logger.info(
            "request",
            extra={
                "trace_id": trace_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": request.client.host if request.client else None,
            },
        )
        response.headers["x-trace-id"] = trace_id
        return response


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# Request logging first so CORS preflight and all routes are captured.
app.add_middleware(RequestLoggingMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)


# ── Routers ───────────────────────────────────────────────
from app.api.v1 import attachments, auth, common, tickets

app.include_router(auth.router, prefix="/api/v1")
app.include_router(tickets.router, prefix="/api/v1")
app.include_router(attachments.router, prefix="/api/v1")
app.include_router(common.users_router, prefix="/api/v1")
app.include_router(common.skill_groups_router, prefix="/api/v1")
app.include_router(common.meta_router, prefix="/api/v1")
app.include_router(common.stats_router, prefix="/api/v1")


# ── Health ───────────────────────────────────────────────

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    # TODO: check DB + Redis connectivity
    return {"status": "ok"}
