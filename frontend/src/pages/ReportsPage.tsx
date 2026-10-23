import { useEffect, useState } from "react";
import { api, messageFrom } from "../api";
import type { OperationalReport, Person, ReportBreakdown, ReportCapacity, ReportStagePerformance, ReportTrendPoint } from "../WorkspaceApp";

function Notice({ children }: { children: React.ReactNode }) {
  return <div className="notice error" role="alert">{children}</div>;
}

function calendarDateKey(value: Date | string): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function dateLabel(value: string | null): string {
  if (!value) return "Sem prazo";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
}

function reportDuration(minutes: number): string {
  if (minutes < 60) return `${minutes}min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours}h ${rest}min` : `${hours}h`;
}

type ReportPeriodMode = "30" | "90" | "180" | "365" | "custom";

function defaultCustomReportRange(): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end); start.setDate(start.getDate() - 29);
  return { start: calendarDateKey(start), end: calendarDateKey(end) };
}

function reportInputDateLabel(value: string): string {
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

function ReportBreakdownList({ title, eyebrow, items, showTime = false }: { title: string; eyebrow: string; items: ReportBreakdown[]; showTime?: boolean }) {
  const visible = items.slice(0, 7);
  const largest = Math.max(1, ...visible.map((item) => item.count));
  return <section className="panel report-breakdown"><header><div><span className="eyebrow dark">{eyebrow}</span><h3>{title}</h3></div><span>{items.reduce((total, item) => total + item.count, 0)} cards</span></header>{visible.length ? <div className="report-bars">{visible.map((item) => <article key={item.id}><div className="report-bar-copy"><span><i style={{ background: item.color ?? "var(--teal-dark)" }} /><strong>{item.label}</strong></span><span><b>{item.count}</b>{showTime && <small>{reportDuration(item.totalMinutes)}</small>}{item.overdue > 0 && <em>{item.overdue} atrasada{item.overdue === 1 ? "" : "s"}</em>}</span></div><div className="report-bar-track"><i style={{ width: `${Math.max(4, Math.round((item.count / largest) * 100))}%`, background: item.color ?? "var(--teal-dark)" }} /></div></article>)}</div> : <div className="report-empty">Ainda não há dados para esta distribuição.</div>}</section>;
}

function reportTrendLabel(value: string, granularity: OperationalReport["trendGranularity"]): string {
  const date = new Date(`${value}T00:00:00`);
  if (granularity === "month") return new Intl.DateTimeFormat("pt-BR", { month: "short" }).format(date).replace(".", "");
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" }).format(date);
}

function ReportTrend({ points, granularity }: { points: ReportTrendPoint[]; granularity: OperationalReport["trendGranularity"] }) {
  const largest = Math.max(1, ...points.flatMap((point) => [point.created, point.completed]));
  const intervalName = granularity === "month" ? "mês" : granularity === "week" ? "semana" : "dia";
  return <section className="panel report-trend"><header><div><span className="eyebrow dark">Histórico operacional</span><h3>Entradas e conclusões por {intervalName}</h3><p>O tempo exibido em cada coluna corresponde aos apontamentos do mesmo intervalo.</p></div><div className="report-legend"><span><i className="created" />Criadas</span><span><i className="completed" />Concluídas</span></div></header>{points.length ? <div className={`report-trend-scroll ${granularity}`}><div className="report-trend-chart">{points.map((point) => <article key={point.date} title={`${point.created} criadas · ${point.completed} concluídas · ${reportDuration(point.trackedMinutes)} apontadas`}><div className="report-trend-time">{point.trackedMinutes > 0 ? reportDuration(point.trackedMinutes) : "—"}</div><div className="report-trend-bars"><i className="created" style={{ height: point.created ? `${Math.max(8, Math.round((point.created / largest) * 100))}%` : "0" }}><span>{point.created || ""}</span></i><i className="completed" style={{ height: point.completed ? `${Math.max(8, Math.round((point.completed / largest) * 100))}%` : "0" }}><span>{point.completed || ""}</span></i></div><time dateTime={point.date}>{reportTrendLabel(point.date, granularity)}</time></article>)}</div></div> : <div className="report-empty">Ainda não há histórico para o período selecionado.</div>}</section>;
}

function ReportCapacityPanel({ items, periodLabel }: { items: ReportCapacity[]; periodLabel: string }) {
  const largest = Math.max(1, ...items.flatMap((item) => [item.expectedMinutes, item.trackedMinutes]));
  return <section className="panel report-capacity"><header><div><span className="eyebrow dark">Distribuição de capacidade</span><h3>Carteira prevista e tempo realizado</h3><p>Estimativa dos cards atualmente abertos comparada ao tempo apontado em {periodLabel.toLocaleLowerCase("pt-BR")}.</p></div></header>{items.length ? <div className="report-capacity-list">{items.map((item) => <article key={item.profileId}><div className="report-capacity-name"><strong>{item.profileName}</strong><small>{item.activeDemands} {item.activeDemands === 1 ? "demanda aberta" : "demandas abertas"}</small></div><div className="report-capacity-metric"><span><b>Previsto em aberto</b><strong>{reportDuration(item.expectedMinutes)}</strong></span><i><b style={{ width: `${Math.max(item.expectedMinutes ? 4 : 0, Math.round((item.expectedMinutes / largest) * 100))}%` }} /></i></div><div className="report-capacity-metric tracked"><span><b>Apontado no período</b><strong>{reportDuration(item.trackedMinutes)}</strong></span><i><b style={{ width: `${Math.max(item.trackedMinutes ? 4 : 0, Math.round((item.trackedMinutes / largest) * 100))}%` }} /></i></div></article>)}</div> : <div className="report-empty">Ainda não há estimativas ou apontamentos para distribuir.</div>}</section>;
}

function ReportStagePerformancePanel({ items }: { items: ReportStagePerformance[] }) {
  return <section className="panel report-stage-performance"><header><div><span className="eyebrow dark">SLA real por etapa</span><h3>Tempo observado no fluxo</h3><p>Horas corridas, sem ocultar noites ou fins de semana. O SLA usa o ciclo integral de cada passagem.</p></div></header>{items.length ? <div className="report-stage-table"><div className="report-stage-table-head"><span>Etapa</span><span>Passagens</span><span>Média observada</span><span>SLA configurado</span><span>Aderência</span><span>Retornos</span></div>{items.map((item) => <article key={item.stageId}><span className="report-stage-name"><i style={{ background: item.color }} /><span><strong>{item.stageName}</strong><small>{item.totalHours.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}h observadas</small></span></span><strong>{item.visits}</strong><span>{item.averageHours.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}h</span><span>{item.slaHours ? `${item.slaHours}h` : "Não definido"}</span><span>{item.slaRate === null ? <em className="neutral">Sem SLA</em> : <em className={item.slaRate >= 80 ? "good" : item.slaRate >= 60 ? "warning" : "danger"}>{item.slaRate}% <small>({item.withinSla}/{item.withinSla + item.breachedSla})</small></em>}</span><span>{item.returns}</span></article>)}</div> : <div className="report-empty">As passagens pelas etapas aparecerão aqui conforme o workflow for utilizado.</div>}</section>;
}

export default function ReportsPage({ onOpen, canViewTeam, people }: { onOpen: (demandId: string) => void; canViewTeam: boolean; people: Person[] }) {
  const [periodMode, setPeriodMode] = useState<ReportPeriodMode>("30");
  const [draftRange, setDraftRange] = useState(defaultCustomReportRange);
  const [appliedRange, setAppliedRange] = useState(defaultCustomReportRange);
  const [selectedPersonId, setSelectedPersonId] = useState("team");
  const [attempt, setAttempt] = useState(0);
  const [report, setReport] = useState<OperationalReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setLoading(true); setError("");
    const query = new URLSearchParams();
    if (periodMode === "custom") { query.set("startDate", appliedRange.start); query.set("endDate", appliedRange.end); }
    else query.set("days", periodMode);
    if (canViewTeam && selectedPersonId !== "team") query.set("assigneeId", selectedPersonId);
    api<OperationalReport>(`/reports/operational?${query.toString()}`).then((value) => { if (active) setReport(value); }).catch((caught) => { if (active) setError(messageFrom(caught)); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [periodMode, appliedRange.start, appliedRange.end, selectedPersonId, canViewTeam, attempt]);
  if (loading && !report) return <section className="panel feature-loading"><span className="loader" /><p>Consolidando a operação…</p></section>;
  if (error && !report) return <section className="panel report-error"><Notice>{error}</Notice><button className="secondary compact" onClick={() => setAttempt((value) => value + 1)}>Tentar novamente</button></section>;
  if (!report) return null;
  const summary = report.summary;
  const completionRate = summary.totalDemands ? Math.round((summary.completedDemands / summary.totalDemands) * 100) : 0;
  const periodLabel = periodMode === "custom" ? `${reportInputDateLabel(appliedRange.start)} a ${reportInputDateLabel(appliedRange.end)}` : `${report.periodDays} dias`;
  const teamReport = report.scope === "team";
  const reportTitle = teamReport ? "Visão executiva da equipe" : canViewTeam ? `Relatório de ${report.scopeProfileName ?? "colaborador"}` : "Meu relatório operacional";
  const reportDescription = teamReport ? "Carteira atual, prazos e gargalos de toda a equipe. O período controla novas entradas e horas apontadas." : canViewTeam ? "Demandas atualmente atribuídas e horas apontadas pela pessoa selecionada." : "Somente suas demandas e seus apontamentos aparecem nesta visão. Coordenadores e administradores também podem acompanhar este relatório.";
  return <div className="reports-workspace">
    <section className={`report-hero${periodMode === "custom" ? " custom" : ""}`}><div className="report-hero-copy"><span className="eyebrow">{teamReport ? "Saúde da operação" : "Desempenho individual"}</span><h2>{reportTitle}</h2><p>{reportDescription}</p></div><div className={`report-controls${periodMode === "custom" ? " custom" : ""}`}>{canViewTeam ? <label className="report-scope-picker"><span>Visualização</span><select value={selectedPersonId} onChange={(event) => setSelectedPersonId(event.target.value)} disabled={loading}><option value="team">Toda a equipe</option>{people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select><small>{selectedPersonId === "team" ? "Overview consolidado da operação." : "Visão individual e privativa."}</small></label> : <div className="report-private-scope"><span>Relatório privativo</span><strong>Somente meus dados</strong><small>Seus colegas não acessam este relatório.</small></div>}<div className={`report-period-picker${periodMode === "custom" ? " custom" : ""}`}><label className="report-period-mode"><span>Período analisado</span><select value={periodMode} onChange={(event) => setPeriodMode(event.target.value as ReportPeriodMode)} disabled={loading}><option value="30">Últimos 30 dias</option><option value="90">Últimos 90 dias</option><option value="180">Últimos 180 dias</option><option value="365">Últimos 12 meses</option><option value="custom">Período personalizado</option></select></label>{periodMode === "custom" && <div className="report-custom-range"><label><span>Data inicial</span><input type="date" value={draftRange.start} max={draftRange.end} onChange={(event) => setDraftRange((current) => ({ start: event.target.value, end: event.target.value > current.end ? event.target.value : current.end }))} /></label><label><span>Data final</span><input type="date" value={draftRange.end} min={draftRange.start} onChange={(event) => setDraftRange((current) => ({ start: event.target.value < current.start ? event.target.value : current.start, end: event.target.value }))} /></label><button type="button" onClick={() => { setAppliedRange(draftRange); setAttempt((value) => value + 1); }} disabled={loading || !draftRange.start || !draftRange.end}>{loading ? "Atualizando…" : "Aplicar"}</button></div>}<small>{periodMode === "custom" ? `Aplicado: ${periodLabel}` : "Use um intervalo pronto ou defina datas específicas."}</small></div></div></section>
    {error && <Notice>{error}</Notice>}
    <section className="report-kpis">
      <article><span>Carteira atual</span><strong>{summary.totalDemands}</strong><small>{summary.createdInPeriod} criada{summary.createdInPeriod === 1 ? "" : "s"} no período</small><i className="teal" /></article>
      <article className={summary.overdue ? "warning" : ""}><span>Prazos vencidos</span><strong>{summary.overdue}</strong><small>{summary.dueSoon} vence{summary.dueSoon === 1 ? "" : "m"} em até 7 dias</small><i className="danger" /></article>
      <article><span>Concluídas na carteira</span><strong>{summary.completedDemands}</strong><small>{completionRate}% do total atual</small><i className="success" /></article>
      <article><span>Tempo apontado</span><strong>{reportDuration(summary.trackedMinutes)}</strong><small>{periodMode === "custom" ? "no período selecionado" : `nos últimos ${report.periodDays} dias`}</small><i className="violet" /></article>
      <article className={summary.blocked || summary.unassigned ? "warning" : ""}><span>Pontos de atenção</span><strong>{summary.blocked + summary.unassigned}</strong><small>{summary.blocked} bloqueada{summary.blocked === 1 ? "" : "s"} · {summary.unassigned} sem responsável</small><i className="orange" /></article>
    </section>
    <section className="report-signal-row"><div><span className="report-signal danger">{summary.overdue}</span><p><strong>Demandas atrasadas</strong><small>Precisam de replanejamento ou conclusão.</small></p></div><div><span className="report-signal orange">{summary.urgent}</span><p><strong>Prioridade urgente</strong><small>Cards abertos marcados como urgentes.</small></p></div><div><span className="report-signal teal">{reportDuration(summary.expectedMinutes)}</span><p><strong>Esforço previsto aberto</strong><small>Soma das estimativas ainda em carteira.</small></p></div></section>
    <ReportTrend points={report.trend} granularity={report.trendGranularity} />
    <ReportCapacityPanel items={report.capacity} periodLabel={periodLabel} />
    <ReportStagePerformancePanel items={report.stagePerformance} />
    <div className="report-grid"><ReportBreakdownList eyebrow="Fluxo" title="Onde estão as demandas" items={report.byStage} /><ReportBreakdownList eyebrow={`Capacidade · ${periodLabel}`} title={teamReport ? "Carga por responsável" : "Carteira e tempo individual"} items={report.byAssignee} showTime /><ReportBreakdownList eyebrow="Carteira" title="Distribuição por empresa" items={report.byCompany} /><ReportBreakdownList eyebrow="Tipos de entrega" title="Distribuição por categoria" items={report.byCategory} /></div>
    <section className="panel report-status"><header><div><span className="eyebrow dark">Situação atual</span><h3>Distribuição por status</h3></div><small>Atualizado {new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(report.generatedAt))}</small></header><div>{report.byStatus.map((item) => <article key={item.id}><span><i style={{ background: item.color ?? "var(--teal-dark)" }} />{item.label}</span><strong>{item.count}</strong><small>{item.overdue ? `${item.overdue} atrasada${item.overdue === 1 ? "" : "s"}` : "Dentro do fluxo"}</small></article>)}</div></section>
    <section className="panel report-attention"><header><div><span className="eyebrow dark">{teamReport ? "Prioridade de gestão" : "Prioridades da carteira"}</span><h3>Demandas que pedem atenção</h3><p>Ordenadas primeiro por atraso e bloqueio.</p></div><span className="count">{report.attention.length}</span></header>{report.attention.length ? <div className="report-attention-list">{report.attention.map((item) => <button key={item.id} onClick={() => onOpen(item.id)}><span className="report-attention-title"><strong>{item.title}</strong><small>{item.publicId} · {item.companyName ?? "Sem empresa"}</small></span><span>{item.assigneeName ?? "Sem responsável"}</span><span>{item.stageName ?? "Sem etapa"}</span><span className="attention-reasons">{item.reasons.map((reason) => <em key={reason}>{reason}</em>)}</span><time>{item.deadlineAt ? dateLabel(item.deadlineAt) : "Sem prazo"}</time><b>›</b></button>)}</div> : <div className="report-empty report-empty-good"><span>✓</span><strong>Nenhuma demanda crítica agora</strong><p>Não há cards atrasados, bloqueados, urgentes ou sem responsável.</p></div>}</section>
  </div>;
}

