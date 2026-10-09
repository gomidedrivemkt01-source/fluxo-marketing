import uuid
from datetime import UTC, datetime, timedelta

from app.api.reports import build_operational_report
from app.models import Company, Demand, DemandCategory, TimeEntry, UserProfile, WorkflowStage


def _demand(
    *,
    organization_id: uuid.UUID,
    created_by: uuid.UUID,
    public_id: str,
    status: str,
    created_at: datetime,
    deadline_at: datetime | None,
    priority: str = "NORMAL",
    company_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
    assignee_id: uuid.UUID | None = None,
    stage_id: uuid.UUID | None = None,
    expected_minutes: int | None = None,
) -> Demand:
    return Demand(
        id=uuid.uuid4(),
        organization_id=organization_id,
        public_id=public_id,
        title=f"Demanda {public_id}",
        created_by=created_by,
        created_at=created_at,
        updated_at=created_at,
        status=status,
        priority=priority,
        deadline_at=deadline_at,
        primary_company_id=company_id,
        category_id=category_id,
        current_assignee_id=assignee_id,
        current_stage_id=stage_id,
        expected_effort_minutes=expected_minutes,
    )


def test_operational_report_consolidates_portfolio_and_time() -> None:
    now = datetime(2026, 10, 9, 12, tzinfo=UTC)
    organization_id = uuid.uuid4()
    profile_id = uuid.uuid4()
    company_id = uuid.uuid4()
    category_id = uuid.uuid4()
    stage_id = uuid.uuid4()
    profile = UserProfile(
        id=profile_id,
        auth_user_id=uuid.uuid4(),
        email="pessoa@example.com",
        full_name="Pessoa Teste",
    )
    company = Company(
        id=company_id,
        organization_id=organization_id,
        name="Empresa Teste",
        short_name="Teste",
        code="TESTE",
        color="#155E75",
    )
    category = DemandCategory(
        id=category_id,
        organization_id=organization_id,
        name="Vídeo",
        code="VIDEO",
        color="#475569",
    )
    stage = WorkflowStage(
        id=stage_id,
        organization_id=organization_id,
        name="Produção",
        code="PRODUCAO",
        color="#087F76",
        position=1,
    )
    overdue = _demand(
        organization_id=organization_id,
        created_by=profile_id,
        public_id="DMD-1",
        status="BLOCKED",
        created_at=now - timedelta(days=5),
        deadline_at=now - timedelta(days=1),
        priority="URGENT",
        expected_minutes=120,
    )
    completed = _demand(
        organization_id=organization_id,
        created_by=profile_id,
        public_id="DMD-2",
        status="COMPLETED",
        created_at=now - timedelta(days=40),
        deadline_at=now - timedelta(days=2),
        company_id=company_id,
        category_id=category_id,
        assignee_id=profile_id,
        stage_id=stage_id,
    )
    due_soon = _demand(
        organization_id=organization_id,
        created_by=profile_id,
        public_id="DMD-3",
        status="IN_PROGRESS",
        created_at=now - timedelta(days=2),
        deadline_at=now + timedelta(days=3),
        company_id=company_id,
        category_id=category_id,
        assignee_id=profile_id,
        stage_id=stage_id,
        expected_minutes=60,
    )
    entries = [
        TimeEntry(
            id=uuid.uuid4(),
            organization_id=organization_id,
            demand_id=completed.id,
            user_profile_id=profile_id,
            source="manual",
            state="COMPLETED",
            started_at=now - timedelta(days=4),
            duration_minutes=30,
        ),
        TimeEntry(
            id=uuid.uuid4(),
            organization_id=organization_id,
            demand_id=due_soon.id,
            user_profile_id=profile_id,
            source="timer",
            state="PAUSED",
            started_at=now - timedelta(days=1),
            duration_minutes=90,
        ),
    ]

    report = build_operational_report(
        demands=[overdue, completed, due_soon],
        entries=entries,
        companies={company_id: company},
        categories={category_id: category},
        profiles={profile_id: profile},
        stages={stage_id: stage},
        days=30,
        now=now,
    )

    assert report.summary.total_demands == 3
    assert report.summary.created_in_period == 2
    assert report.summary.completed_demands == 1
    assert report.summary.overdue == 1
    assert report.summary.due_soon == 1
    assert report.summary.blocked == 1
    assert report.summary.unassigned == 1
    assert report.summary.urgent == 1
    assert report.summary.tracked_minutes == 120
    assert report.summary.expected_minutes == 180
    assert report.by_stage[0].label == "Produção"
    assert report.by_stage[0].count == 1
    assert report.by_assignee[0].label == "Pessoa Teste"
    assert report.by_assignee[0].total_minutes == 90
    assert report.attention[0].public_id == "DMD-1"
    assert report.attention[0].reasons == ["Prazo vencido", "Bloqueada", "Urgente", "Sem responsável"]
