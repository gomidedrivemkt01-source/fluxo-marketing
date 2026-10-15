"""Blueprint versionado do manual operacional de Marketing Gomide v1."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.demands import ensure_workflow_version
from app.auth.service import Principal
from app.models import (
    AuditEvent,
    BriefingField,
    BriefingTemplate,
    BriefingTemplateVersion,
    CategoryTemplateBinding,
    ChecklistTemplateItem,
    DemandCategory,
    JobRole,
    MemberRoleAssignment,
    Membership,
    MembershipStatus,
    UserProfile,
    Workflow,
    WorkflowStage,
    utc_now,
)

BLUEPRINT_CODE = "MARKETING_GOMIDE_V1"

ROLE_NAMES = {
    "STRATEGY_APPROVAL": "Estratégia, aprovação e priorização",
    "COPY_CONTENT": "Copy, redação e conteúdo",
    "EDITORIAL_PUBLICATION": "Planejamento editorial e publicação",
    "DESIGN_AUDIOVISUAL": "Design, edição e audiovisual",
    "TECH_AUTOMATION": "Tecnologia e automações",
    "COMMERCIAL_RELATIONSHIP": "Comercial e relacionamento",
    "LOGISTICS_SUPPLIERS": "Logística e fornecedores",
    "TECHNICAL_SPECIALIST": "Especialista técnico",
    "DEFINED_OWNER": "Responsável definido no card",
    "DEFINED_REVIEWER": "Revisor definido no card",
}

# Nomes iniciais definidos pelo manual. A associação continua configurável e usa IDs;
# estes nomes servem apenas para preparar automaticamente quem já está cadastrado.
ROLE_PROFILE_MATCHES = {
    "STRATEGY_APPROVAL": ("João Guimarães",),
    "COPY_CONTENT": ("Maria",),
    "EDITORIAL_PUBLICATION": ("Natália",),
    "DESIGN_AUDIOVISUAL": ("Sivas Junior",),
    "TECH_AUTOMATION": ("Junior (TI)",),
    "COMMERCIAL_RELATIONSHIP": ("Eduarda",),
    "LOGISTICS_SUPPLIERS": ("Danilo",),
}

GLOBAL_FIELDS = [
    "Objetivo",
    "Público",
    "Entregável",
    "Data final",
    "Objetivo SMART",
    "OKR vinculado",
    "KPI primário",
    "Baseline do KPI",
    "Janela de medição",
    "Fonte de mensuração",
    "Referências",
    "Dependências",
    "Aprovador",
    "Critério de aceite",
]

StageSpec = tuple[str, str, str]

BLUEPRINTS: dict[str, dict[str, Any]] = {
    "AUTOMATION": {
        "name": "Automação",
        "fields": ["Processo atual", "Problema", "Gatilho", "Condições", "Ações", "Exceções", "Sistemas", "Entradas e saídas", "Frequência", "Alerta", "Contingência", "Responsável de manutenção"],
        "okr": ["O1", "O4"],
        "kpis": ["Taxa de sucesso", "Falhas", "Intervenções", "Horas poupadas", "Volume", "Tempo de recuperação"],
        "stages": [
            ("Briefing", "STRATEGY_APPROVAL", "Problema, regra de negócio e aceite definidos."),
            ("Mapeamento", "TECH_AUTOMATION", "Gatilhos, exceções, permissões e dados mapeados."),
            ("Construção", "TECH_AUTOMATION", "Fluxo em teste, logs e segurança configurados."),
            ("Testes", "TECH_AUTOMATION", "Cenários normal, falha, duplicidade e rollback testados."),
            ("Validação", "STRATEGY_APPROVAL", "Regras e efeitos colaterais aprovados."),
            ("Ativação", "TECH_AUTOMATION", "Produção, alertas e monitoramento ativos."),
            ("Monitoramento inicial", "TECH_AUTOMATION", "Estabilidade e falhas documentadas."),
            ("Concluída", "STRATEGY_APPROVAL", "Documentação e manutenção atribuídas."),
        ],
    },
    "BLOG": {
        "name": "Blog",
        "fields": ["Tema", "Marca", "Search intent", "Persona", "Problema", "Keyword", "Termos relacionados", "Perguntas", "Ângulo", "Fontes", "Links internos", "CTA", "Especialista", "Distribuição"],
        "okr": ["O2", "O3"],
        "kpis": ["Indexação", "Impressões", "Cliques", "CTR", "Posição", "Tráfego", "Conversões"],
        "stages": [
            ("Briefing", "STRATEGY_APPROVAL", "Intenção, tema, público, KPI e especialista definidos."),
            ("Pesquisa/SEO", "COPY_CONTENT", "SERP, fontes, palavras-chave e H2/H3 definidos."),
            ("Redação", "COPY_CONTENT", "Artigo, links, CTA e referências concluídos."),
            ("Revisão técnica", "TECHNICAL_SPECIALIST", "Normas, datas e exemplos conferidos."),
            ("Aprovação editorial", "STRATEGY_APPROVAL", "Clareza, posicionamento e estratégia aprovados."),
            ("Publicação/SEO", "COPY_CONTENT", "WordPress, Yoast, slug, meta, imagens, schema e links validados."),
            ("Distribuição", "EDITORIAL_PUBLICATION", "Canais, calendário e links revisados."),
            ("Concluída", "EDITORIAL_PUBLICATION", "URL, indexação monitorável e KPI registrados."),
        ],
    },
    "CAMPAIGN": {
        "name": "Campanha",
        "fields": ["Objetivo comercial", "Oferta", "Persona", "Segmentação", "Jornada", "Proposta", "Mensagem", "Canais", "Período", "Orçamento", "Conversão", "Destino", "Tracking", "Assets"],
        "okr": ["O1", "O3"],
        "kpis": ["Leads", "MQL", "CPL", "CPA", "CTR", "CPM", "Frequência", "Conversão", "Receita atribuída"],
        "parent": True,
        "stages": [
            ("Briefing", "STRATEGY_APPROVAL", "Resultado, público, oferta, verba e KPI definidos."),
            ("Estratégia", "STRATEGY_APPROVAL", "Hipóteses, canais, jornada e metas definidos."),
            ("Desdobramento", "EDITORIAL_PUBLICATION", "Cards filhos, datas e dependências registrados."),
            ("Ativos prontos", "EDITORIAL_PUBLICATION", "Todos os entregáveis dependentes aprovados."),
            ("Tracking", "STRATEGY_APPROVAL", "UTM, eventos, CRM e formulários validados."),
            ("Validação", "STRATEGY_APPROVAL", "Oferta, criativos, orçamento e tracking aprovados."),
            ("Ativação", "STRATEGY_APPROVAL", "Campanha no ar e eventos recebidos."),
            ("Otimização", "STRATEGY_APPROVAL", "Hipóteses e ajustes registrados."),
            ("Relatório", "STRATEGY_APPROVAL", "Resultados e decisão de continuidade registrados."),
        ],
    },
    "CAROUSEL": {
        "name": "Carrossel",
        "fields": ["Tema", "Persona", "Dor", "Tese", "Promessa da capa", "Sequência", "CTA", "Fontes", "Quantidade de lâminas", "Referências"],
        "okr": ["O2", "O3"],
        "kpis": ["Salvamentos", "Compartilhamentos", "Alcance", "Visitas", "Cliques"],
        "stages": [
            ("Briefing", "EDITORIAL_PUBLICATION", "Objetivo, tese, fonte e KPI definidos."),
            ("Copy", "COPY_CONTENT", "Capa, progressão, slides e CTA concluídos."),
            ("Design", "DESIGN_AUDIOVISUAL", "Legibilidade, identidade e formatos validados."),
            ("Revisão", "COPY_CONTENT", "Sequência, gramática e dados conferidos."),
            ("Aprovação", "STRATEGY_APPROVAL", "Qualidade estratégica e visual aprovadas."),
            ("Legenda", "COPY_CONTENT", "Contexto e CTA concluídos."),
            ("Agendamento", "EDITORIAL_PUBLICATION", "Perfil, data e arquivos corretos."),
            ("Publicação", "EDITORIAL_PUBLICATION", "URL e métrica registradas."),
        ],
    },
    "INTERNAL_MARKETING": {
        "name": "Endomarketing",
        "fields": ["Motivo", "Público interno", "Comportamento desejado", "Mensagem", "Canal", "Data", "Liderança", "Sensibilidade", "Materiais"],
        "okr": ["O1", "O4"],
        "kpis": ["Adesão", "Participação", "Presença", "Respostas", "Feedback"],
        "stages": [
            ("Briefing", "STRATEGY_APPROVAL", "Público e mudança esperada definidos."),
            ("Estratégia", "STRATEGY_APPROVAL", "Tom, canal, timing e riscos definidos."),
            ("Copy", "COPY_CONTENT", "Mensagem e orientação objetivas."),
            ("Produção visual", "DESIGN_AUDIOVISUAL", "Peça clara e adequada."),
            ("Validação", "STRATEGY_APPROVAL", "Coerência cultural e conteúdo aprovados."),
            ("Distribuição", "EDITORIAL_PUBLICATION", "Público, canal e horário conferidos."),
            ("Mensuração", "STRATEGY_APPROVAL", "Adesão e retorno mensurados."),
            ("Concluída", "STRATEGY_APPROVAL", "Evidência e aprendizado registrados."),
        ],
    },
    "STATIC": {
        "name": "Estático",
        "fields": ["Mensagem única", "Objetivo", "Público", "Headline", "CTA", "Fonte", "Referência", "Canal"],
        "okr": ["O2", "O3"],
        "kpis": ["Alcance", "Compartilhamentos", "Cliques", "Visitas", "Conversões"],
        "stages": [
            ("Briefing", "EDITORIAL_PUBLICATION", "Justificativa do formato e KPI definidos."),
            ("Copy", "COPY_CONTENT", "Headline, apoio e CTA concluídos."),
            ("Design", "DESIGN_AUDIOVISUAL", "Contraste, hierarquia e marca validados."),
            ("Revisão", "COPY_CONTENT", "Texto e dados conferidos."),
            ("Aprovação", "STRATEGY_APPROVAL", "Relevância e posicionamento aprovados."),
            ("Agendamento", "EDITORIAL_PUBLICATION", "Data, perfil e legenda conferidos."),
            ("Publicação", "EDITORIAL_PUBLICATION", "URL e KPI registrados."),
        ],
    },
    "EVENT": {
        "name": "Evento",
        "fields": ["Nome", "Objetivo", "Formato", "Data", "Local", "Público", "Capacidade", "Meta", "Parceiros", "Orçamento", "Inscrições", "Comunicação", "Leads", "Pós-evento"],
        "okr": ["O1", "O3"],
        "kpis": ["Inscrições", "Presença", "Show rate", "CPL", "Reuniões", "NPS", "Custo por participante"],
        "parent": True,
        "stages": [
            ("Briefing", "STRATEGY_APPROVAL", "Objetivo, público e orçamento definidos."),
            ("Planejamento", "STRATEGY_APPROVAL", "Cronograma e dependências definidos."),
            ("Logística", "LOGISTICS_SUPPLIERS", "Local, fornecedores e materiais confirmados."),
            ("Jornada comercial", "COMMERCIAL_RELATIONSHIP", "Inscrição, atendimento e CRM validados."),
            ("Comunicação", "EDITORIAL_PUBLICATION", "Cards filhos e cobertura organizados."),
            ("Checkpoint", "STRATEGY_APPROVAL", "Equipe, listas, tracking e local conferidos."),
            ("Execução", "COMMERCIAL_RELATIONSHIP", "Recepção e captação executadas."),
            ("Pós-evento", "COMMERCIAL_RELATIONSHIP", "Follow-up e oportunidades registrados."),
            ("Relatório", "STRATEGY_APPROVAL", "Resultados e próximos passos registrados."),
        ],
    },
    "LANDING_PAGE": {
        "name": "Landing Page",
        "fields": ["Oferta", "Público", "Origem", "Proposta", "CTA", "Campos", "CRM", "Prova social", "Objeções", "Analytics", "SEO se aplicável"],
        "okr": ["O3", "O4"],
        "kpis": ["Sessões", "Taxa de conversão", "Leads", "CPL", "Erros", "Performance técnica"],
        "stages": [
            ("Briefing", "STRATEGY_APPROVAL", "Oferta, tráfego, conversão e KPI definidos."),
            ("Arquitetura/CRO", "STRATEGY_APPROVAL", "Fluxo, argumento e CTA definidos."),
            ("Copy", "COPY_CONTENT", "Headline, benefícios e objeções concluídos."),
            ("Design", "DESIGN_AUDIOVISUAL", "Layout desktop e mobile validado."),
            ("Desenvolvimento", "TECH_AUTOMATION", "Responsividade e formulário implementados."),
            ("Integrações", "TECH_AUTOMATION", "CRM, GA4, Pixel e UTM validados."),
            ("QA", "STRATEGY_APPROVAL", "Formulário, links, copy e mobile testados."),
            ("Publicação", "TECH_AUTOMATION", "URL, SSL e eventos validados."),
            ("Monitoramento", "STRATEGY_APPROVAL", "Conversão e falhas monitoradas."),
            ("Concluída", "STRATEGY_APPROVAL", "Resultado inicial documentado."),
        ],
    },
    "GRAPHIC_MATERIAL": {
        "name": "Material Gráfico",
        "fields": ["Tipo", "Finalidade", "Dimensões", "Suporte", "Quantidade", "Fornecedor", "Sangria", "Acabamento", "Prazo", "Conteúdo", "CTA", "QR e destino"],
        "okr": ["O1", "O4"],
        "kpis": ["Pontualidade", "Retrabalho", "Custo", "Erros", "Scans", "Conversões"],
        "stages": [
            ("Briefing", "STRATEGY_APPROVAL", "Uso, dimensões e prazo definidos."),
            ("Especificação", "DESIGN_AUDIOVISUAL", "Resolução, sangria e formato conferidos."),
            ("Conteúdo", "COPY_CONTENT", "Texto, contatos e CTA conferidos."),
            ("Design", "DESIGN_AUDIOVISUAL", "Layout e identidade concluídos."),
            ("Prova", "DESIGN_AUDIOVISUAL", "QR, medidas e qualidade testados."),
            ("Aprovação", "STRATEGY_APPROVAL", "Conteúdo e arte final aprovados."),
            ("Produção", "LOGISTICS_SUPPLIERS", "Fornecedor, orçamento e prazo confirmados."),
            ("Recebimento", "LOGISTICS_SUPPLIERS", "Quantidade e integridade conferidas."),
            ("Concluída", "STRATEGY_APPROVAL", "Arquivos e evidência registrados."),
        ],
    },
    "STORY": {
        "name": "Story",
        "fields": ["Modalidade", "Objetivo", "Tema", "Frames", "Links", "Stickers", "Ativo", "Pessoa", "Urgência"],
        "okr": ["O2", "O3"],
        "kpis": ["Alcance", "Conclusão da sequência", "Saídas", "Respostas", "Cliques", "Leads"],
        "stages": [
            ("Briefing", "EDITORIAL_PUBLICATION", "Modalidade, objetivo e frames definidos."),
            ("Roteiro", "COPY_CONTENT", "Progressão e interação definidas."),
            ("Produção", "DESIGN_AUDIOVISUAL", "Vídeo ou arte legível."),
            ("Revisão", "EDITORIAL_PUBLICATION", "Ordem, links e stickers conferidos."),
            ("Aprovação", "EDITORIAL_PUBLICATION", "Rotina aprovada e conteúdos sensíveis escalados."),
            ("Publicação", "EDITORIAL_PUBLICATION", "Sequência e links testados."),
            ("Concluída", "EDITORIAL_PUBLICATION", "Evidência e KPI registrados."),
        ],
    },
    "VIDEO_REELS": {
        "name": "Vídeo Reels",
        "fields": ["Tema", "Público", "Dor", "Tese", "Gancho", "Porta-voz", "Duração", "Fontes", "Referência", "CTA", "Locação", "B-roll", "Desdobramento"],
        "okr": ["O2", "O3"],
        "kpis": ["Retenção inicial", "Watch time", "Percentual assistido", "Compartilhamentos", "Alcance", "Leads"],
        "stages": [
            ("Briefing", "EDITORIAL_PUBLICATION", "Pauta, porta-voz, data e KPI definidos."),
            ("Copy/roteiro", "COPY_CONTENT", "Gancho, tese, narrativa e fontes concluídos."),
            ("Validação técnica", "TECHNICAL_SPECIALIST", "Dados e contexto conferidos."),
            ("Aprovação roteiro", "STRATEGY_APPROVAL", "Estratégia, densidade e voz aprovadas."),
            ("Gravação", "DESIGN_AUDIOVISUAL", "Áudio, luz e takes conferidos."),
            ("Edição", "DESIGN_AUDIOVISUAL", "Cortes, legendas e ritmo concluídos."),
            ("Finalização", "DESIGN_AUDIOVISUAL", "Capa, exportação e arquivo conferidos."),
            ("Legenda", "COPY_CONTENT", "Contexto e CTA concluídos quando aplicável."),
            ("Aprovação final", "STRATEGY_APPROVAL", "Vídeo, marca e conteúdo aprovados."),
            ("Publicação", "EDITORIAL_PUBLICATION", "Perfil, data, legenda e URL conferidos."),
            ("Concluída", "EDITORIAL_PUBLICATION", "Arquivos e KPI registrados."),
        ],
    },
    "VIDEO_YOUTUBE": {
        "name": "Vídeo YouTube",
        "fields": ["Tema", "Pergunta central", "Audiência", "Título", "Thumbnail", "Capítulos", "Fontes", "Especialista", "Duração", "CTA", "Cortes"],
        "okr": ["O2", "O3"],
        "kpis": ["CTR da thumbnail", "Retenção", "Watch time", "Inscritos", "Visualizações", "Leads"],
        "stages": [
            ("Briefing", "STRATEGY_APPROVAL", "Audiência, promessa e KPI definidos."),
            ("Pesquisa", "COPY_CONTENT", "Fontes, argumento e capítulos definidos."),
            ("Roteiro", "COPY_CONTENT", "Abertura, desenvolvimento e final concluídos."),
            ("Revisão técnica", "TECHNICAL_SPECIALIST", "Precisão e exemplos conferidos."),
            ("Aprovação", "STRATEGY_APPROVAL", "Título, roteiro e proposta aprovados."),
            ("Gravação", "DESIGN_AUDIOVISUAL", "Áudio, luz e continuidade conferidos."),
            ("Edição", "DESIGN_AUDIOVISUAL", "Ritmo, gráficos e capítulos concluídos."),
            ("Thumbnail", "DESIGN_AUDIOVISUAL", "Conceito e leitura mobile validados."),
            ("SEO/publicação", "EDITORIAL_PUBLICATION", "Título, descrição e links conferidos."),
            ("Aprovação final", "STRATEGY_APPROVAL", "Vídeo e metadados aprovados."),
            ("Agendamento", "EDITORIAL_PUBLICATION", "Playlist e telas finais conferidas."),
            ("Concluída", "EDITORIAL_PUBLICATION", "URL, cortes e KPI registrados."),
        ],
    },
    "OTHER": {
        "name": "Outro",
        "fields": ["Demanda", "Razão", "Entregável", "Destinatário", "Responsável", "Prazo", "Aceite", "Dependências"],
        "okr": ["O1", "O4"],
        "kpis": ["Prazo", "Qualidade do aceite", "Retrabalho", "Esforço"],
        "stages": [
            ("Triagem", "STRATEGY_APPROVAL", "Inexistência de categoria adequada confirmada."),
            ("Briefing", "STRATEGY_APPROVAL", "Escopo e aceite definidos."),
            ("Planejamento", "DEFINED_OWNER", "Passos e prazo definidos."),
            ("Produção", "DEFINED_OWNER", "Entregável gerado."),
            ("Revisão", "DEFINED_REVIEWER", "Critérios conferidos."),
            ("Aprovação", "STRATEGY_APPROVAL", "Aceite formal registrado."),
            ("Entrega", "DEFINED_OWNER", "Evidência anexada."),
            ("Concluída", "STRATEGY_APPROVAL", "Histórico e classificação registrados."),
        ],
    },
}

STAGE_COLORS = [
    "#0F766E", "#2563EB", "#7C3AED", "#C2410C", "#0E7490", "#A21CAF",
    "#4F46E5", "#15803D", "#B45309", "#BE123C", "#0369A1", "#4338CA",
]


def stable_code(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]+", "_", normalized.upper()).strip("_")


def checklist_parts(value: str) -> list[str]:
    """Transforma o critério do manual em confirmações menores e auditáveis."""
    clean = value.strip().rstrip(".")
    parts = [item.strip() for item in re.split(r",\s*|\s+e\s+", clean) if item.strip()]
    return [item[:1].upper() + item[1:] for item in parts]


def briefing_definition(category_code: str, spec: dict[str, Any]) -> dict[str, Any]:
    global_fields = [
        {
            "key": stable_code(label).lower(),
            "label": label,
            "fieldType": "long_text" if label in {"Referências", "Dependências", "Critério de aceite"} else "text",
            "requirement": "required",
        }
        for label in GLOBAL_FIELDS
    ]
    category_fields = [
        {
            "key": f"{category_code.lower()}_{stable_code(label).lower()}",
            "label": label,
            "fieldType": "long_text",
            "requirement": (
                "conditional"
                if label in {"Especialista", "CTA", "SEO se aplicável", "B-roll"}
                else "required"
            ),
        }
        for label in spec["fields"]
    ]
    return {
        "blueprint": BLUEPRINT_CODE,
        "globalFields": global_fields,
        "categoryFields": category_fields,
        "okrOptions": spec["okr"],
        "kpiOptions": spec["kpis"],
        "parentCard": bool(spec.get("parent")),
        "targets": {"state": "TO_DEFINE"},
    }


def normalized_name(value: str) -> str:
    return stable_code(value).replace("_", " ")


def ensure_initial_role_assignments(
    db: Session,
    organization_id: Any,
    roles: dict[str, JobRole],
) -> int:
    """Associa somente nomes explicitamente definidos no manual e já cadastrados."""
    members = list(
        db.execute(
            select(Membership, UserProfile)
            .join(UserProfile, UserProfile.id == Membership.user_profile_id)
            .where(
                Membership.organization_id == organization_id,
                Membership.status == MembershipStatus.ACTIVE,
            )
        ).all()
    )
    created = 0
    for role_code, expected_names in ROLE_PROFILE_MATCHES.items():
        role = roles.get(role_code)
        if role is None:
            continue
        existing = db.scalar(
            select(MemberRoleAssignment.id).where(
                MemberRoleAssignment.organization_id == organization_id,
                MemberRoleAssignment.job_role_id == role.id,
                MemberRoleAssignment.active.is_(True),
            )
        )
        if existing:
            continue
        matches: list[Membership] = []
        for membership, profile in members:
            profile_name = normalized_name(profile.full_name)
            if any(
                profile_name == normalized_name(expected)
                or (
                    " " not in normalized_name(expected)
                    and profile_name.startswith(f"{normalized_name(expected)} ")
                )
                for expected in expected_names
            ):
                matches.append(membership)
        if len(matches) != 1:
            continue
        db.add(
            MemberRoleAssignment(
                organization_id=organization_id,
                membership_id=matches[0].id,
                job_role_id=role.id,
                priority=10,
                is_fallback=False,
                active=True,
            )
        )
        created += 1
    return created


def sync_operational_briefing_fields(
    db: Session,
    organization_id: Any,
    category: DemandCategory,
    definition: dict[str, Any],
) -> int:
    """Espelha a versão publicada na interface operacional já usada pelos cards."""
    fields = [*definition.get("globalFields", []), *definition.get("categoryFields", [])]
    existing = {
        item.key: item
        for item in db.scalars(
            select(BriefingField).where(
                BriefingField.organization_id == organization_id,
                BriefingField.category_id == category.id,
            )
        )
    }
    changed = 0
    okr_options = [str(value) for value in definition.get("okrOptions", [])]
    kpi_options = [str(value) for value in definition.get("kpiOptions", [])]
    for position, field in enumerate(fields, start=1):
        key = str(field["key"])
        label = str(field["label"])
        field_type = str(field.get("fieldType") or "text")
        options: list[str] = []
        if label == "OKR vinculado" and okr_options:
            field_type, options = "select", okr_options
        elif label == "KPI primário" and kpi_options:
            field_type, options = "select", kpi_options
        item = existing.get(key)
        if item is None:
            item = BriefingField(
                organization_id=organization_id,
                category_id=category.id,
                label=label,
                key=key,
                help_text=f"Campo publicado pelo {BLUEPRINT_CODE}.",
                field_type=field_type,
                options=options,
                required=field.get("requirement") == "required",
                position=position,
                active=True,
            )
            db.add(item)
            changed += 1
            continue
        next_values = (
            label,
            field_type,
            options,
            field.get("requirement") == "required",
            position,
            True,
        )
        current_values = (
            item.label,
            item.field_type,
            item.options,
            item.required,
            item.position,
            item.active,
        )
        if current_values != next_values:
            item.label = label
            item.field_type = field_type
            item.options = options
            item.required = field.get("requirement") == "required"
            item.position = position
            item.active = True
            item.revision += 1
            item.updated_at = utc_now()
            changed += 1
    return changed


def blueprint_preview(db: Session, principal: Principal) -> dict[str, Any]:
    organization_id = principal.membership.organization_id
    categories = {
        item.code: item
        for item in db.scalars(
            select(DemandCategory).where(
                DemandCategory.organization_id == organization_id,
                DemandCategory.active.is_(True),
            )
        )
    }
    existing = {
        item.code: item.lifecycle_state
        for item in db.scalars(
            select(Workflow).where(
                Workflow.organization_id == organization_id,
                Workflow.code.in_([f"WF_{code}" for code in BLUEPRINTS]),
            )
        )
    }
    return {
        "blueprint": BLUEPRINT_CODE,
        "categories": len(BLUEPRINTS),
        "stages": sum(len(spec["stages"]) for spec in BLUEPRINTS.values()),
        "categoryFields": sum(len(spec["fields"]) for spec in BLUEPRINTS.values()),
        "matchedCategories": sorted(code for code in BLUEPRINTS if code in categories),
        "missingCategories": sorted(code for code in BLUEPRINTS if code not in categories),
        "existingWorkflows": existing,
        "safeToApply": all(code in categories for code in BLUEPRINTS),
    }


def apply_blueprint(db: Session, principal: Principal) -> dict[str, Any]:
    preview = blueprint_preview(db, principal)
    if not preview["safeToApply"]:
        raise ValueError(f"Categorias ausentes: {', '.join(preview['missingCategories'])}")
    organization_id = principal.membership.organization_id
    roles = {
        item.code: item
        for item in db.scalars(
            select(JobRole).where(JobRole.organization_id == organization_id)
        )
    }
    roles_by_name = {item.name.casefold(): item for item in roles.values()}
    for code, name in ROLE_NAMES.items():
        role = roles.get(code) or roles_by_name.get(name.casefold())
        if role is None:
            role = JobRole(
                organization_id=organization_id,
                code=code,
                name=name,
                description="Papel operacional configurável do manual Marketing Gomide v1.",
            )
            db.add(role)
            db.flush()
        elif role.code != code:
            role.code = code
        roles[code] = role
    role_assignment_count = ensure_initial_role_assignments(db, organization_id, roles)

    categories = {
        item.code: item
        for item in db.scalars(
            select(DemandCategory).where(DemandCategory.organization_id == organization_id)
        )
    }
    workflow_count = stage_count = checklist_count = briefing_count = 0
    for category_code, spec in BLUEPRINTS.items():
        category = categories[category_code]
        workflow_code = f"WF_{category_code}"
        workflow = db.scalar(
            select(Workflow).where(
                Workflow.organization_id == organization_id,
                Workflow.code == workflow_code,
            )
        )
        if workflow and workflow.lifecycle_state != "DRAFT":
            continue
        if workflow is None:
            workflow = Workflow(
                organization_id=organization_id,
                name=f"{spec['name']} · Manual v1",
                code=workflow_code,
                description=f"Rascunho gerado por {BLUEPRINT_CODE}. Não publicado.",
                is_default=False,
                lifecycle_state="DRAFT",
                time_basis="ELAPSED",
                active=True,
            )
            db.add(workflow)
            db.flush()
            workflow_count += 1

        current_stages = {
            item.code: item
            for item in db.scalars(
                select(WorkflowStage).where(WorkflowStage.workflow_id == workflow.id)
            )
        }
        for position, (name, role_code, checklist) in enumerate(spec["stages"], start=1):
            stage_code = stable_code(name)
            stage = current_stages.get(stage_code)
            condition_rule: dict[str, object] = {}
            if role_code == "TECHNICAL_SPECIALIST":
                condition_rule = {"field": "technicalSpecialistId", "operator": "is_set"}
            if role_code in {"DEFINED_OWNER", "DEFINED_REVIEWER"}:
                condition_rule = {"resolution": role_code}
            if stage is None:
                stage = WorkflowStage(
                    organization_id=organization_id,
                    workflow_id=workflow.id,
                    name=name,
                    code=stage_code,
                    color=STAGE_COLORS[(position - 1) % len(STAGE_COLORS)],
                    position=position,
                    owner_role_id=roles[role_code].id,
                    expected_duration_hours=None,
                    sla_hours=None,
                    acceptance_rule=checklist,
                    condition_rule=condition_rule,
                    active=True,
                )
                db.add(stage)
                db.flush()
                stage_count += 1
            else:
                stage.name = name
                stage.position = position
                stage.owner_role_id = roles[role_code].id
                stage.expected_duration_hours = None
                stage.sla_hours = None
                stage.acceptance_rule = checklist
                stage.condition_rule = condition_rule
                stage.active = True
            for item_position, item_title in enumerate(checklist_parts(checklist), start=1):
                template_item = db.scalar(
                    select(ChecklistTemplateItem).where(
                        ChecklistTemplateItem.workflow_stage_id == stage.id,
                        ChecklistTemplateItem.position == item_position,
                    )
                )
                if template_item is None:
                    db.add(
                        ChecklistTemplateItem(
                            organization_id=organization_id,
                            workflow_stage_id=stage.id,
                            title=item_title,
                            description=(
                                f"Parte do critério de saída: {checklist} "
                                f"Fonte: {BLUEPRINT_CODE}."
                            ),
                            position=item_position,
                            required=True,
                        )
                    )
                    checklist_count += 1
                else:
                    template_item.title = item_title
                    template_item.description = (
                        f"Parte do critério de saída: {checklist} "
                        f"Fonte: {BLUEPRINT_CODE}."
                    )
                    template_item.required = True
                    template_item.active = True
        db.flush()
        workflow_version = ensure_workflow_version(
            db, organization_id, workflow.id, principal.profile.id
        )

        template = db.scalar(
            select(BriefingTemplate).where(BriefingTemplate.category_id == category.id)
        )
        if template is None:
            template = BriefingTemplate(
                organization_id=organization_id,
                category_id=category.id,
                code=f"BRIEFING_{category_code}",
                name=f"Briefing · {spec['name']}",
            )
            db.add(template)
            db.flush()
        definition = briefing_definition(category_code, spec)
        latest = db.scalar(
            select(BriefingTemplateVersion)
            .where(BriefingTemplateVersion.template_id == template.id)
            .order_by(BriefingTemplateVersion.version.desc())
            .limit(1)
        )
        if latest is None or latest.definition != definition:
            db.add(
                BriefingTemplateVersion(
                    organization_id=organization_id,
                    template_id=template.id,
                    version=(latest.version + 1) if latest else 1,
                    state="DRAFT",
                    definition=definition,
                    created_by=principal.profile.id,
                )
            )
            briefing_count += 1
        workflow.description = (
            f"Rascunho {BLUEPRINT_CODE}; versão técnica {workflow_version.version}. "
            "Tempo em horas corridas reais; SLA ainda não definido."
        )

    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=principal.profile.id,
            event_type="WORKFLOW_BLUEPRINT_DRAFTS_PREPARED",
            source="interface",
            metadata_json={
                "blueprint": BLUEPRINT_CODE,
                "workflowsCreated": workflow_count,
                "stagesCreated": stage_count,
                "checklistsCreated": checklist_count,
                "briefingVersionsCreated": briefing_count,
                "roleAssignmentsCreated": role_assignment_count,
            },
        )
    )
    db.commit()
    return {
        **preview,
        "workflowsCreated": workflow_count,
        "stagesCreated": stage_count,
        "checklistsCreated": checklist_count,
        "briefingVersionsCreated": briefing_count,
        "roleAssignmentsCreated": role_assignment_count,
        "appliedAt": utc_now(),
    }


def publish_blueprint(db: Session, principal: Principal) -> dict[str, Any]:
    """Publica e vincula o pacote do manual sem migrar cards existentes."""
    preview = blueprint_preview(db, principal)
    if not preview["safeToApply"]:
        raise ValueError(f"Categorias ausentes: {', '.join(preview['missingCategories'])}")
    organization_id = principal.membership.organization_id
    roles = {
        item.code: item
        for item in db.scalars(
            select(JobRole).where(
                JobRole.organization_id == organization_id,
                JobRole.active.is_(True),
            )
        )
    }
    role_assignment_count = ensure_initial_role_assignments(db, organization_id, roles)
    db.flush()
    assignments_by_role = {
        str(role_id)
        for role_id in db.scalars(
            select(MemberRoleAssignment.job_role_id).where(
                MemberRoleAssignment.organization_id == organization_id,
                MemberRoleAssignment.active.is_(True),
            )
        )
    }
    categories = {
        item.code: item
        for item in db.scalars(
            select(DemandCategory).where(
                DemandCategory.organization_id == organization_id,
                DemandCategory.active.is_(True),
            )
        )
    }
    published = bindings = briefing_versions = briefing_fields = 0
    missing_people: set[str] = set()
    now = utc_now()
    for category_code in BLUEPRINTS:
        workflow = db.scalar(
            select(Workflow).where(
                Workflow.organization_id == organization_id,
                Workflow.code == f"WF_{category_code}",
                Workflow.active.is_(True),
            )
        )
        if workflow is None:
            raise ValueError(f"Workflow ausente para {category_code}.")
        stages = list(
            db.scalars(
                select(WorkflowStage).where(
                    WorkflowStage.organization_id == organization_id,
                    WorkflowStage.workflow_id == workflow.id,
                    WorkflowStage.active.is_(True),
                )
            )
        )
        if not stages:
            raise ValueError(f"Workflow {workflow.name} não possui etapas ativas.")
        uncovered = [
            stage.name
            for stage in stages
            if not stage.default_assignee_id and not stage.owner_role_id and not stage.fallback_user_id
        ]
        if uncovered:
            raise ValueError(
                f"Workflow {workflow.name} possui etapas sem papel responsável: {', '.join(uncovered)}."
            )
        for stage in stages:
            if (
                stage.owner_role_id
                and str(stage.owner_role_id) not in assignments_by_role
                and not stage.default_assignee_id
                and not stage.fallback_user_id
            ):
                role = db.get(JobRole, stage.owner_role_id)
                if role and role.code not in {"TECHNICAL_SPECIALIST", "DEFINED_OWNER", "DEFINED_REVIEWER"}:
                    missing_people.add(role.name)

        workflow_version = ensure_workflow_version(
            db, organization_id, workflow.id, principal.profile.id
        )
        template = db.scalar(
            select(BriefingTemplate).where(
                BriefingTemplate.organization_id == organization_id,
                BriefingTemplate.category_id == categories[category_code].id,
            )
        )
        if template is None:
            raise ValueError(f"Briefing ausente para {category_code}.")
        briefing_version = db.scalar(
            select(BriefingTemplateVersion)
            .where(BriefingTemplateVersion.template_id == template.id)
            .order_by(BriefingTemplateVersion.version.desc())
            .limit(1)
        )
        if briefing_version is None:
            raise ValueError(f"Versão de briefing ausente para {category_code}.")

        workflow_changed = False
        if workflow.lifecycle_state != "PUBLISHED":
            workflow.lifecycle_state = "PUBLISHED"
            workflow.published_at = now
            published += 1
            workflow_changed = True
        published_description = (
            f"Manual {BLUEPRINT_CODE}; versão técnica {workflow_version.version}. "
            "Tempo em horas corridas reais; SLA ainda não definido."
        )
        if workflow.description != published_description:
            workflow.description = published_description
            workflow_changed = True
        if workflow_changed:
            workflow.revision += 1
            workflow.updated_at = now
        if briefing_version.state != "PUBLISHED":
            briefing_version.state = "PUBLISHED"
            briefing_version.published_at = now
            briefing_versions += 1

        category = categories[category_code]
        current_binding = db.scalar(
            select(CategoryTemplateBinding).where(
                CategoryTemplateBinding.organization_id == organization_id,
                CategoryTemplateBinding.category_id == category.id,
                CategoryTemplateBinding.effective_until.is_(None),
            )
        )
        binding_matches = bool(
            current_binding
            and current_binding.workflow_version_id == workflow_version.id
            and current_binding.briefing_template_version_id == briefing_version.id
        )
        if current_binding and not binding_matches:
            current_binding.effective_until = now
            current_binding.revision += 1
            db.flush()
        if not binding_matches:
            db.add(
                CategoryTemplateBinding(
                    organization_id=organization_id,
                    category_id=category.id,
                    workflow_version_id=workflow_version.id,
                    briefing_template_version_id=briefing_version.id,
                    effective_from=now,
                    activated_by=principal.profile.id,
                )
            )
            bindings += 1
        if category.default_workflow_id != workflow.id:
            category.default_workflow_id = workflow.id
            category.revision += 1
        briefing_fields += sync_operational_briefing_fields(
            db, organization_id, category, briefing_version.definition
        )

    db.add(
        AuditEvent(
            organization_id=organization_id,
            actor_user_id=principal.profile.id,
            event_type="WORKFLOW_BLUEPRINT_PUBLISHED",
            source="interface",
            metadata_json={
                "blueprint": BLUEPRINT_CODE,
                "workflowsPublished": published,
                "bindingsCreated": bindings,
                "briefingVersionsPublished": briefing_versions,
                "briefingFieldsSynchronized": briefing_fields,
                "roleAssignmentsCreated": role_assignment_count,
                "rolesWithoutPeople": sorted(missing_people),
                "existingCardsMigrated": 0,
            },
        )
    )
    db.commit()
    return {
        **preview,
        "workflowsPublished": published,
        "bindingsCreated": bindings,
        "briefingVersionsPublished": briefing_versions,
        "briefingFieldsSynchronized": briefing_fields,
        "roleAssignmentsCreated": role_assignment_count,
        "rolesWithoutPeople": sorted(missing_people),
        "existingCardsMigrated": 0,
        "publishedAt": now,
    }
