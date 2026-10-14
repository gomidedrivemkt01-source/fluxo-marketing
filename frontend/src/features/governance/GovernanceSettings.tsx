import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, messageFrom } from "../../api";

type Preview = {
  filename: string;
  alreadyImported: boolean;
  board: { id: string; name: string };
  counts: { lists: number; cards: number; members: number; labels: number; checklists: number; new: number; changed: number; unchanged: number; sourceArchivedOrCompleted: number };
  listMappings: { sourceId: string; sourceName: string; cards: number; status: string; stageName: string }[];
  memberMappings: { sourceId: string; sourceName: string; profileId: string | null; profileName: string | null }[];
  warnings: string[];
};

type Batch = { id: string; filename: string; boardName: string; state: string; totalCards: number; createdCards: number; updatedCards: number; unchangedCards: number; archivedCards: number; createdAt: string; revertedAt: string | null };
type Overview = {
  events: { id: string; eventType: string; source: string; actorName: string; metadata: Record<string, unknown>; createdAt: string }[];
  archivedDemands: { id: string; publicId: string; title: string; status: string; archivedAt: string | null; deletedAt: string | null }[];
  revisions: { id: string; demandId: string; revision: number; operation: string; title: string; createdAt: string }[];
};
type Retention = { automaticEnabled: boolean; intervalDays: number; completedAfterDays: number; lastRunAt: string | null; eligibleCompleted: number; permanentDeletion: false };

const statusNames: Record<string, string> = {
  WAITING_EXECUTION: "Aguardando execução",
  IN_PROGRESS: "Em andamento",
  WAITING_APPROVAL: "Aguardando aprovação",
  SCHEDULED: "Agendada",
  BLOCKED: "Pausada",
  COMPLETED: "Concluída",
};

function dateTime(value: string | null): string {
  return value ? new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)) : "Ainda não executada";
}

export function GovernanceSettings({ onReload }: { onReload: () => Promise<void> }) {
  const [tab, setTab] = useState<"transfer" | "history" | "retention">("transfer");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [retention, setRetention] = useState<Retention | null>(null);
  const [updateExisting, setUpdateExisting] = useState(false);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState<{ kind: "error" | "success"; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextBatches, nextOverview, nextRetention] = await Promise.all([
        api<Batch[]>("/governance/trello/batches"),
        api<Overview>("/governance/overview"),
        api<Retention>("/governance/retention"),
      ]);
      setBatches(nextBatches);
      setOverview(nextOverview);
      setRetention(nextRetention);
    } catch (error) {
      setNotice({ kind: "error", text: messageFrom(error) });
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  async function validate(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy("validate"); setNotice(null); setPreview(null);
    const body = new FormData(); body.append("file", file);
    try {
      setPreview(await api<Preview>("/governance/trello/validate", { method: "POST", body }));
    } catch (error) {
      setNotice({ kind: "error", text: messageFrom(error) });
    } finally { setBusy(""); }
  }

  async function applyImport() {
    if (!file || !preview || preview.alreadyImported) return;
    const question = updateExisting
      ? "Aplicar a importação e atualizar também as demandas já vinculadas? Cada alteração poderá ser revertida pelo histórico do lote."
      : "Criar as novas demandas deste arquivo? Cartões já vinculados serão preservados.";
    if (!window.confirm(question)) return;
    setBusy("apply"); setNotice(null);
    const body = new FormData(); body.append("file", file); body.append("updateExisting", String(updateExisting));
    try {
      const result = await api<{ created: number; updated: number; unchanged: number; archived: number }>("/governance/trello/apply", { method: "POST", body });
      setNotice({ kind: "success", text: `Importação concluída: ${result.created} criadas, ${result.updated} atualizadas e ${result.unchanged} preservadas.` });
      setPreview(null); setFile(null); setUpdateExisting(false);
      await Promise.all([load(), onReload()]);
    } catch (error) { setNotice({ kind: "error", text: messageFrom(error) }); }
    finally { setBusy(""); }
  }

  async function revert(batch: Batch) {
    if (!window.confirm(`Reverter a importação “${batch.filename}”? Demandas criadas serão arquivadas e alterações serão restauradas.`)) return;
    setBusy(batch.id); setNotice(null);
    try {
      const result = await api<{ restored: number; archived: number }>(`/governance/trello/batches/${batch.id}/revert`, { method: "POST" });
      setNotice({ kind: "success", text: `Lote revertido: ${result.restored} demandas restauradas e ${result.archived} criações arquivadas.` });
      await Promise.all([load(), onReload()]);
    } catch (error) { setNotice({ kind: "error", text: messageFrom(error) }); }
    finally { setBusy(""); }
  }

  async function restore(path: string, message: string) {
    if (!window.confirm(message)) return;
    setBusy(path); setNotice(null);
    try {
      await api(path, { method: "POST" });
      setNotice({ kind: "success", text: "Restauração concluída e registrada no histórico." });
      await Promise.all([load(), onReload()]);
    } catch (error) { setNotice({ kind: "error", text: messageFrom(error) }); }
    finally { setBusy(""); }
  }

  async function saveRetention(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!retention) return;
    const data = new FormData(event.currentTarget); setBusy("retention-save"); setNotice(null);
    try {
      const saved = await api<Retention>("/governance/retention", { method: "PUT", body: JSON.stringify({ automaticEnabled: data.get("automaticEnabled") === "on", intervalDays: Number(data.get("intervalDays")), completedAfterDays: Number(data.get("completedAfterDays")) }) });
      setRetention(saved); setNotice({ kind: "success", text: "Política de retenção salva." });
    } catch (error) { setNotice({ kind: "error", text: messageFrom(error) }); }
    finally { setBusy(""); }
  }

  async function runRetention() {
    if (!retention || !window.confirm(`Arquivar agora ${retention.eligibleCompleted} demanda(s) concluída(s) elegível(is)? Nada será apagado permanentemente.`)) return;
    setBusy("retention-run"); setNotice(null);
    try {
      const result = await api<{ archived: number; policy: Retention }>("/governance/retention/run", { method: "POST" });
      setRetention(result.policy); setNotice({ kind: "success", text: `${result.archived} demanda(s) concluída(s) arquivada(s). Tempos e indicadores foram preservados.` });
      await Promise.all([load(), onReload()]);
    } catch (error) { setNotice({ kind: "error", text: messageFrom(error) }); }
    finally { setBusy(""); }
  }

  return <section className="panel page-panel governance-page">
    <div className="panel-head governance-head"><div><span className="eyebrow dark">Dados e segurança operacional</span><h3>Importação, histórico e retenção</h3><p className="panel-help">Controle administrativo para migrar dados, revisar alterações e arquivar demandas concluídas sem perder indicadores.</p></div><span className="admin-lock">Administrador</span></div>
    <nav className="governance-tabs" aria-label="Configurações de dados">
      <button className={tab === "transfer" ? "active" : ""} onClick={() => setTab("transfer")}>Importar e exportar</button>
      <button className={tab === "history" ? "active" : ""} onClick={() => setTab("history")}>Histórico e restauração</button>
      <button className={tab === "retention" ? "active" : ""} onClick={() => setTab("retention")}>Retenção e limpeza</button>
    </nav>
    {notice && <div className={`notice ${notice.kind}`}>{notice.text}</div>}

    {tab === "transfer" && <div className="governance-content">
      <article className="governance-card"><div className="governance-card-head"><div><span className="governance-step">01</span><h4>Validar export do Trello</h4><p>O arquivo é analisado antes de qualquer gravação. IDs estáveis evitam demandas duplicadas.</p></div><a className="secondary compact export-link" href="/api/v1/governance/trello/export">Exportar dados</a></div>
        <form className="trello-upload" onSubmit={validate}><label><span>Arquivo JSON do quadro</span><input type="file" accept="application/json,.json" onChange={(event) => { setFile(event.target.files?.[0] ?? null); setPreview(null); }} required /></label><button className="primary action-primary compact" disabled={!file || Boolean(busy)}>{busy === "validate" ? "Validando…" : "Validar arquivo"}</button></form>
      </article>
      {preview && <article className="governance-card preview-card"><div className="governance-card-head"><div><span className="governance-step">02</span><h4>{preview.board.name}</h4><p>{preview.filename}</p></div><span className={preview.alreadyImported ? "status-pill warning" : "status-pill ready"}>{preview.alreadyImported ? "Arquivo já importado" : "Pronto para revisão"}</span></div>
        <div className="governance-metrics"><span><strong>{preview.counts.cards}</strong> cartões</span><span><strong>{preview.counts.new}</strong> novos</span><span><strong>{preview.counts.changed}</strong> alterados</span><span><strong>{preview.counts.unchanged}</strong> sem mudança</span><span><strong>{preview.counts.checklists}</strong> checklists</span></div>
        {preview.warnings.map((warning) => <div className="inline-warning" key={warning}>{warning}</div>)}
        <div className="mapping-grid"><div><h5>Listas e destino</h5>{preview.listMappings.map((item) => <p key={item.sourceId}><strong>{item.sourceName}</strong><span>{item.cards} cards · {statusNames[item.status] ?? item.status} · {item.stageName}</span></p>)}</div><div><h5>Correspondência de usuários</h5>{preview.memberMappings.map((item) => <p key={item.sourceId}><strong>{item.sourceName}</strong><span>{item.profileName ?? "Sem correspondência — ficará sem responsável"}</span></p>)}</div></div>
        <label className="check governance-update-check"><input type="checkbox" checked={updateExisting} onChange={(event) => setUpdateExisting(event.target.checked)} /><span>Atualizar demandas já vinculadas quando o cartão do Trello tiver mudanças. A versão anterior ficará disponível para reversão.</span></label>
        <div className="governance-actions"><button className="primary action-primary compact" disabled={preview.alreadyImported || Boolean(busy)} onClick={() => void applyImport()}>{busy === "apply" ? "Importando…" : "Aplicar importação"}</button></div>
      </article>}
      <article className="governance-card"><div className="governance-card-head"><div><span className="governance-step">03</span><h4>Histórico de importações</h4><p>Cada lote pode ser revertido enquanto não houver outra importação posterior dos mesmos cartões.</p></div></div>
        <div className="table-wrap"><table><thead><tr><th>Arquivo</th><th>Resultado</th><th>Data</th><th>Situação</th><th>Ação</th></tr></thead><tbody>{batches.length ? batches.map((batch) => <tr key={batch.id}><td><strong>{batch.boardName}</strong><small className="table-subtitle">{batch.filename}</small></td><td>{batch.createdCards} criadas · {batch.updatedCards} atualizadas</td><td>{dateTime(batch.createdAt)}</td><td><span className={`import-state ${batch.state}`}>{batch.state === "reverted" ? "Revertida" : "Aplicada"}</span></td><td>{batch.state === "applied" ? <button className="table-action danger-text" disabled={busy === batch.id} onClick={() => void revert(batch)}>{busy === batch.id ? "Revertendo…" : "Reverter lote"}</button> : "—"}</td></tr>) : <tr><td colSpan={5}>Nenhuma importação do Trello realizada.</td></tr>}</tbody></table></div>
      </article>
    </div>}

    {tab === "history" && <div className="governance-content two-column-governance">
      <article className="governance-card"><div className="governance-card-head"><div><h4>Demandas arquivadas</h4><p>Itens saem das áreas operacionais, mas continuam no banco e nos indicadores.</p></div></div><div className="history-list">{overview?.archivedDemands.length ? overview.archivedDemands.map((item) => <div key={item.id}><span><strong>{item.title}</strong><small>{item.publicId} · {item.deletedAt ? "Excluída" : "Arquivada"}</small></span><button className="table-action" disabled={busy.includes(item.id)} onClick={() => void restore(`/governance/demands/${item.id}/restore`, `Restaurar “${item.title}” para as áreas operacionais?`)}>Restaurar</button></div>) : <p className="empty-copy">Nenhuma demanda arquivada.</p>}</div></article>
      <article className="governance-card"><div className="governance-card-head"><div><h4>Versões recuperáveis</h4><p>Cópias automáticas geradas antes de alterações em demandas.</p></div></div><div className="history-list">{overview?.revisions.length ? overview.revisions.slice(0, 30).map((item) => <div key={item.id}><span><strong>{item.title}</strong><small>Versão {item.revision} · {dateTime(item.createdAt)}</small></span><button className="table-action" disabled={busy.includes(item.id)} onClick={() => void restore(`/governance/revisions/${item.id}/restore`, `Restaurar a versão ${item.revision} de “${item.title}”? O estado atual também será guardado.`)}>Restaurar versão</button></div>) : <p className="empty-copy">Nenhuma versão anterior registrada.</p>}</div></article>
      <article className="governance-card governance-audit"><div className="governance-card-head"><div><h4>Atividade administrativa</h4><p>Registro geral das alterações relevantes da plataforma.</p></div></div><div className="table-wrap"><table><thead><tr><th>Evento</th><th>Responsável</th><th>Origem</th><th>Data</th></tr></thead><tbody>{overview?.events.map((event) => <tr key={event.id}><td>{event.eventType}</td><td>{event.actorName}</td><td>{event.source}</td><td>{dateTime(event.createdAt)}</td></tr>)}</tbody></table></div></article>
    </div>}

    {tab === "retention" && retention && <div className="governance-content retention-grid">
      <article className="governance-card"><div className="governance-card-head"><div><h4>Política automática</h4><p>O serviço verifica periodicamente somente demandas concluídas e antigas.</p></div></div><form className="retention-form" onSubmit={saveRetention}><label className="check"><input name="automaticEnabled" type="checkbox" defaultChecked={retention.automaticEnabled} /><span>Ativar arquivamento automático</span></label><label><span>Executar a cada</span><div><input name="intervalDays" type="number" min={30} max={365} defaultValue={retention.intervalDays} /><b>dias</b></div></label><label><span>Arquivar concluídas sem alteração há</span><div><input name="completedAfterDays" type="number" min={30} max={3650} defaultValue={retention.completedAfterDays} /><b>dias</b></div></label><button className="primary action-primary compact" disabled={busy === "retention-save"}>{busy === "retention-save" ? "Salvando…" : "Salvar política"}</button></form></article>
      <article className="governance-card retention-summary"><span className="retention-count">{retention.eligibleCompleted}</span><h4>demandas concluídas elegíveis</h4><p>Última execução: {dateTime(retention.lastRunAt)}</p><div className="safe-cleanup"><strong>Arquivamento seguro</strong><span>Não há exclusão permanente. Tempos, relatórios, comentários e histórico permanecem preservados.</span></div><button className="secondary compact" disabled={!retention.eligibleCompleted || busy === "retention-run"} onClick={() => void runRetention()}>{busy === "retention-run" ? "Arquivando…" : "Arquivar agora"}</button></article>
    </div>}
  </section>;
}
