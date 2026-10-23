import { type CSSProperties, useEffect, useMemo, useState } from "react";
import calendarIcon from "../assets/navigation/calendar.svg";
import listViewIcon from "../assets/views/list.svg";
import type { Company, Demand, Person } from "../WorkspaceApp";

const statusNames: Record<string, string> = {
  WAITING_EXECUTION: "Aguardando execução",
  IN_PROGRESS: "Em andamento",
  WAITING_INFORMATION: "Aguardando informação",
  WAITING_APPROVAL: "Aguardando aprovação",
  BLOCKED: "Bloqueada",
  SCHEDULED: "Agendada",
  COMPLETED: "Concluída",
};
const priorityNames: Record<string, string> = { LOW: "Baixa", NORMAL: "Normal", HIGH: "Alta", URGENT: "Urgente" };

function ThemeIcon({ src, className }: { src: string; className: string }) {
  return <span className={className} style={{ "--icon-source": `url("${src}")` } as CSSProperties} aria-hidden="true" />;
}

function AvatarView({ name, url }: { name: string; url?: string | null }) {
  return <span className="avatar avatar-normal">{url ? <img src={url} alt="" loading="lazy" decoding="async" /> : name.charAt(0).toUpperCase()}</span>;
}

type CalendarMode = "month" | "agenda";

function calendarDateKey(value: Date | string): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

export default function CalendarPage({ demands, companies, people, onOpen }: { demands: Demand[]; companies: Company[]; people: Person[]; onOpen: (demand: Demand) => void }) {
  const [mode, setMode] = useState<CalendarMode>(() => window.localStorage.getItem("fluxo.calendar-mode") === "agenda" ? "agenda" : "month");
  const [cursor, setCursor] = useState(() => { const value = new Date(); return new Date(value.getFullYear(), value.getMonth(), 1); });
  const [query, setQuery] = useState("");
  const [company, setCompany] = useState("ALL");
  const [assignee, setAssignee] = useState("ALL");
  const [status, setStatus] = useState("ALL");
  const [priority, setPriority] = useState("ALL");
  const filtered = useMemo(() => demands.filter((demand) => {
    const needle = query.trim().toLocaleLowerCase("pt-BR");
    const matchesCompany = company === "ALL" || (company === "UNASSIGNED" ? !demand.primaryCompanyId : demand.primaryCompanyId === company);
    const matchesAssignee = assignee === "ALL" || (assignee === "UNASSIGNED" ? !demand.assigneeId : demand.assigneeId === assignee);
    const matchesText = !needle || `${demand.publicId} ${demand.title} ${demand.companyName ?? ""} ${demand.assigneeName ?? ""} ${demand.categoryName ?? ""}`.toLocaleLowerCase("pt-BR").includes(needle);
    return matchesCompany && matchesAssignee && (status === "ALL" || demand.status === status) && (priority === "ALL" || demand.priority === priority) && matchesText;
  }), [demands, query, company, assignee, status, priority]);
  const scheduled = useMemo(() => filtered.filter((demand) => demand.deadlineAt).sort((a, b) => String(a.deadlineAt).localeCompare(String(b.deadlineAt))), [filtered]);
  const year = cursor.getFullYear(); const month = cursor.getMonth();
  const monthItems = scheduled.filter((demand) => { const date = new Date(demand.deadlineAt!); return date.getFullYear() === year && date.getMonth() === month; });
  const byDay = new Map<string, Demand[]>();
  monthItems.forEach((demand) => { const key = calendarDateKey(demand.deadlineAt!); byDay.set(key, [...(byDay.get(key) ?? []), demand]); });
  const firstDay = new Date(year, month, 1); const lastDay = new Date(year, month + 1, 0);
  const gridStart = new Date(year, month, 1 - ((firstDay.getDay() + 6) % 7));
  const cellCount = ((firstDay.getDay() + 6) % 7) + lastDay.getDate() > 35 ? 42 : 35;
  const gridDays = Array.from({ length: cellCount }, (_, index) => { const date = new Date(gridStart); date.setDate(gridStart.getDate() + index); return date; });
  const monthDays = Array.from({ length: lastDay.getDate() }, (_, index) => new Date(year, month, index + 1));
  const todayKey = calendarDateKey(new Date());
  const rawTitle = new Intl.DateTimeFormat("pt-BR", { month: "long", year: "numeric" }).format(cursor);
  const title = `${rawTitle.charAt(0).toLocaleUpperCase("pt-BR")}${rawTitle.slice(1)}`;
  useEffect(() => { window.localStorage.setItem("fluxo.calendar-mode", mode); }, [mode]);
  function moveMonth(amount: number) { setCursor((current) => new Date(current.getFullYear(), current.getMonth() + amount, 1)); }
  function clearFilters() { setQuery(""); setCompany("ALL"); setAssignee("ALL"); setStatus("ALL"); setPriority("ALL"); }
  const time = (demand: Demand) => demand.deadlineAt ? new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(new Date(demand.deadlineAt)) : "—";
  const activeFilters = Number(Boolean(query.trim())) + Number(company !== "ALL") + Number(assignee !== "ALL") + Number(status !== "ALL") + Number(priority !== "ALL");
  return <section className="calendar-workspace">
    <header className="calendar-toolbar"><div><span className="eyebrow dark">Planejamento editorial e operacional</span><h2>{title}</h2><p>{monthItems.length} {monthItems.length === 1 ? "demanda programada" : "demandas programadas"} neste mês · {scheduled.length} no calendário</p></div><div className="calendar-toolbar-actions"><div className="calendar-mode-switch" role="group" aria-label="Visualização do calendário"><button className={mode === "month" ? "active" : ""} onClick={() => setMode("month")}><ThemeIcon src={calendarIcon} className="view-icon" />Mês</button><button className={mode === "agenda" ? "active" : ""} onClick={() => setMode("agenda")}><ThemeIcon src={listViewIcon} className="view-icon" />Agenda por dia</button></div><div className="calendar-navigation"><button onClick={() => moveMonth(-1)} aria-label="Mês anterior">‹</button><button onClick={() => { const value = new Date(); setCursor(new Date(value.getFullYear(), value.getMonth(), 1)); }}>Hoje</button><button onClick={() => moveMonth(1)} aria-label="Próximo mês">›</button></div></div></header>
    <div className="calendar-filters" aria-label="Filtros do calendário">
      <label className="calendar-search"><span>Buscar</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Demanda, código, empresa ou pessoa" /></label>
      <label><span>Responsável</span><select value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="ALL">Todos os usuários</option><option value="UNASSIGNED">Sem responsável</option>{people.map((person) => <option value={person.id} key={person.id}>{person.name}</option>)}</select></label>
      <label><span>Empresa</span><select value={company} onChange={(event) => setCompany(event.target.value)}><option value="ALL">Todas as empresas</option><option value="UNASSIGNED">Sem empresa</option>{companies.map((item) => <option value={item.id} key={item.id}>{item.shortName}</option>)}</select></label>
      <label><span>Situação</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">Todas</option>{Object.entries(statusNames).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label><span>Prioridade</span><select value={priority} onChange={(event) => setPriority(event.target.value)}><option value="ALL">Todas</option>{Object.entries(priorityNames).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <button className="calendar-clear-filters" type="button" disabled={!activeFilters} onClick={clearFilters}>Limpar{activeFilters ? ` (${activeFilters})` : ""}</button>
    </div>
    {mode === "month" ? <div className="calendar-month"><div className="calendar-weekdays">{["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"].map((day) => <span key={day}>{day}</span>)}</div><div className="calendar-month-grid">{gridDays.map((date) => { const key = calendarDateKey(date); const items = byDay.get(key) ?? []; const outside = date.getMonth() !== month; return <article className={`calendar-day${outside ? " outside" : ""}${key === todayKey ? " today" : ""}`} key={key}><header><time dateTime={key}>{date.getDate()}</time>{items.length > 0 && <span>{items.length}</span>}</header><div>{items.slice(0, 4).map((demand) => <button className="calendar-event" key={demand.id} onClick={() => onOpen(demand)} title={demand.title}><i style={{ background: demand.companyColor ?? demand.categoryColor ?? "#94A3B8" }} /><span><strong>{demand.title}</strong><small>{time(demand)} · {demand.companyName ?? "Sem empresa"}</small></span></button>)}{items.length > 4 && <button className="calendar-more" onClick={() => setMode("agenda")}>+ {items.length - 4} materiais</button>}</div></article>; })}</div></div>
      : <div className="calendar-agenda-scroll"><div className="calendar-agenda"><div className="calendar-agenda-head"><span>Data</span><div><span>Material</span><span>Empresa</span><span>Responsável</span><span>Etapa</span><span>Situação</span><span>Prazo</span></div></div>{monthDays.map((date) => { const key = calendarDateKey(date); const items = byDay.get(key) ?? []; const weekend = date.getDay() === 0 || date.getDay() === 6; return <section className={`calendar-agenda-day${weekend ? " weekend" : ""}${key === todayKey ? " today" : ""}`} key={key}><header><strong>{String(date.getDate()).padStart(2, "0")}</strong><span>{new Intl.DateTimeFormat("pt-BR", { weekday: "long" }).format(date)}</span><small>{new Intl.DateTimeFormat("pt-BR", { month: "short" }).format(date)}</small></header><div>{items.length ? items.map((demand) => <button className="calendar-material" key={demand.id} onClick={() => onOpen(demand)}><span className="calendar-material-title"><i style={{ background: demand.companyColor ?? demand.categoryColor ?? "#94A3B8" }} /><span><strong>{demand.title}</strong><small>{demand.publicId} · {demand.categoryName ?? "Sem categoria"}</small></span></span><span>{demand.companyName ?? "Sem empresa"}</span><span>{demand.assigneeName ? <><AvatarView name={demand.assigneeName} url={demand.assigneeAvatarUrl} />{demand.assigneeName}</> : "Sem responsável"}</span><span>{demand.stageName ?? "Sem etapa"}</span><span><b className={`demand-status ${demand.status.toLowerCase()}`}>{statusNames[demand.status] ?? demand.status}</b></span><span className="calendar-material-deadline"><strong>{time(demand)}</strong><small className={`priority priority-${demand.priority.toLowerCase()}`}>{priorityNames[demand.priority] ?? demand.priority}</small></span></button>) : <p className="calendar-day-empty">Nenhuma demanda prevista para esta data.</p>}</div></section>; })}</div></div>}
  </section>;
}

