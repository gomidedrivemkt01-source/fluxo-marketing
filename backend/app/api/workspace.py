from typing import Literal

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


WorkspacePage = Literal[
    "overview",
    "my-work",
    "demands",
    "calendar",
    "companies",
    "team",
    "reports",
    "intelligence",
    "workflows",
    "categories",
    "users",
    "settings",
    "profile",
]


class WorkspacePageOut(BaseModel):
    """Dados opcionais carregados somente pela rota que realmente os usa."""

    companies: list[CompanyOut] | None = None
    categories: list[CategoryOut] | None = None
    workflows: list[WorkflowOut] | None = None
    stages: list[WorkflowStageOut] | None = None
    people: list[UserOptionOut] | None = None
    demands: list[DemandOut] | None = None
    profile: ProfileOut


def _catalog_data(
    principal: Principal,
    db: Session,
) -> tuple[
    list[CompanyOut],
    list[CategoryOut],
    list[WorkflowOut],
    list[WorkflowStageOut],
    list[UserOptionOut],
]:
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
    return (
        [CompanyOut.model_validate(item) for item in companies],
        [CategoryOut.model_validate(item) for item in categories],
        [WorkflowOut.model_validate(item) for item in workflows],
        [WorkflowStageOut.model_validate(item) for item in stages],
        list_user_options(principal=principal, db=db),
    )


@router.get(
    "/pages/{page}",
    response_model=WorkspacePageOut,
    response_model_exclude_none=True,
)
def workspace_page(
    page: WorkspacePage,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> WorkspacePageOut:
    """Carrega somente os conjuntos necessários para a página solicitada.

    As telas operacionais compartilham a mesma carteira. Páginas administrativas,
    perfil e relatórios deixam de pagar o custo de serializar todas as demandas.
    """
    profile = get_my_profile(principal=principal)
    operational_pages = {"my-work", "demands"}

    if page in operational_pages or page == "workflows":
        companies, categories, workflows, stages, people = _catalog_data(principal, db)
        return WorkspacePageOut(
            companies=companies,
            categories=categories,
            workflows=workflows,
            stages=stages,
            people=people,
            demands=list_demands(q=None, principal=principal, db=db),
            profile=profile,
        )
    if page == "overview":
        return WorkspacePageOut(
            demands=list_demands(q=None, principal=principal, db=db),
            profile=profile,
        )
    if page == "calendar":
        companies = list_companies(include_inactive=False, principal=principal, db=db)
        return WorkspacePageOut(
            companies=[CompanyOut.model_validate(item) for item in companies],
            people=list_user_options(principal=principal, db=db),
            demands=list_demands(q=None, principal=principal, db=db),
            profile=profile,
        )
    if page == "companies":
        companies = list_companies(include_inactive=False, principal=principal, db=db)
        return WorkspacePageOut(
            companies=[CompanyOut.model_validate(item) for item in companies],
            profile=profile,
        )
    if page == "categories":
        categories = list_categories(principal=principal, db=db)
        workflows = list_workflows(
            include_inactive=False,
            include_draft=False,
            principal=principal,
            db=db,
        )
        return WorkspacePageOut(
            categories=[CategoryOut.model_validate(item) for item in categories],
            workflows=[WorkflowOut.model_validate(item) for item in workflows],
            profile=profile,
        )
    if page in {"team", "reports"}:
        return WorkspacePageOut(
            people=list_user_options(principal=principal, db=db),
            profile=profile,
        )
    if page == "intelligence":
        return WorkspacePageOut(
            demands=list_demands(q=None, principal=principal, db=db),
            profile=profile,
        )
    return WorkspacePageOut(profile=profile)


@router.get("/bootstrap", response_model=WorkspaceBootstrapOut)
def workspace_bootstrap(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> WorkspaceBootstrapOut:
    """Entrega em uma chamada os dados comuns a todas as telas autenticadas."""
    companies, categories, workflows, stages, people = _catalog_data(principal, db)
    return WorkspaceBootstrapOut(
        companies=companies,
        categories=categories,
        workflows=workflows,
        stages=stages,
        people=people,
        demands=list_demands(q=None, principal=principal, db=db),
        profile=get_my_profile(principal=principal),
    )
