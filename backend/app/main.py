import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.api.catalogs import router as catalogs_router
from app.api.collaboration import router as collaboration_router
from app.api.daily_imports import router as daily_imports_router
from app.api.demands import router as demands_router
from app.api.errors import ApiError, api_error_handler
from app.api.users import router as users_router
from app.api.work_content import catalog_router as work_catalog_router
from app.api.work_content import demand_router as work_demand_router
from app.auth.router import router as auth_router
from app.core.config import get_settings

settings = get_settings()
app = FastAPI(
    title=f"{settings.name} API",
    version="0.1.0",
    docs_url="/api/docs" if settings.env != "production" else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.env != "production" else None,
)
app.add_exception_handler(ApiError, api_error_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
    request_id = request.headers.get("X-Request-ID", "")[:80] or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "Revise os campos informados.",
            "requestId": request.state.request_id,
            "fieldErrors": [
                {"field": ".".join(str(part) for part in error["loc"][1:]), "type": error["type"]}
                for error in exc.errors()
            ],
        },
    )


app.include_router(auth_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(catalogs_router, prefix="/api/v1")
app.include_router(demands_router, prefix="/api/v1")
app.include_router(daily_imports_router, prefix="/api/v1")
app.include_router(work_catalog_router, prefix="/api/v1")
app.include_router(work_demand_router, prefix="/api/v1")
app.include_router(collaboration_router, prefix="/api/v1")


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
