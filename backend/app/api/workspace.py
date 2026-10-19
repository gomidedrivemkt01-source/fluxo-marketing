from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.catalogs import (
    CategoryOut,
    CompanyOut,
    WorkflowOut,
    WorkflowStageOut,
    list_categories,
    list_companies,
    list_workflow_stages,
    list_workflows,
)
from app.api.demands import DemandOut, list_demands
from app.api.users import ProfileOut, UserOptionOut, get_my_profile, list_user_options
from app.auth.dependencies import get_principal
from app.auth.service import Principal
from app.database import get_db

router = APIRouter(prefix="/workspace", tags=["Workspace"])


class WorkspaceBootstrapOut(BaseModel):
    companies: list[CompanyOut]
    categories: list[CategoryOut]
    workflows: list[WorkflowOut]
    stages: list[WorkflowStageOut]
    people: list[UserOptionOut]
    demands: list[DemandOut]
    profile: ProfileOut


@router.get("/bootstrap", response_model=WorkspaceBootstrapOut)
def workspace_bootstrap(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> WorkspaceBootstrapOut:
    """Entrega em uma chamada os dados comuns a todas as telas autenticadas."""
    companies = list_companies(include_inactive=False, principal=principal, db=db)
    categories = list_categories(principal=principal, db=db)
    workflows = list_workflows(
        include_inactive=False,
        include_draft=False,
        principal=principal,
        db=db,
    )
    stages = list_workflow_stages(
        include_inactive=False,
        include_draft=False,
        workflow_id=None,
        all_workflows=True,
        principal=principal,
        db=db,
    )
    return WorkspaceBootstrapOut(
        companies=[CompanyOut.model_validate(item) for item in companies],
        categories=[CategoryOut.model_validate(item) for item in categories],
        workflows=[WorkflowOut.model_validate(item) for item in workflows],
        stages=[WorkflowStageOut.model_validate(item) for item in stages],
        people=list_user_options(principal=principal, db=db),
        demands=list_demands(q=None, principal=principal, db=db),
        profile=get_my_profile(principal=principal),
    )
