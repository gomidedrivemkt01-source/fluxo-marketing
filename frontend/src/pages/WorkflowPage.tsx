import { ValidatedForm } from "../components/ValidatedForm";
import { type FormEvent, useEffect, useState } from "react";
import { api, messageFrom } from "../api";
import { RemovalDialog, ResponsibilityEditor } from "../features/management/ManagementDialogs";
import FunctionsManager from "../features/management/FunctionsManager";
import type {
  Category,
  Demand,
  JobRole,
  JobRoleAssignment,
  Person,
  Workflow,
  WorkflowBlueprintPreview,
  WorkflowStage,
} from "../WorkspaceApp";

function Field({
  label,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input {...props} />
    </label>
  );
}

function Notice({
  kind = "error",
  children,
}: {
  kind?: "error" | "success";
  children: React.ReactNode;
}) {
  return (
    <div
      className={`notice ${kind}`}
      role={kind === "error" ? "alert" : "status"}
    >
      {children}
    </div>
  );
}

function WorkflowStageModal({
  stage,
  workflowId,
  people,
  roles,
  roleAssignments,
  nextPosition,
  onClose,
  onSaved,
}: {
  stage?: WorkflowStage | null;
  workflowId: string;
  people: Person[];
  roles: JobRole[];
  roleAssignments: JobRoleAssignment[];
  nextPosition: number;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ownerRoleId, setOwnerRoleId] = useState(stage ? stage.ownerRoleId ?? "" : "__shared");
  const sharedPrimary = roleAssignments.find((item) => item.roleId === ownerRoleId && !item.isFallback);
  const sharedFallback = roleAssignments.find((item) => item.roleId === ownerRoleId && item.isFallback);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const duration = String(data.get("expectedDurationHours") || "");
    const payload: Record<string, unknown> = {
      name: data.get("name"),
      code: data.get("code"),
      color: data.get("color"),
      position: stage?.position ?? nextPosition,
      workflowId,
      defaultAssigneeId: data.get("defaultAssigneeId") || null,
      ownerRoleId: data.get("ownerRoleId") || null,
      fallbackUserId: data.get("fallbackUserId") || null,
      expectedDurationHours: duration ? Number(duration) : null,
      slaHours: stage?.slaHours ?? null,
      acceptanceRule: stage?.acceptanceRule ?? null,
      conditionRule: stage?.conditionRule ?? {},
    };
    if (stage) {
      payload.expectedRevision = stage.revision;
      payload.active = data.get("active") === "on";
    }
    if (ownerRoleId === "__shared") delete payload.ownerRoleId;
    try {
      await api(
        stage
          ? `/catalogs/workflow-stages/${stage.id}`
          : "/catalogs/workflow-stages",
        { method: stage ? "PUT" : "POST", body: JSON.stringify(payload) },
      );
      await onSaved();
      onClose();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop">
      <section
        className="form-modal compact-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="stage-modal-title"
      >
        <header className="modal-head">
          <div>
            <span className="eyebrow dark">Configuração do fluxo</span>
            <h2 id="stage-modal-title">
              {stage ? "Editar etapa" : "Nova etapa"}
            </h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Fechar">
            ×
          </button>
        </header>
        <ValidatedForm className="modal-form" onSubmit={submit}>
          {error && <Notice>{error}</Notice>}
          <p className="form-intro">
            Vincule a etapa a uma responsabilidade compartilhada ou defina pessoas específicas.
            Use “Responsáveis” na lista de etapas para redistribuir também os cards existentes.
          </p>
          <Field
            label="Nome da etapa"
            name="name"
            defaultValue={stage?.name}
            placeholder="Ex.: Aprovação jurídica"
            required
            maxLength={120}
          />
          <Field
            label="Código interno"
            name="code"
            defaultValue={stage?.code}
            placeholder="APROVACAO_JURIDICA"
            required
            maxLength={50}
          />
          <label className="field color-field">
            <span>Cor da etapa</span>
            <input
              name="color"
              type="color"
              defaultValue={stage?.color ?? "#475569"}
            />
          </label>
          <div className="form-grid">
            <label className="field">
              <span>Responsabilidade compartilhada</span>
              <select
                name="ownerRoleId"
                value={ownerRoleId}
                onChange={(event) => setOwnerRoleId(event.target.value)}
              >
                {!stage && <option value="__shared">Usar a função das etapas de mesmo nome</option>}
                <option value="">Definir pessoas nesta etapa</option>
                {roles.map((role) => (
                  <option key={role.id} value={role.id}>
                    {role.name}
                  </option>
                ))}
              </select>
              <small>
                Principal: {sharedPrimary?.profileName ?? "Não definido"} · Substituto: {sharedFallback?.profileName ?? "Não definido"}
              </small>
            </label>
            <label className="field">
              <span>Responsável principal específico</span>
              <select
                name="defaultAssigneeId"
                defaultValue={stage?.defaultAssigneeId ?? ""}
              >
                <option value="">{sharedPrimary ? `Herdar: ${sharedPrimary.profileName}` : "Não definido"}</option>
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
              <small>Quando preenchido, prevalece sobre a função.</small>
            </label>
          </div>
          <div className="form-grid">
            <label className="field">
              <span>Substituto da etapa</span>
              <select
                name="fallbackUserId"
                defaultValue={stage?.fallbackUserId ?? ""}
              >
                <option value="">{sharedFallback ? `Herdar: ${sharedFallback.profileName}` : "Não definido"}</option>
                {people.map((person) => (
                  <option key={person.id} value={person.id}>
                    {person.name}
                  </option>
                ))}
              </select>
            </label>
            <Field
              label="Previsão da etapa em horas corridas"
              name="expectedDurationHours"
              type="number"
              min={1}
              max={8760}
              defaultValue={stage?.expectedDurationHours ?? ""}
              placeholder="Ex.: 48"
            />
          </div>
          {stage && (
            <label className="check stage-active-check">
              <input
                name="active"
                type="checkbox"
                defaultChecked={stage.active}
              />
              <span>Etapa ativa e disponível para novas movimentações</span>
            </label>
          )}
          <footer className="form-actions">
            <button
              className="secondary compact"
              type="button"
              onClick={onClose}
            >
              Cancelar
            </button>
            <button className="primary action-primary" disabled={busy}>
              {busy ? "Salvando…" : "Salvar etapa"}
            </button>
          </footer>
        </ValidatedForm>
      </section>
    </div>
  );
}

function WorkflowModal({
  workflow,
  onClose,
  onSaved,
}: {
  workflow?: Workflow | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = {
      name: data.get("name"),
      code: data.get("code"),
      description: data.get("description") || null,
      isDefault: data.get("isDefault") === "on",
    };
    if (workflow) {
      payload.expectedRevision = workflow.revision;
      payload.active = data.get("active") === "on";
    }
    try {
      await api(
        workflow ? `/catalogs/workflows/${workflow.id}` : "/catalogs/workflows",
        { method: workflow ? "PUT" : "POST", body: JSON.stringify(payload) },
      );
      await onSaved();
      onClose();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop">
      <section
        className="form-modal compact-modal"
        role="dialog"
        aria-modal="true"
      >
        <header className="modal-head">
          <div>
            <span className="eyebrow dark">Modelo operacional</span>
            <h2>{workflow ? "Editar workflow" : "Novo workflow"}</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Fechar">
            ×
          </button>
        </header>
        <ValidatedForm className="modal-form" onSubmit={submit}>
          {error && <Notice>{error}</Notice>}
          <Field
            label="Nome"
            name="name"
            defaultValue={workflow?.name}
            placeholder="Ex.: Produção de vídeo"
            required
          />
          <Field
            label="Código"
            name="code"
            defaultValue={workflow?.code}
            placeholder="VIDEO"
            required
          />
          <label className="field">
            <span>Descrição</span>
            <textarea
              name="description"
              rows={3}
              defaultValue={workflow?.description ?? ""}
            />
          </label>
          <label className="check stage-active-check">
            <input
              name="isDefault"
              type="checkbox"
              defaultChecked={workflow?.isDefault}
              disabled={workflow?.lifecycleState === "DRAFT"}
            />
            <span>
              {workflow?.lifecycleState === "DRAFT"
                ? "Rascunhos não podem ser o padrão antes da publicação"
                : "Usar como workflow padrão da organização"}
            </span>
          </label>
          {workflow && (
            <label className="check stage-active-check">
              <input
                name="active"
                type="checkbox"
                defaultChecked={workflow.active}
              />
              <span>Workflow ativo</span>
            </label>
          )}
          <footer className="form-actions">
            <button
              className="secondary compact"
              type="button"
              onClick={onClose}
            >
              Cancelar
            </button>
            <button className="primary action-primary" disabled={busy}>
              {busy ? "Salvando…" : "Salvar workflow"}
            </button>
          </footer>
        </ValidatedForm>
      </section>
    </div>
  );
}

export default function WorkflowPage({
  workflows,
  stages,
  demands,
  categories,
  people,
  roles,
  roleAssignments,
  canPrepare,
  onReload,
}: {
  workflows: Workflow[];
  stages: WorkflowStage[];
  demands: Demand[];
  categories: Category[];
  people: Person[];
  roles: JobRole[];
  roleAssignments: JobRoleAssignment[];
  canPrepare: boolean;
  onReload: () => Promise<void>;
}) {
  const [selectedId, setSelectedId] = useState(
    workflows.find((item) => item.isDefault)?.id ?? workflows[0]?.id ?? "",
  );
  const [editingWorkflow, setEditingWorkflow] = useState<
    Workflow | "new" | null
  >(null);
  const [editing, setEditing] = useState<WorkflowStage | "new" | null>(null);
  const [removing, setRemoving] = useState<{ stageId?: string; name: string } | null>(null);
  const [responsibility, setResponsibility] = useState<{ stageId?: string; roleId?: string } | null>(null);
  const [view, setView] = useState<"workflows" | "functions">("workflows");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [blueprint, setBlueprint] = useState<WorkflowBlueprintPreview | null>(
    null,
  );
  const selected =
    workflows.find((workflow) => workflow.id === selectedId) ?? workflows[0];
  const selectedStages = stages.filter(
    (stage) => stage.workflowId === selected?.id,
  );
  const active = selectedStages
    .filter((stage) => stage.active)
    .sort((a, b) => a.position - b.position);
  const inactive = selectedStages
    .filter((stage) => !stage.active)
    .sort((a, b) => a.position - b.position);
  useEffect(() => {
    if (canPrepare)
      api<WorkflowBlueprintPreview>("/catalogs/workflow-blueprint")
        .then(setBlueprint)
        .catch((caught) => setError(messageFrom(caught)));
  }, [canPrepare, workflows.length]);
  async function prepareBlueprint() {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const result = await api<WorkflowBlueprintPreview>(
        "/catalogs/workflow-blueprint/prepare",
        { method: "POST" },
      );
      setBlueprint(result);
      setSuccess(
        `${result.workflowsCreated ?? 0} workflows e ${result.stagesCreated ?? 0} etapas preparados como rascunho.`,
      );
      await onReload();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }
  async function publishBlueprint() {
    if (
      !window.confirm(
        "Publicar os 13 workflows especializados e vinculá-los às categorias? Os cards existentes permanecerão nas versões atuais.",
      )
    )
      return;
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const result = await api<WorkflowBlueprintPreview>(
        "/catalogs/workflow-blueprint/publish",
        { method: "POST" },
      );
      const pendingRoles = result.rolesWithoutPeople?.length
        ? ` Funções ainda sem pessoa cadastrada: ${result.rolesWithoutPeople.join(", ")}.`
        : "";
      setSuccess(
        `${result.workflowsPublished ?? 0} workflows publicados e ${result.bindingsCreated ?? 0} categorias vinculadas. Nenhum card existente foi migrado.${pendingRoles}`,
      );
      await onReload();
      setBlueprint(
        await api<WorkflowBlueprintPreview>("/catalogs/workflow-blueprint"),
      );
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }
  async function deleteWorkflow() {
    if (selected && !selected.isDefault) setRemoving({ name: selected.name });
  }
  async function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= active.length) return;
    const ordered = [...active];
    const sourceStage = ordered[index];
    const targetStage = ordered[target];
    if (!sourceStage || !targetStage) return;
    ordered[index] = targetStage;
    ordered[target] = sourceStage;
    setBusy(true);
    setError("");
    try {
      await api("/catalogs/workflow-stages/order", {
        method: "PATCH",
        body: JSON.stringify({
          stages: ordered.map((stage) => ({
            id: stage.id,
            expectedRevision: stage.revision,
          })),
        }),
      });
      await onReload();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }
  const managementTabs = <nav className="management-tabs" aria-label="Gestão de workflows"><button className={view === "workflows" ? "active" : ""} onClick={() => setView("workflows")}>Workflows</button><button className={view === "functions" ? "active" : ""} onClick={() => setView("functions")}>Funções e etapas</button></nav>;
  if (view === "functions") return <>{managementTabs}<FunctionsManager onSaved={onReload} /></>;
  if (!selected)
    return (
      <section className="panel page-panel">
        <div className="empty-state">
          <span>↗</span>
          <h3>Nenhum workflow cadastrado</h3>
          <p>Crie o primeiro modelo de etapas da operação.</p>
          <button
            className="primary compact"
            onClick={() => setEditingWorkflow("new")}
          >
            + Criar workflow
          </button>
        </div>
        {editingWorkflow && (
          <WorkflowModal
            workflow={null}
            onClose={() => setEditingWorkflow(null)}
            onSaved={onReload}
          />
        )}
      </section>
    );
  const maxPosition =
    selectedStages.reduce(
      (value, stage) => Math.max(value, stage.position),
      0,
    ) + 1;
  return (
    <>
      {managementTabs}
      {canPrepare && blueprint && (
        <section className="panel blueprint-banner">
          <div>
            <span className="eyebrow dark">{blueprint.blueprint}</span>
            <strong>
              Manual especializado: {blueprint.categories} categorias ·{" "}
              {blueprint.stages} etapas
            </strong>
            <small>
              {Object.keys(blueprint.existingWorkflows).length} modelos
              preparados. Publicar libera a seleção por categoria sem migrar
              cards existentes.
            </small>
          </div>
          <div className="blueprint-actions">
            <button
              className="secondary compact"
              type="button"
              disabled={busy || !blueprint.safeToApply}
              onClick={() => void prepareBlueprint()}
            >
              {busy ? "Processando…" : "Sincronizar rascunhos"}
            </button>
            <button
              className="primary compact"
              type="button"
              disabled={busy || !blueprint.safeToApply}
              onClick={() => void publishBlueprint()}
            >
              Publicar e vincular categorias
            </button>
          </div>
        </section>
      )}
      {success && <Notice kind="success">{success}</Notice>}
      <div className="workflow-library">
        <aside className="panel workflow-selector">
          <header>
            <div>
              <span className="eyebrow dark">Biblioteca</span>
              <h3>Workflows</h3>
            </div>
            <button onClick={() => setEditingWorkflow("new")}>+</button>
          </header>
          <div>
            {workflows.map((workflow) => (
              <button
                className={workflow.id === selected.id ? "active" : ""}
                key={workflow.id}
                onClick={() => setSelectedId(workflow.id)}
              >
                <span>
                  <strong>{workflow.name}</strong>
                  <small>
                    {
                      categories.filter(
                        (category) =>
                          category.defaultWorkflowId === workflow.id,
                      ).length
                    }{" "}
                    categorias ·{" "}
                    {
                      demands.filter(
                        (demand) => demand.workflowId === workflow.id,
                      ).length
                    }{" "}
                    cards
                  </small>
                </span>
                {workflow.isDefault ? (
                  <b>Padrão</b>
                ) : workflow.lifecycleState === "DRAFT" ? (
                  <b>Rascunho</b>
                ) : null}
              </button>
            ))}
          </div>
        </aside>
        <section className="panel page-panel workflow-detail">
          <div className="panel-head">
            <div>
              <span className="eyebrow dark">
                {selected.code} ·{" "}
                {selected.lifecycleState === "DRAFT" ? "Rascunho" : "Publicado"}
              </span>
              <h3>{selected.name}</h3>
              <p>
                {selected.description ||
                  "Workflow personalizado sem descrição."}
              </p>
            </div>
            <div className="workflow-head-actions">
              <button
                className="secondary compact"
                onClick={() => setEditingWorkflow(selected)}
              >
                Editar modelo
              </button>
              {!selected.isDefault && (
                <button
                  className="secondary compact danger-text"
                  disabled={busy}
                  onClick={() => void deleteWorkflow()}
                >
                  Excluir
                </button>
              )}
              <button
                className="small-button"
                onClick={() => setEditing("new")}
              >
                + Nova etapa
              </button>
            </div>
          </div>
          <div className="workflow-admin-intro">
            <strong>
              {selected.lifecycleState === "DRAFT"
                ? "Modelo isolado para revisão"
                : "Fluxo compartilhado por tipo de trabalho"}
            </strong>
            <p>
              {selected.lifecycleState === "DRAFT"
                ? "Este rascunho aparece nas categorias para conferência, mas só pode ser selecionado depois da publicação."
                : categories.filter(
                      (category) => category.defaultWorkflowId === selected.id,
                    ).length
                  ? `Padrão de ${categories
                      .filter(
                        (category) =>
                          category.defaultWorkflowId === selected.id,
                      )
                      .map((category) => category.name)
                      .join(", ")}.`
                  : "Workflow livre, sem categoria vinculada. Pode ser escolhido em qualquer card."}
            </p>
          </div>
          {error && (
            <div className="workflow-editor-error">
              <Notice>{error}</Notice>
            </div>
          )}
          <div className="workflow-admin-list editable">
            {active.map((stage, index) => {
              const role = roles.find((item) => item.id === stage.ownerRoleId);
              const rolePeople = roleAssignments.filter(
                (item) => item.roleId === role?.id && item.active,
              );
              const responsible =
                people.find((person) => person.id === stage.defaultAssigneeId)
                  ?.name ??
                rolePeople.find((item) => !item.isFallback)?.profileName ??
                (role ? `${role.name} · pessoa pendente` : "Responsável atual");
              const substitute = people.find((person) => person.id === stage.fallbackUserId)?.name ?? rolePeople.find((item) => item.isFallback)?.profileName ?? "Não definido";
              return (
                <article key={stage.id}>
                  <span>{index + 1}</span>
                  <i style={{ background: stage.color }} />
                  <div>
                    <strong>{stage.name}</strong>
                    <small>
                      {role?.name ?? "Sem função definida"} · Principal: {responsible} ·{" "}
                      {stage.slaHours
                        ? `${stage.slaHours}h de SLA`
                        : "SLA a definir com dados reais"}
                    </small>
                    <small>Substituto: {substitute}{stage.defaultAssigneeId ? " · Principal específico nesta etapa" : role ? " · Herdado da função" : ""}</small>
                  </div>
                  <b>
                    {
                      demands.filter((demand) => demand.stageId === stage.id)
                        .length
                    }{" "}
                    cards
                  </b>
                  <div className="stage-row-actions">
                    <button onClick={() => setResponsibility({ stageId: stage.id })}>Responsáveis</button>
                    <button
                      disabled={busy || index === 0}
                      onClick={() => void move(index, -1)}
                    >
                      ↑
                    </button>
                    <button
                      disabled={busy || index === active.length - 1}
                      onClick={() => void move(index, 1)}
                    >
                      ↓
                    </button>
                    <details className="stage-actions-menu"><summary aria-label={`Mais ações de ${stage.name}`} title="Mais ações">⋯</summary><div>
                      {stage.ownerRoleId && <button onClick={() => setResponsibility({ roleId: stage.ownerRoleId! })}>Pessoas da função</button>}
                      <button onClick={() => setEditing(stage)}>Editar etapa</button>
                      <button className="danger-text" disabled={busy} onClick={() => setRemoving({ stageId: stage.id, name: stage.name })}>Excluir etapa</button>
                    </div></details>
                  </div>
                </article>
              );
            })}
          </div>
          {!active.length && (
            <div className="empty-state compact-empty">
              <span>↗</span>
              <h3>Adicione a primeira etapa</h3>
              <p>
                Um workflow pode ser criado antes de receber suas colunas
                operacionais.
              </p>
            </div>
          )}
          {inactive.length > 0 && (
            <div className="inactive-stages">
              <span className="eyebrow dark">Etapas inativas</span>
              {inactive.map((stage) => (
                <div className="inactive-stage-row" key={stage.id}><button onClick={() => setEditing(stage)}>
                  <i style={{ background: stage.color }} />
                  <span>
                    <strong>{stage.name}</strong>
                    <small>{stage.code}</small>
                  </span>
                  <b>Reativar ou editar</b>
                </button><button className="secondary compact danger-text" onClick={() => setRemoving({ stageId: stage.id, name: stage.name })}>Excluir etapa</button></div>
              ))}
            </div>
          )}
        </section>
      </div>
      {editingWorkflow && (
        <WorkflowModal
          workflow={editingWorkflow === "new" ? null : editingWorkflow}
          onClose={() => setEditingWorkflow(null)}
          onSaved={onReload}
        />
      )}
      {removing && <RemovalDialog workflowId={selected.id} stageId={removing.stageId} name={removing.name} onClose={() => setRemoving(null)} onSaved={onReload} />}
      {responsibility && <ResponsibilityEditor stageId={responsibility.stageId} roleId={responsibility.roleId} onClose={() => setResponsibility(null)} onSaved={onReload} />}
      {editing && (
        <WorkflowStageModal
          stage={editing === "new" ? null : editing}
          workflowId={selected.id}
          people={people}
          roles={roles}
          roleAssignments={roleAssignments}
          nextPosition={maxPosition}
          onClose={() => setEditing(null)}
          onSaved={onReload}
        />
      )}

    </>
  );
}
