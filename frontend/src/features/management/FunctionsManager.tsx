import { useEffect, useState, type FormEvent } from "react";
import { api, messageFrom } from "../../api";
import type { JobRole, JobRoleAssignment } from "../../WorkspaceApp";
import { ResponsibilityEditor } from "./ManagementDialogs";

type StageGroup = {
  key: string;
  name: string;
  roleId: string | null;
  mixed: boolean;
  stages: {
    id: string;
    workflowId: string;
    workflowName: string;
    roleId: string | null;
    revision: number;
  }[];
};
type Impact = {
  stages: number;
  currentDemands: number;
  futureStages: number;
  runningTimers: number;
  revision?: number;
};
type Operation =
  | { kind: "bind"; group: StageGroup; roleId: string | null }
  | { kind: "remove"; role: JobRole };

function RoleForm({
  role,
  onClose,
  onSaved,
}: {
  role: JobRole | null;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const generated = name
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, "_")
      .replace(/^_|_$/g, "")
      .slice(0, 60);
    try {
      await api(
        role ? `/catalogs/job-roles/${role.id}` : "/catalogs/job-roles",
        {
          method: role ? "PUT" : "POST",
          body: JSON.stringify({
            name: name.trim(),
            description: description.trim() || null,
            code:
              role?.code ??
              (generated.length >= 2 ? generated : `FUNCAO_${Date.now()}`),
            ...(role ? { expectedRevision: role.revision } : {}),
          }),
        },
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
        className="form-modal management-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="function-form-title"
      >
        <header className="modal-head">
          <h2 id="function-form-title">
            {role ? "Editar função" : "Nova função"}
          </h2>
          <button
            className="icon-button"
            aria-label="Fechar"
            disabled={busy}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <form onSubmit={(event) => void submit(event)}>
          <div className="management-body">
            {error && (
              <div className="notice error" role="alert">
                {error}
              </div>
            )}
            <label className="field">
              <span>Nome da função</span>
              <input
                required
                minLength={2}
                maxLength={120}
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Ex.: Planejamento de Demandas ou Copywriter"
              />
            </label>
            <label className="field">
              <span>Descrição</span>
              <textarea
                maxLength={1000}
                rows={3}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="O que essa função entrega"
              />
            </label>
          </div>
          <footer className="form-actions">
            <button
              type="button"
              className="secondary compact"
              disabled={busy}
              onClick={onClose}
            >
              Cancelar
            </button>
            <button className="primary compact" disabled={busy}>
              {busy ? "Salvando…" : "Salvar função"}
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}

function FunctionImpactDialog({
  operation,
  roles,
  onClose,
  onSaved,
}: {
  operation: Operation;
  roles: JobRole[];
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [current, setCurrent] = useState(true);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const binding = operation.kind === "bind";
  const payload = binding
    ? {
        roleId: operation.roleId,
        stages: operation.group.stages.map((s) => ({
          id: s.id,
          revision: s.revision,
        })),
        applyToCurrent: current,
      }
    : null;
  const base = binding
    ? `/management/stage-functions/${encodeURIComponent(operation.group.key)}`
    : `/management/job-roles/${operation.role.id}`;
  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    setImpact(null);
    const promise = binding
      ? api<Impact>(`${base}/preview`, {
          method: "POST",
          body: JSON.stringify(payload),
        })
      : api<Impact>(`${base}/removal-preview`);
    promise
      .then((value) => {
        if (active) setImpact(value);
      })
      .catch((caught) => {
        if (active) setError(messageFrom(caught));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [operation, current]);
  async function save() {
    if (!impact) return;
    setBusy(true);
    setError("");
    try {
      await api(
        binding ? base : `${base}?expectedRevision=${impact.revision}`,
        {
          method: binding ? "PUT" : "DELETE",
          ...(binding ? { body: JSON.stringify(payload) } : {}),
        },
      );
      await onSaved();
      onClose();
    } catch (caught) {
      setError(messageFrom(caught));
      setImpact(null);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop">
      <section
        className="form-modal management-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="function-impact-title"
      >
        <header className="modal-head">
          <div>
            <h2 id="function-impact-title">
              {binding
                ? `Vincular ${operation.group.name}`
                : `Excluir ${operation.role.name}`}
            </h2>
            <p>
              {binding
                ? `Função: ${roles.find((r) => r.id === operation.roleId)?.name ?? "Padrão da etapa"}`
                : "Revise o impacto antes de excluir a função."}
            </p>
          </div>
          <button
            className="icon-button"
            aria-label="Fechar"
            disabled={busy}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="management-body">
          {error && (
            <div className="notice error" role="alert">
              {error}
            </div>
          )}
          {binding ? (
            <>
              <p>
                A mesma definição será aplicada em todos os workflows listados.
                Uma função vinculada passa a definir o principal e o substituto
                dessas etapas.
              </p>
              <div className="function-workflow-tags">
                {operation.group.stages.map((stage) => (
                  <span key={stage.id}>{stage.workflowName}</span>
                ))}
              </div>
              <label className="check">
                <input
                  type="checkbox"
                  checked={current}
                  onChange={(event) => setCurrent(event.target.checked)}
                  disabled={busy}
                />
                <span>
                  Atualizar também os responsáveis herdados nas etapas atuais
                </span>
              </label>
            </>
          ) : (
            <p>
              As etapas perderão o vínculo com esta função e usarão as pessoas
              definidas diretamente na própria etapa. Se não houver um padrão,
              ficarão sem responsável. O histórico da função será preservado.
            </p>
          )}
          <p>
            Exceções de responsáveis definidas em cada card, prazos e etapas
            concluídas permanecem preservados. As etapas futuras dos cards
            existentes acompanham a nova definição.
          </p>
          {loading ? (
            <p>Conferindo vínculos…</p>
          ) : (
            impact && (
              <>
                <div className="management-metrics">
                  <span>
                    <strong>{impact.stages}</strong> etapas nos modelos
                  </span>
                  <span>
                    <strong>{impact.currentDemands}</strong> demandas atuais
                  </span>
                  <span>
                    <strong>{impact.futureStages}</strong> etapas futuras
                  </span>
                </div>
                {impact.runningTimers > 0 && (
                  <div className="notice error">
                    Pause os {impact.runningTimers} timers afetados antes de
                    confirmar.
                  </div>
                )}
              </>
            )
          )}
        </div>
        <footer className="form-actions">
          <button
            className="secondary compact"
            onClick={onClose}
            disabled={busy}
          >
            Cancelar
          </button>
          <button
            className={`primary compact${binding ? "" : " danger-action"}`}
            disabled={busy || loading || !impact || impact.runningTimers > 0}
            onClick={() => void save()}
          >
            {busy
              ? "Aplicando…"
              : binding
                ? "Confirmar vínculo"
                : "Excluir função"}
          </button>
        </footer>
      </section>
    </div>
  );
}

export default function FunctionsManager({
  onSaved,
}: {
  onSaved: () => Promise<void>;
}) {
  const [data, setData] = useState<{
    roles: JobRole[];
    groups: StageGroup[];
    assignments: JobRoleAssignment[];
  } | null>(null);
  const [error, setError] = useState("");
  const [editing, setEditing] = useState<JobRole | "new" | null>(null);
  const [personRole, setPersonRole] = useState<string | null>(null);
  const [operation, setOperation] = useState<Operation | null>(null);
  async function load() {
    const [roles, groups, assignments] = await Promise.all([
      api<JobRole[]>("/catalogs/job-roles"),
      api<StageGroup[]>("/management/stage-functions"),
      api<JobRoleAssignment[]>("/catalogs/job-role-assignments"),
    ]);
    setData({ roles, groups, assignments });
  }
  useEffect(() => {
    let active = true;
    Promise.all([
      api<JobRole[]>("/catalogs/job-roles"),
      api<StageGroup[]>("/management/stage-functions"),
      api<JobRoleAssignment[]>("/catalogs/job-role-assignments"),
    ])
      .then(([roles, groups, assignments]) => {
        if (active) setData({ roles, groups, assignments });
      })
      .catch((caught) => {
        if (active) setError(messageFrom(caught));
      });
    return () => {
      active = false;
    };
  }, []);
  async function saved() {
    await load();
    await onSaved();
  }
  return (
    <div className="functions-manager">
      <section className="panel">
        <header className="panel-head">
          <div>
            <h3>Funções</h3>
            <p>
              Defina as pessoas de cada função e reutilize essa responsabilidade
              em vários workflows.
            </p>
          </div>
          <button className="primary compact" onClick={() => setEditing("new")}>
            + Nova função
          </button>
        </header>
        {error && (
          <div className="notice error" role="alert">
            {error}
          </div>
        )}
        {!data ? (
          <p className="management-body">Carregando funções…</p>
        ) : data.roles.length ? (
          <div className="function-catalog">
            {data.roles.map((role) => {
              const assignments = data.assignments.filter(
                (a) => a.roleId === role.id,
              );
              const linked = data.groups
                .flatMap((g) => g.stages)
                .filter((s) => s.roleId === role.id);
              return (
                <article key={role.id}>
                  <div>
                    <h4>{role.name}</h4>
                    {role.description && <p>{role.description}</p>}
                    <small>
                      {linked.length} etapas ·{" "}
                      {new Set(linked.map((s) => s.workflowId)).size} workflows
                    </small>
                  </div>
                  <div className="function-people">
                    <span>
                      Principal
                      <strong>
                        {assignments.find((a) => !a.isFallback)?.profileName ??
                          "Não definido"}
                      </strong>
                    </span>
                    <span>
                      Substituto
                      <strong>
                        {assignments.find((a) => a.isFallback)?.profileName ??
                          "Não definido"}
                      </strong>
                    </span>
                  </div>
                  <div className="function-actions">
                    <button
                      className="secondary compact"
                      onClick={() => setPersonRole(role.id)}
                    >
                      Responsáveis
                    </button>
                    <button
                      className="table-action"
                      onClick={() => setEditing(role)}
                    >
                      Editar
                    </button>
                    <button
                      className="table-action danger-text"
                      onClick={() => setOperation({ kind: "remove", role })}
                    >
                      Excluir
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        ) : (
          <p className="management-body">
            Cadastre a primeira função para começar a vincular etapas.
          </p>
        )}
      </section>
      <section className="panel">
        <header className="panel-head">
          <div>
            <h3>Etapas por função</h3>
            <p>
              Etapas com o mesmo nome são agrupadas. Escolha uma função para
              aplicar o vínculo em todos os workflows do grupo.
            </p>
          </div>
        </header>
        <div className="function-bindings">
          {data?.groups.map((group) => (
            <article key={group.key}>
              <div>
                <strong>{group.name}</strong>
                <small>
                  {group.stages.length} etapas ·{" "}
                  {new Set(group.stages.map((s) => s.workflowId)).size}{" "}
                  workflows
                </small>
                <details>
                  <summary>Ver workflows</summary>
                  <div className="function-workflow-tags">
                    {group.stages.map((stage) => (
                      <span key={stage.id}>{stage.workflowName}</span>
                    ))}
                  </div>
                </details>
              </div>
              <div className="function-binding-control">
                <label className="field">
                  <span>Função responsável</span>
                  <select
                    aria-label={`Função de ${group.name}`}
                    value={group.mixed ? "__mixed" : (group.roleId ?? "")}
                    onChange={(event) =>
                      setOperation({
                        kind: "bind",
                        group,
                        roleId: event.target.value || null,
                      })
                    }
                  >
                    {group.mixed && (
                      <option value="__mixed" disabled>
                        Vínculos diferentes entre workflows
                      </option>
                    )}
                    <option value="">Padrão da etapa</option>
                    {data.roles.map((role) => (
                      <option key={role.id} value={role.id}>
                        {role.name}
                      </option>
                    ))}
                  </select>
                </label>
                {!group.mixed && group.roleId && (
                  <button
                    className="table-action"
                    onClick={() =>
                      setOperation({
                        kind: "bind",
                        group,
                        roleId: group.roleId,
                      })
                    }
                  >
                    Aplicar pessoas desta função ao grupo
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      </section>
      {editing && (
        <RoleForm
          role={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={saved}
        />
      )}
      {personRole && (
        <ResponsibilityEditor
          roleId={personRole}
          onClose={() => setPersonRole(null)}
          onSaved={saved}
        />
      )}
      {operation && data && (
        <FunctionImpactDialog
          operation={operation}
          roles={data.roles}
          onClose={() => setOperation(null)}
          onSaved={saved}
        />
      )}
    </div>
  );
}
