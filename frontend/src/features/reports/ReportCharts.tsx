import { useId } from "react";
import type { AnalyticsReport } from "./analytics";
import { duration, hoursLabel } from "./analytics";

export function DeliveryTrend({ report }: { report: AnalyticsReport }) {
  const titleId = useId();
  const width = 760, height = 240, pad = 32, plot = height - 2 * pad;
  const max = Math.max(1, ...report.trend.flatMap(item => [item.cardsCompleted, item.confirmedContributions]));
  const ticks = [...new Set([0, Math.ceil(max / 2), max])];
  const step = (width - 2 * pad) / Math.max(1, report.trend.length);
  const bar = Math.min(12, step * .29), stride = Math.max(1, Math.ceil(report.trend.length / 7));
  return <section className="analytics-panel analytics-trend"><header><div><h2>Entregas ao longo do tempo</h2><p>Cards encerrados e participações confirmadas por {report.granularity === "day" ? "dia" : report.granularity === "week" ? "semana" : "mês"}</p></div><span className="analytics-cohort">No período</span></header><div className="analytics-chart-legend"><span><i className="chart-cards" />Cards concluídos</span><span><i className="chart-contributions" />Entregas individuais</span></div><div className="analytics-svg-wrap"><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby={titleId}><title id={titleId}>Evolução de cards concluídos e entregas individuais confirmadas</title>{ticks.map(tick => <g key={tick}><line x1={pad} y1={height - pad - tick / max * plot} x2={width - pad} y2={height - pad - tick / max * plot} stroke="var(--line)" strokeDasharray="3 4" /><text x={pad - 8} y={height - pad - tick / max * plot + 4} textAnchor="end">{tick}</text></g>)}{report.trend.map((item, index) => {
    const x = pad + step * (index + .5), cardsHeight = item.cardsCompleted / max * plot, creditsHeight = item.confirmedContributions / max * plot;
    return <g key={item.date}><title>{`${item.date}: ${item.cardsCompleted} cards concluídos, ${item.confirmedContributions} entregas individuais confirmadas, ${item.stageAdvances} avanços de etapa`}</title><rect x={x - bar - 2} y={height - pad - cardsHeight} width={bar} height={cardsHeight} rx="2" fill="var(--teal-dark)" /><rect x={x + 2} y={height - pad - creditsHeight} width={bar} height={creditsHeight} rx="2" fill="var(--teal)" />{index % stride === 0 && <text x={x} y={height - 10} textAnchor="middle">{new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "2-digit" }).format(new Date(`${item.date}T12:00:00`))}</text>}</g>;
  })}</svg></div><footer>Uma pessoa conta uma entrega por card. Um card pode ter contribuições de várias pessoas.</footer></section>;
}

export function DeadlineRisk({ report }: { report: AnalyticsReport }) {
  const labels: Record<string, string> = { overdue: "Prazo vencido", dueSoon: `Menos de ${report.warningDays} dias`, later: "Prazo mais distante", undated: "Sem prazo definido" };
  const max = Math.max(1, ...report.deadlineRisk.map(item => item.count));
  return <section className="analytics-panel analytics-risk"><header><div><h2>Pressão de prazos</h2><p>Carteira atualmente atribuída</p></div><span className="analytics-cohort">Agora</span></header><div className="risk-bars">{report.deadlineRisk.map(item => <div key={item.id} className={`risk-bar risk-${item.id}`}><span>{labels[item.id]}</span><strong>{item.count}</strong><div><i style={{ width: `${item.count / max * 100}%` }} /></div></div>)}</div><footer>{report.summary.activeCards} cards ativos · {report.quality.unassignedActive} sem responsável</footer></section>;
}

export function StageBottlenecks({ stages }: { stages: AnalyticsReport["stages"] }) {
  const rows = stages.slice(0, 7), max = Math.max(1, ...rows.map(item => item.p90Hours ?? 0));
  return <section className="analytics-panel analytics-bottlenecks"><header><div><h2>Onde o fluxo leva mais tempo</h2><p>Permanência em horas corridas nas etapas com saídas registradas</p></div></header><div className="analytics-chart-legend"><span><i className="chart-cards" />Mediana</span><span><i className="chart-range" />P90</span></div>{rows.length ? <div className="bottleneck-list">{rows.map(item => <article key={item.id}><div className="bottleneck-copy"><strong title={`${item.name} · ${item.workflowName}`}>{item.name}<small>{item.workflowName}</small></strong><span>{hoursLabel(item.medianHours)}<small>P90 {hoursLabel(item.p90Hours)}</small></span></div><div className="bottleneck-track"><i className="range" style={{ width: `${(item.p90Hours ?? 0) / max * 100}%` }} /><i className="median" style={{ width: `${(item.medianHours ?? 0) / max * 100}%` }} /></div><small className="bottleneck-detail">{item.completedVisits} saídas · {item.returns} retornos · {item.slaRate === null ? "SLA sem base histórica" : `${item.slaRate}% dentro do SLA (${item.measuredSla} medições)`}</small></article>)}</div> : <div className="analytics-empty">As saídas reais de etapas aparecerão aqui. Passagens inferidas não medem desempenho.</div>}<footer>P90: 90% das permanências ficaram até esse tempo. Tempo corrido não equivale a horas trabalhadas.</footer></section>;
}

export function TimeAllocation({ report }: { report: AnalyticsReport }) {
  const rows = report.timeAllocation.slice(0, 6);
  if (report.timeAllocation.length > 6) rows.push({ id: "others", label: "Outras categorias", color: null, minutes: report.timeAllocation.slice(6).reduce((sum, item) => sum + item.minutes, 0) });
  const colors = ["var(--teal-dark)", "var(--teal)", "var(--orange)", "#8C79BD", "#7192B5", "#849B91", "var(--subtle)"];
  const total = rows.reduce((sum, item) => sum + item.minutes, 0);
  let offset = 0;
  return <section className="analytics-panel analytics-time"><header><div><h2>Como o tempo foi distribuído</h2><p>Apontamentos encerrados, por categoria</p></div></header>{total ? <div className="time-allocation"><div className="time-donut"><svg viewBox="0 0 140 140" role="img" aria-label={`${duration(total)} registrados por categoria`}><circle cx="70" cy="70" r="55" fill="none" stroke="var(--line)" strokeWidth="12" />{rows.map((item, index) => { const share = item.minutes / total * 100, start = offset; offset += share; return <circle key={item.id} cx="70" cy="70" r="55" pathLength="100" fill="none" stroke={item.color ?? colors[index]} strokeWidth="12" strokeDasharray={`${share} ${100 - share}`} strokeDashoffset={-start} transform="rotate(-90 70 70)"><title>{item.label}: {duration(item.minutes)}</title></circle>; })}</svg><span><strong>{duration(total)}</strong><small>tempo registrado</small></span></div><div className="time-allocation-legend">{rows.map((item, index) => <div key={item.id}><i style={{ background: item.color ?? colors[index] }} /><span title={item.label}>{item.label}</span><strong>{duration(item.minutes)}</strong><small>{Math.round(item.minutes / total * 100)}%</small></div>)}</div></div> : <div className="analytics-empty">Nenhum apontamento encerrado no período. Os timers abertos ficam fora deste total.</div>}<footer>O período considera a data de encerramento do apontamento. Timers simultâneos podem registrar intervalos sobrepostos.</footer></section>;
}
