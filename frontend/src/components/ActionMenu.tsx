import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

type MenuItem = { label: string; onSelect: () => void; disabled?: boolean; danger?: boolean; selected?: boolean };

export function ActionMenu({ label, children, items, disabled = false }: { label: string; children?: ReactNode; items: MenuItem[]; disabled?: boolean }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  function close() { setOpen(false); trigger.current?.focus(); }
  useEffect(() => {
    if (!open) return;
    const buttons = root.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)');
    buttons?.[0]?.focus();
    function outside(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target)) setOpen(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  function keyboard(event: KeyboardEvent) {
    if (event.key === "Escape") { event.preventDefault(); close(); return; }
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    if (!open) { setOpen(true); return; }
    const buttons = [...(root.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)') ?? [])];
    const index = buttons.findIndex((item) => item === document.activeElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
    buttons[next]?.focus();
  }
  return <div className="action-menu" ref={root} onKeyDown={keyboard} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false); }}>
    <button type="button" className="secondary compact action-menu-trigger" ref={trigger} aria-label={label} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} disabled={disabled} onClick={() => setOpen((value) => !value)}>{children ?? label}<span aria-hidden="true">⌄</span></button>
    {open && <div className="action-menu-options" role="menu" id={id} aria-label={label}>{items.map((item) => <button type="button" role="menuitem" aria-current={item.selected ? "true" : undefined} className={item.danger ? "danger-text" : undefined} key={item.label} disabled={item.disabled} onClick={() => { close(); item.onSelect(); }}><span>{item.label}</span>{item.selected && <span aria-hidden="true">✓</span>}</button>)}</div>}
  </div>;
}
