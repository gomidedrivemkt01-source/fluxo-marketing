import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.bulk_demands import router as bulk_demands_router
from app.api.catalogs import router as catalogs_router
from app.api.collaboration import router as collaboration_router
from app.api.daily_imports import router as daily_imports_router
from app.api.demands import router as demands_router
from app.api.errors import ApiError, api_error_handler
from app.api.files import router as files_router
from app.api.files import signed_router as signed_files_router
from app.api.governance import router as governance_router
from app.api.management import router as management_router
from app.api.reports import router as reports_router
from app.api.time_tracking import active_router as active_time_tracking_router
from app.api.time_tracking import router as time_tracking_router
from app.api.users import router as users_router
from app.api.work_content import catalog_router as work_catalog_router
from app.api.work_content import demand_router as work_demand_router
from app.api.workspace import router as workspace_router
from app.auth.router import router as auth_router
from app.core.config import get_settings
from app.retention import retention_loop

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    retention_task = (
        asyncio.create_task(retention_loop()) if settings.retention_scheduler_enabled else None
    )
    yield
    if retention_task is not None:
        retention_task.cancel()
        with suppress(asyncio.CancelledError):
            await retention_task


app = FastAPI(
    title=f"{settings.name} API",
    version="0.1.0",
    docs_url="/api/docs" if settings.env != "production" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.env != "production" else None,
    lifespan=lifespan,
)
app.add_exception_handler(ApiError, api_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


@app.middleware("http")
async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
    started_at = perf_counter()
    request_id = request.headers.get("X-Request-ID", "")[:80] or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    elapsed_ms = (perf_counter() - started_at) * 1000
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    elif not request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-cache"
    if elapsed_ms >= 750:
        logger.warning(
            "slow_request method=%s path=%s status=%s duration_ms=%.1f request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
    return response


def validation_message(error: dict[str, Any]) -> str:
    kind = error["type"]
    context = error.get("ctx", {})
    if kind == "missing":
        return "Preencha este campo."
    if kind == "string_too_long":
        return f"Use no máximo {context.get('max_length')} caracteres."
    if kind == "string_too_short":
        return f"Use pelo menos {context.get('min_length')} caracteres."
    if kind.startswith("datetime"):
        return "Informe uma data e horário válidos, com o fuso horário no arquivo JSON."
    if kind == "string_pattern_mismatch":
        if error["loc"][-1] in {"externalId", "batchId"}:
            return "Use letras sem acento, números e os caracteres . _ : / -, sem espaços."
        return "Escolha uma das opções disponíveis para este campo."
    if kind == "timezone_aware":
        return "Inclua o fuso horário na data, por exemplo 2026-12-10T17:00:00-03:00."
    if kind in {"too_long", "too_short"}:
        limit = context.get("max_length" if kind == "too_long" else "min_length")
        return f"Use {'no máximo' if kind == 'too_long' else 'pelo menos'} {limit} item(ns)."
    if kind == "extra_forbidden":
        return "Este campo não faz parte do modelo. Confira o JSON de referência."
    if kind == "value_error":
        return str(error["msg"]).removeprefix("Value error, ")
    return "Confira o formato e o valor deste campo."


def validation_field(error: dict[str, Any], body: Any) -> str:
    path = error["loc"][1:]
    if (
        len(path) >= 3
        and path[0] == "answers"
        and isinstance(path[1], int)
        and path[2] == "value"
        and isinstance(body, dict)
    ):
        answers = body.get("answers", [])
        if (
            isinstance(answers, list)
            and path[1] < len(answers)
            and isinstance(answers[path[1]], dict)
        ):
            try:
                return str(uuid.UUID(str(answers[path[1]].get("fieldId"))))
            except (ValueError, TypeError):
                pass
    return ".".join(str(part) for part in path)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "Revise os campos informados.",
            "requestId": request.state.request_id,
            "fieldErrors": [
                {
                    "field": validation_field(error, exc.body),
                    "type": error["type"],
                    "message": validation_message(error),
                }
                for error in exc.errors()
            ],
        },
    )


app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(catalogs_router, prefix="/api/v1")
app.include_router(management_router, prefix="/api/v1")
app.include_router(demands_router, prefix="/api/v1")
app.include_router(bulk_demands_router, prefix="/api/v1")
app.include_router(daily_imports_router, prefix="/api/v1")
app.include_router(work_catalog_router, prefix="/api/v1")
app.include_router(work_demand_router, prefix="/api/v1")
app.include_router(collaboration_router, prefix="/api/v1")
app.include_router(files_router, prefix="/api/v1")
app.include_router(signed_files_router, prefix="/api/v1")
app.include_router(time_tracking_router, prefix="/api/v1")
app.include_router(active_time_tracking_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(governance_router, prefix="/api/v1")
app.include_router(workspace_router, prefix="/api/v1")


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.exists():
    assets = frontend_dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def frontend(full_path: str) -> FileResponse:
        candidate = (frontend_dist / full_path).resolve()
        if candidate.is_file() and frontend_dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(frontend_dist / "index.html")
