import { useEffect, useMemo, useState } from "react";

import { api, messageFrom } from "../../api";

type TimerEntry = {
  id: string;
  state: "RUNNING" | "PAUSED";
  startedAt: string;
  durationMinutes: number | null;
  revision: number;
};

type ActiveTimer = {
  demandId: string;
  demandPublicId: string;
  demandTitle: string;
  timer: TimerEntry;
};

type CurrentDemand = { id: string; publicId: string; title: string } | null;

function clockLabel(timer: TimerEntry | null, now: number): string {
  if (!timer) return "00:00:00";
  const accumulated = (timer.durationMinutes ?? 0) * 60;
  const running = timer.state === "RUNNING"
    ? Math.max(0, Math.floor((now - new Date(timer.startedAt).getTime()) / 1000))
    : 0;
  const seconds = accumulated + running;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const rest = seconds % 60;
  return [hours, minutes, rest].map((value) => String(value).padStart(2, "0")).join(":");
}

export function GlobalTimer({
  currentDemand,
  canTrack,
  hasStageDock,
  onOpenDemand,
}: {
  currentDemand: CurrentDemand;
  canTrack: boolean;
  hasStageDock: boolean;
  onOpenDemand: (demandId: string) => void;
}) {
  const [active, setActive] = useState<ActiveTimer | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());

  async function load() {
    try {
      setActive(await api<ActiveTimer | null>("/time/active"));
      setError("");
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    void load();
    const listener = () => void load();
    window.addEventListener("fluxo:timer-changed", listener);
    return () => window.removeEventListener("fluxo:timer-changed", listener);
  }, []);

  useEffect(() => {
    if (active?.timer.state !== "RUNNING") return;
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [active?.timer.id, active?.timer.state]);

  const demand = useMemo(
    () => active
      ? { id: active.demandId, publicId: active.demandPublicId, title: active.demandTitle }
      : currentDemand,
    [active, currentDemand],
  );

  async function start() {
    if (!currentDemand) return;
    setBusy(true); setError("");
    try {
      await api(`/demands/${currentDemand.id}/time/timer/start`, {
        method: "POST",
        body: JSON.stringify({ note: null }),
      });
      await load();
      window.dispatchEvent(new Event("fluxo:timer-changed"));
    } catch (caught) { setError(messageFrom(caught)); }
    finally { setBusy(false); }
  }

  async function change(action: "pause" | "resume" | "stop") {
    if (!active) return;
    setBusy(true); setError("");
    try {
      await api(`/demands/${active.demandId}/time/timer/${action}`, {
        method: "POST",
        body: JSON.stringify({ expectedRevision: active.timer.revision }),
      });
      await load();
      window.dispatchEvent(new Event("fluxo:timer-changed"));
    } catch (caught) { setError(messageFrom(caught)); await load(); }
    finally { setBusy(false); }
  }

  if (!loaded || (!active && (!currentDemand || !canTrack))) return null;
  const outsideActiveCard = Boolean(active && currentDemand?.id !== active.demandId);
  return (
    <aside className={`global-timer${active ? " active" : ""}${hasStageDock ? " with-stage-dock" : ""}`} aria-live="polite">
      {error && <span className="global-timer-error" title={error}>!</span>}
      <button
        className={`timer-orb ${active?.timer.state === "RUNNING" ? "running" : ""}`}
        type="button"
        disabled={busy}
        onClick={() => active ? void change(active.timer.state === "RUNNING" ? "pause" : "resume") : void start()}
        aria-label={active?.timer.state === "RUNNING" ? "Pausar timer" : active ? "Continuar timer" : "Iniciar timer"}
      >
        <span>{active?.timer.state === "RUNNING" ? "Ⅱ" : "▶"}</span>
      </button>
      <div className="global-timer-copy">
        <strong>{clockLabel(active?.timer ?? null, now)}</strong>
        <span>{demand?.publicId} · {active ? (active.timer.state === "RUNNING" ? "Em andamento" : "Pausado") : "Pronto para iniciar"}</span>
      </div>
      {active && <button className="timer-finish" type="button" disabled={busy} onClick={() => void change("stop")} title="Concluir apontamento">✓</button>}
      {outsideActiveCard && <button className="timer-open-card" type="button" onClick={() => onOpenDemand(active!.demandId)}>Abrir card</button>}
    </aside>
  );
}
