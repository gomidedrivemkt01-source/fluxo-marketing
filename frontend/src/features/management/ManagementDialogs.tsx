import { useEffect, useState } from "react";
import { api, messageFrom } from "../../api";
import type { JobRole, JobRoleAssignment, Person, Workflow, WorkflowStage } from "../../WorkspaceApp";

export type TeamUser = { id: string; profileId: string; name: string; email: string; state: string; role: string | null; revision: number; avatarUrl: string | null };
type RoleChange = { roleId: string; primaryProfileId: string | null; fallbackProfileId: string | null; expectedRevision: number };
type StageChange = { stageId: string; ownerRoleId: string | null; primaryProfileId: string | null; fallbackProfileId: string | null; expectedRevision: number };
type Preview = { roles: number; stages: number; currentDemands: number; futureStages: number; runningTimers: number; demands: { id: string; publicId: string; title: string }[] };
type RemovalPreview = { targetWorkflowName: string; revision: number; currentDemands: number; migratedDemands: number; categories: number; runningTimers: number; targets: { id: string; name: string }[] };

export function ResponsibilityEditor({ person, roleId, stageId, onClose, onSaved }: { person?: TeamUser; roleId?: string; stageId?: string; onClose: () => void; onSaved: () => Promise<void> }) {
  const [data, setData] = useState<{ roles: JobRole[]; assignments: JobRoleAssignment[]; people: Person[]; stages: WorkflowStage[]; workflows: Workflow[] } | null>(null);
  const [roles, setRoles] = useState<Record<string, RoleChange>>({});
  const [stages, setStages] = useState<Record<string, StageChange>>({});
  const [current, setCurrent] = useState(true);
  const [future, setFuture] = useState(true);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([api<JobRole[]>("/catalogs/job-roles"), api<JobRoleAssignment[]>("/catalogs/job-role-assignments"), api<Person[]>("/users/options"), api<WorkflowStage[]>("/catalogs/workflow-stages?allWorkflows=true&includeDraft=true"), api<Workflow[]>("/catalogs/workflows?includeDraft=true")])
      .then(([roles, assignments, people, stages, workflows]) => { if (active) setData({ roles, assignments, people, stages, workflows }); })
      .catch((caught) => { if (active) setError(messageFrom(caught)); });
    return () => { active = false; };
  }, []);
  function roleValue(role: JobRole): RoleChange {
    return roles[role.id] ?? { roleId: role.id, primaryProfileId: data?.assignments.find((a) => a.roleId === role.id && !a.isFallback)?.profileId ?? null, fallbackProfileId: data?.assignments.find((a) => a.roleId === role.id && a.isFallback)?.profileId ?? null, expectedRevision: role.revision };
  }
  function roleMode(role: JobRole) {
    const value = roleValue(role);
    return value.primaryProfileId === person?.profileId ? "primary" : value.fallbackProfileId === person?.profileId ? "fallback" : "";
  }
  function setPersonRole(role: JobRole, mode: string) {
    if (!person) return;
    const value = { ...roleValue(role) };
    if (value.primaryProfileId === person.profileId) value.primaryProfileId = null;
    if (value.fallbackProfileId === person.profileId) value.fallbackProfileId = null;
    if (mode === "primary") value.primaryProfileId = person.profileId;
    if (mode === "fallback") value.fallbackProfileId = person.profileId;
    setRoles((prev) => ({ ...prev, [role.id]: value })); setPreview(null);
  }
  function setPersonStage(stage: WorkflowStage, mode: string) {
    if (!person) return;
    const value = { ...(stages[stage.id] ?? { stageId: stage.id, ownerRoleId: stage.ownerRoleId, primaryProfileId: stage.defaultAssigneeId, fallbackProfileId: stage.fallbackUserId, expectedRevision: stage.revision }) };
    if (value.primaryProfileId === person.profileId) value.primaryProfileId = null;
    if (value.fallbackProfileId === person.profileId) value.fallbackProfileId = null;
    if (mode === "primary") value.primaryProfileId = person.profileId;
    if (mode === "fallback") value.fallbackProfileId = person.profileId;
    setStages((prev) => ({ ...prev, [stage.id]: value })); setPreview(null);
  }
  const payload = { roles: Object.values(roles), stages: Object.values(stages), applyToCurrent: current, applyToFuture: future };
  async function review() {
    setBusy(true); setError("");
    try { setPreview(await api<Preview>("/management/responsibilities/preview", { method: "POST", body: JSON.stringify(payload) })); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function save() {
    setBusy(true); setError("");
    try { await api("/management/responsibilities", { method: "POST", body: JSON.stringify(payload) }); await onSaved(); onClose(); }
    catch (caught) { setPreview(null); setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  const filteredRoles = data?.roles.filter((r) => !stageId && (!roleId || r.id === roleId) && r.name.toLocaleLowerCase().includes(query.toLocaleLowerCase())) ?? [];
  const selectedStage = data?.stages.find((s) => s.id === stageId);
  const stageValue = selectedStage ? stages[selectedStage.id] ?? { stageId: selectedStage.id, ownerRoleId: selectedStage.ownerRoleId, primaryProfileId: selectedStage.defaultAssigneeId, fallbackProfileId: selectedStage.fallbackUserId, expectedRevision: selectedStage.revision } : null;
  return <div className="modal-backdrop"><section className="form-modal management-modal" role="dialog" aria-modal="true" aria-labelledby="responsibility-title"><header className="modal-head"><div><h2 id="responsibility-title">{person ? person.name : "Pessoas da função"}</h2><p>Responsabilidade compartilhada entre Equipe e Workflows.</p></div><button className="icon-button" aria-label="Fechar" onClick={onClose} disabled={busy}>×</button></header><div className="management-body">{error && <div className="notice error" role="alert">{error}</div>}{!data ? <p>Carregando atribuições…</p> : preview ? <><h3>Revisar alteração em massa</h3><div className="management-metrics"><span><strong>{preview.roles}</strong> funções</span><span><strong>{preview.stages}</strong> etapas nos modelos</span><span><strong>{preview.currentDemands}</strong> demandas atuais</span><span><strong>{preview.futureStages}</strong> etapas futuras</span></div><p>Os responsáveis definidos especificamente no card, os prazos e as etapas concluídas serão preservados.</p>{preview.runningTimers > 0 && <div className="notice error">Pause {preview.runningTimers} timer(s) das demandas afetadas antes de confirmar.</div>}<div className="management-preview-list">{preview.demands.map((d) => <p key={d.id}><small>{d.publicId}</small> {d.title}</p>)}</div></> : <><label className="field"><span>Buscar função ou etapa</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ex.: Design" /></label><div className="management-role-list">{filteredRoles.map((role) => {
    const value = roleValue(role);
    const linked = data.stages.filter((s) => s.ownerRoleId === role.id);
    return <article key={role.id}><div><strong>{role.name}</strong><small>{linked.length} etapas vinculadas · {new Set(linked.map((s) => s.workflowId)).size} workflows</small>{person && <small>Principal: {data.people.find((p) => p.id === value.primaryProfileId)?.name ?? "Não definido"} · Substituto: {data.people.find((p) => p.id === value.fallbackProfileId)?.name ?? "Não definido"}</small>}</div>{person ? <label className="field"><span>Atribuição de {person.name}</span><select value={roleMode(role)} onChange={(event) => setPersonRole(role, event.target.value)} disabled={person.state !== "active"}><option value="">Sem atribuição</option><option value="primary">Principal</option><option value="fallback">Substituto</option></select></label> : <div className="form-grid">{(["primaryProfileId", "fallbackProfileId"] as const).map((key) => <label className="field" key={key}><span>{key === "primaryProfileId" ? "Principal" : "Substituto"}</span><select value={value[key] ?? ""} onChange={(event) => { setRoles((prev) => ({ ...prev, [role.id]: { ...value, [key]: event.target.value || null } })); setPreview(null); }}><option value="">Não definido</option>{data.people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>)}</div>}</article>;
  })}</div>{selectedStage && stageValue && <div className="management-role-list"><h3>{selectedStage.name}</h3><label className="field"><span>Vincular à responsabilidade compartilhada</span><select value={stageValue.ownerRoleId ?? ""} onChange={(event) => { setStages({ [selectedStage.id]: { ...stageValue, ownerRoleId: event.target.value || null, primaryProfileId: null, fallbackProfileId: null } }); setPreview(null); }}><option value="">Definir pessoas apenas nesta etapa</option>{data.roles.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</select></label>{(["primaryProfileId", "fallbackProfileId"] as const).map((key) => { const inherited = data.assignments.find((a) => a.roleId === stageValue.ownerRoleId && a.isFallback === (key === "fallbackProfileId")); return <label className="field" key={key}><span>{key === "primaryProfileId" ? "Responsável principal" : "Substituto"}</span><select value={stageValue[key] ?? ""} onChange={(event) => { setStages({ [selectedStage.id]: { ...stageValue, [key]: event.target.value || null } }); setPreview(null); }}><option value="">{inherited ? `Herdar da função: ${inherited.profileName}` : "Não definido"}</option>{data.people.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></label>; })}<p>Uma pessoa específica nesta etapa prevalece sobre a responsabilidade compartilhada.</p></div>}{person && <details className="management-stage-exceptions"><summary>Responsabilidades específicas por etapa</summary><p>Uma atribuição específica prevalece sobre a função compartilhada.</p>{data.stages.filter((s) => `${s.name} ${data.workflows.find((w) => w.id === s.workflowId)?.name}`.toLocaleLowerCase().includes(query.toLocaleLowerCase())).map((stage) => {
    const value = stages[stage.id]; const primary = value ? value.primaryProfileId : stage.defaultAssigneeId; const fallback = value ? value.fallbackProfileId : stage.fallbackUserId;
    return <label className="management-exception-row" key={stage.id}><span><strong>{stage.name}</strong><small>{data.workflows.find((w) => w.id === stage.workflowId)?.name}</small></span><select aria-label={`Atribuição em ${stage.name}`} value={primary === person.profileId ? "primary" : fallback === person.profileId ? "fallback" : ""} onChange={(event) => setPersonStage(stage, event.target.value)} disabled={person.state !== "active"}><option value="">Sem atribuição direta</option><option value="primary">Principal da etapa</option><option value="fallback">Substituto da etapa</option></select></label>;
  })}</details>}<div className="management-apply-options"><label className="check"><input type="checkbox" checked={current} onChange={(event) => setCurrent(event.target.checked)} /><span>Atualizar responsáveis herdados nas demandas em andamento</span></label><label className="check"><input type="checkbox" checked={future} onChange={(event) => setFuture(event.target.checked)} /><span>Atualizar também as etapas futuras dos cards existentes</span></label><p>Novos cards seguem as novas definições automaticamente.</p></div></>}</div><footer className="form-actions">{preview ? <><button className="secondary compact" disabled={busy} onClick={() => setPreview(null)}>Voltar</button><button className="primary compact" disabled={busy || preview.runningTimers > 0} onClick={() => void save()}>{busy ? "Aplicando…" : "Confirmar atualização"}</button></> : <><button className="secondary compact" disabled={busy} onClick={onClose}>Cancelar</button><button className="primary compact" disabled={busy || !data || (!payload.roles.length && !payload.stages.length)} onClick={() => void review()}>{busy ? "Verificando…" : "Revisar alterações"}</button></>}</footer></section></div>;
}

export function RemovalDialog({ workflowId, stageId, name, onClose, onSaved }: { workflowId: string; stageId?: string; name: string; onClose: () => void; onSaved: () => Promise<void> }) {
  const [preview, setPreview] = useState<RemovalPreview | null>(null);
  const [target, setTarget] = useState(""); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  useEffect(() => { let active = true; api<RemovalPreview>(stageId ? `/management/stages/${stageId}/removal-preview` : `/management/workflows/${workflowId}/removal-preview`).then((value) => { if (active) { setPreview(value); setTarget(value.targets[0]?.id ?? ""); } }).catch((caught) => { if (active) setError(messageFrom(caught)); }); return () => { active = false; }; }, [workflowId, stageId]);
  async function remove() { if (!preview) return; setBusy(true); setError(""); try { await api(stageId ? `/management/stages/${stageId}?expectedRevision=${preview.revision}&targetStageId=${target}` : `/catalogs/workflows/${workflowId}?expectedRevision=${preview.revision}`, { method: "DELETE" }); await onSaved(); onClose(); } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); } }
  return <div className="modal-backdrop"><section className="form-modal compact-modal" role="dialog" aria-modal="true" aria-labelledby="remove-model-title"><header className="modal-head"><h2 id="remove-model-title">Excluir {stageId ? "etapa" : "workflow"}</h2><button className="icon-button" aria-label="Fechar" disabled={busy} onClick={onClose}>×</button></header><div className="management-body"><strong>{name}</strong>{error && <div className="notice error" role="alert">{error}</div>}{preview ? <><p>{stageId ? `${preview.currentDemands} demanda(s) estão nesta etapa. O plano de ${preview.migratedDemands} card(s) será atualizado para retirar a etapa.` : `${preview.migratedDemands} card(s) e ${preview.categories} categoria(s) serão transferidos para ${preview.targetWorkflowName}. Etapas com o mesmo código serão correspondidas; as demais irão à primeira etapa.`}</p>{stageId && <label className="field"><span>Enviar os cards desta etapa para</span><select value={target} onChange={(event) => setTarget(event.target.value)}>{preview.targets.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></label>}<p>Comentários, anexos, prazos, tempos e versões anteriores permanecerão no histórico.</p>{preview.runningTimers > 0 && <div className="notice error">Pause {preview.runningTimers} timer(s) do fluxo antes de executar esta alteração.</div>}</> : !error && <p>Verificando vínculos…</p>}</div><footer className="form-actions"><button className="secondary compact" disabled={busy} onClick={onClose}>Cancelar</button><button className="secondary compact danger-text" disabled={busy || !preview || preview.runningTimers > 0 || (!!stageId && !target)} onClick={() => void remove()}>{busy ? "Transferindo…" : "Transferir e excluir"}</button></footer></section></div>;
}

export function PersonRemovalDialog({ person, onClose, onSaved }: { person: TeamUser; onClose: () => void; onSaved: () => Promise<void> }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function remove() { setBusy(true); setError(""); try { await api(`/management/people/${person.id}?expectedRevision=${person.revision}`, { method: "DELETE" }); await onSaved(); onClose(); } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); } }
  return <div className="modal-backdrop"><section className="form-modal compact-modal" role="dialog" aria-modal="true" aria-labelledby="remove-person-title"><header className="modal-head"><h2 id="remove-person-title">Excluir cadastro de {person.name}</h2><button className="icon-button" aria-label="Fechar" disabled={busy} onClick={onClose}>×</button></header><div className="management-body">{error && <div className="notice error" role="alert">{error}</div>}<p>A conta de acesso será excluída e a pessoa sairá da Equipe e de Acessos. O nome permanecerá nos comentários, apontamentos e ações anteriores.</p><p>Timers desta pessoa serão encerrados com o tempo já realizado. Responsabilidades abertas passarão ao substituto ou ficarão sem responsável quando não houver substituto ativo.</p></div><footer className="form-actions"><button className="secondary compact" disabled={busy} onClick={onClose}>Cancelar</button><button className="secondary compact danger-text" disabled={busy} onClick={() => void remove()}>{busy ? "Excluindo…" : "Excluir cadastro e preservar histórico"}</button></footer></section></div>;
}

export function RemovedAccessList({ users, ownProfileId, onReload }: { users: TeamUser[]; ownProfileId?: string; onReload: () => Promise<void> }) {
  const [selected, setSelected] = useState<TeamUser | null>(null);
  const suspended = users.filter((user) => user.state === "suspended" && user.profileId !== ownProfileId);
  if (!suspended.length) return null;
  return <section className="panel page-panel"><div className="panel-head"><div><h3>Cadastros com acesso removido</h3><p>Exclua o cadastro operacional preservando a autoria no histórico.</p></div></div><div className="management-role-list management-body">{suspended.map((user) => <article key={user.id}><strong>{user.name}</strong><button className="secondary compact danger-text" onClick={() => setSelected(user)}>Excluir cadastro</button></article>)}</div>{selected && <PersonRemovalDialog person={selected} onClose={() => setSelected(null)} onSaved={onReload} />}</section>;
}
