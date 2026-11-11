from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass(slots=True)
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, object] | None = None


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    request_id = getattr(request.state, "request_id", None)
    fields = {
        "company_invalid": "companyId",
        "category_invalid": "categoryId",
        "assignee_invalid": "assigneeId",
        "stage_invalid": "stageId",
        "stage_workflow_mismatch": "stageId",
        "workflow_invalid": "workflowId",
        "workflow_required": "workflowId",
        "return_comment_required": "comment",
        "briefing_requires_category": "categoryId",
        "active_timer_requires_closure": "time",
    }
    details = exc.details or {}
    if exc.code in fields and "fieldErrors" not in details:
        details = {**details, "fieldErrors": [{"field": fields[exc.code], "message": exc.message}]}
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "requestId": request_id, **details},
    )
