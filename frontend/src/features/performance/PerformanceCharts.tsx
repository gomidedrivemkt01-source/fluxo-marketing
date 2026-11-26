import { useEffect, useRef } from "react";
import type { PersonalPerformance } from "./performance";
import { minuteLabel } from "./performance";

export function PerformanceTimeline({ report, day, onOpen }: { report: PersonalPerformance; day: string; onOpen: (id: string) => void }) {
  const segments = report.segments.filter(item => item.date === day);
  const activity = report.cadence.filter(item => item.date === day);
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = scrollRef.current; if (!element) return;
    const align = () => {
      const track = element.querySelector<HTMLElement>(".performance-time-track");
      if (track && element.scrollWidth > element.clientWidth) {
        const earliest = Math.min(1440,...report.segments.filter(item => item.date===day).map(item => item.startMinute));
        element.scrollLeft = Math.max(0,earliest-60)/1440*track.getBoundingClientRect().width;
      } else element.scrollLeft = 0;
    };
    align(); const observer = new ResizeObserver(align); observer.observe(element); return () => observer.disconnect();
  },[day,report]);
  const ids = [...new Set(segments.map(item => item.id))];
  const clock = (value: string) => new Intl.DateTimeFormat("pt-BR", { timeZone: report.timezone, hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  const minute = (at: string) => { const pieces = new Intl.DateTimeFormat("en-GB", { timeZone: report.timezone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date(at)); return Number(pieces.find(p => p.type === "hour")?.value ?? 0)*60+Number(pieces.find(p => p.type === "minute")?.value ?? 0); };
  return <div className="performance-timeline"><div className="performance-timeline-scroll" ref={scrollRef}><div className="performance-timeline-inner">
    <div className="performance-clock-row"><span /><div>{[0,4,8,12,16,20,24].map(hour => <span key={hour} style={{ left: `${hour/24*100}%` }}>{String(hour).padStart(2,"0")}h</span>)}</div></div>
    <div className="performance-cadence-row"><strong>Entregas e retornos</strong><div>{activity.map((item,index) => <button key={`${item.id}-${index}`} className={`performance-event ${item.kind}`} style={{ left: `${minute(item.at)/1440*100}%` }} onClick={() => item.canOpen && onOpen(item.id)} aria-label={`${clock(item.at)} · ${item.kind === "advance" ? "Avanço" : "Retorno"} · ${item.title}`} title={`${clock(item.at)} · ${item.stageName} · ${item.title}`}>{item.kind === "advance" ? "↑" : "↩"}</button>)}</div></div>
    {ids.length ? ids.map(id => { const rows = segments.filter(item => item.id === id), card = rows[0]!; const lanes: number[] = []; const positions = rows.map(row => { let lane = lanes.findIndex(end => end <= row.startMinute); if (lane < 0) lane = lanes.length; lanes[lane] = row.endMinute; return lane; }); return <div className="performance-time-row" key={id}><button className="performance-row-label" disabled={!card.canOpen} onClick={() => onOpen(id)} title={card.title}>{card.title}</button><div className="performance-time-track" style={{ height: Math.max(36,lanes.length*22+10) }}>{rows.map((row,index) => <button key={`${row.entryId}-${index}`} className={`performance-time-segment ${row.kind}${row.running ? " running" : ""}`} style={{ left: `${row.startMinute/1440*100}%`, width: `${Math.max(.3,(row.endMinute-row.startMinute)/1440*100)}%`, top: positions[index]!*22+8 }} disabled={!row.canOpen} onClick={() => onOpen(row.id)} title={`${row.title} · ${clock(row.startedAt)}–${clock(row.endedAt)} · ${minuteLabel(row.minutes)} · ${row.kind === "timer" ? row.running ? "Timer ativo" : "Timer" : row.kind === "manual" ? "Apontamento manual" : "Apontamento ajustado"}`} aria-label={`${row.title}, ${clock(row.startedAt)} até ${clock(row.endedAt)}`} />)}</div></div>; }) : <p className="performance-empty">Não há intervalos com horários comprovados neste dia.</p>}
    </div></div><div className="performance-legend"><span><i className="timer" />Timer</span><span><i className="manual" />Manual ou ajustado</span><span>↑ Etapa avançada</span><span>↩ Retorno</span></div><p className="performance-chart-note">Deslize a linha do tempo para examinar os horários. Horários em {report.timezone}. Pausas ficam fora dos timers. Timers simultâneos podem somar tempos sobrepostos; cobertura conta cada minuto uma vez.</p></div>;
}

export function PerformanceDays({ report, selected, onSelect }: { report: PersonalPerformance; selected: string; onSelect: (date: string) => void }) {
  const max = Math.max(1,...report.days.map(item => item.stageAdvances));
  return <div className="performance-days">{report.days.map(day => <button key={day.date} className={day.date === selected ? "selected" : ""} onClick={() => onSelect(day.date)} aria-label={`Ver cadência de ${day.date}: ${day.stageAdvances} avanços de etapa`}><strong>{day.stageAdvances}</strong><span className="performance-day-bar"><i style={{ height: `${day.stageAdvances/max*100}%` }} /></span><time>{day.date.slice(8)}/{day.date.slice(5,7)}</time><small>{minuteLabel(day.recordedMinutes)}</small></button>)}</div>;
}
