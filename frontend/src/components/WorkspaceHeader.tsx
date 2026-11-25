import { useEffect, useId, useRef, useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";
import { InterfaceIcon } from "./InterfaceIcon";

export type NavigationGroup = { label: string; links: { id: string; label: string; icon: string; badge?: number }[] };
type Alert = { id: string; title: string; reason: string; deadline: string };

export function WorkspaceHeader({ brand, groups, page, name, role, avatarUrl, alerts, onGo, onLogout, onPreload, onLoadAlerts, onOpenAlert }: {
  brand: ReactNode;
  groups: NavigationGroup[];
  page: string;
  name: string;
  role: string;
  avatarUrl?: string | null;
  alerts: Alert[];
  onGo: (page: string) => void;
  onLogout: () => void;
  onPreload: (page: string) => void;
  onLoadAlerts: () => Promise<void>;
  onOpenAlert: (id: string) => void;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const [visibleAlerts, setVisibleAlerts] = useState(30);
  const [loadingAlerts, setLoadingAlerts] = useState(false);
  const [alertError, setAlertError] = useState("");
  const root = useRef<HTMLElement>(null);
  const prefix = useId();
  useEffect(() => { setOpen(null); }, [page]);
  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(null);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  function keyboard(event: KeyboardEvent<HTMLElement>) {
    const group = (event.target as HTMLElement).closest<HTMLElement>(".header-disclosure");
    if (!group) return;
    const trigger = group.querySelector<HTMLButtonElement>(".header-trigger");
    if (event.key === "Escape") { setOpen(null); trigger?.focus(); event.preventDefault(); }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const links = [...group.querySelectorAll<HTMLElement>(".header-popover a, .header-popover button")];
    if (!links.length) return;
    event.preventDefault();
    const index = links.findIndex((item) => item === document.activeElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? links.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
    links[next]?.focus();
  }
  function go(id: string) { setOpen(null); onGo(id); }
  async function toggleAlerts() {
    if (open === "alerts") { setOpen(null); return; }
    setOpen("alerts"); setVisibleAlerts(30); setLoadingAlerts(true); setAlertError("");
    try { await onLoadAlerts(); }
    catch { setAlertError("Não foi possível atualizar seus avisos. Tente abrir novamente."); }
    finally { setLoadingAlerts(false); }
  }
  return <header className="workspace-header" ref={root} onKeyDown={keyboard} onBlur={(event) => { if (event.relatedTarget instanceof Node && !event.currentTarget.contains(event.relatedTarget)) setOpen(null); }}>
    <a className="workspace-brand" href="/overview" onClick={(event) => { event.preventDefault(); go("overview"); }} aria-label="Fluxo Marketing — Visão geral">{brand}</a>
    <nav className="navigation-capsule" aria-label="Navegação principal">{groups.map((group, index) => {
      const active = group.links.some((link) => link.id === page);
      const expanded = open === group.label;
      const id = `${prefix}-group-${index}`;
      return <div className="header-disclosure" key={group.label}>
        <button className={`header-trigger nav-group-trigger${active ? " active" : ""}`} type="button" aria-expanded={expanded} aria-current={active ? "true" : undefined} aria-controls={id} onClick={() => setOpen(expanded ? null : group.label)} onKeyDown={(event) => { if (event.key === "ArrowDown" && !expanded) { event.preventDefault(); setOpen(group.label); window.requestAnimationFrame(() => document.getElementById(id)?.querySelector<HTMLElement>("a")?.focus()); } }}>{group.label}<InterfaceIcon name="chevron" /></button>
        {expanded && <div id={id} className="header-popover navigation-popover"><span className="header-popover-label">{group.label}</span>{group.links.map((link) => <a key={link.id} href={`/${link.id}`} aria-current={page === link.id ? "page" : undefined} onPointerEnter={() => onPreload(link.id)} onFocus={() => onPreload(link.id)} onClick={(event) => { if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return; event.preventDefault(); go(link.id); }}><span className="header-link-icon" style={{ "--icon-source": `url("${link.icon}")` } as CSSProperties} aria-hidden="true" /><span>{link.label}</span>{Boolean(link.badge) && <b>{link.badge}</b>}{page === link.id && <InterfaceIcon name="check" />}</a>)}</div>}
      </div>;
    })}</nav>
    <div className="workspace-user-controls">
      <div className="header-disclosure"><button type="button" className="header-trigger header-alert-trigger" aria-label={`Avisos da sua carteira${alerts.length ? `, ${alerts.length} pendências` : ""}`} aria-expanded={open === "alerts"} aria-controls={`${prefix}-alerts`} onClick={() => void toggleAlerts()}><InterfaceIcon name="bell" />{alerts.length > 0 && <i aria-hidden="true" />}</button>{open === "alerts" && <section className="header-popover alerts-popover" id={`${prefix}-alerts`} aria-label="Avisos operacionais"><header><strong>Sua atenção, agora</strong><span>Pendências da sua carteira</span></header>{loadingAlerts ? <p className="header-empty" role="status">Atualizando avisos…</p> : alertError ? <p className="header-empty" role="alert">{alertError}</p> : alerts.length ? <div className="header-alert-list">{alerts.slice(0, visibleAlerts).map((alert) => <button key={alert.id} onClick={() => { setOpen(null); onOpenAlert(alert.id); }}><span><strong>{alert.title}</strong><small>{alert.reason} · {alert.deadline}</small></span><InterfaceIcon name="arrow" /></button>)}{visibleAlerts < alerts.length && <button className="header-alert-more" onClick={() => setVisibleAlerts(value => value + 30)}>Mostrar mais avisos ({alerts.length})</button>}</div> : <p className="header-empty">Nenhum prazo em alerta ou aprovação pendente na sua carteira.</p>}</section>}</div>
      <div className="header-disclosure"><button type="button" className="header-trigger header-avatar-trigger" aria-label="Abrir menu do perfil" title={name} aria-expanded={open === "profile"} aria-controls={`${prefix}-profile`} onClick={() => setOpen(open === "profile" ? null : "profile")}>{avatarUrl ? <img src={avatarUrl} alt="" /> : <span>{name.charAt(0).toUpperCase()}</span>}</button>{open === "profile" && <div className="header-popover profile-popover" id={`${prefix}-profile`}><header><strong>{name}</strong><small>{role}</small></header><a href="/profile" onClick={(event) => { event.preventDefault(); go("profile"); }}>Meu perfil</a><button onClick={onLogout}>Sair da conta</button></div>}</div>
    </div>
  </header>;
}
