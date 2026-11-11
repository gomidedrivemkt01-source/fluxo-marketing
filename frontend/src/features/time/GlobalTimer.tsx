import { useEffect, useRef, useState } from "react";
import { api, messageFrom } from "../../api";
import pauseActionIcon from "../../assets/actions/pause.svg";
import playActionIcon from "../../assets/actions/play.svg";
import { ActionIcon } from "../../components/ActionIcon";

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
  const seconds =
    (timer?.durationMinutes ?? 0) * 60 +
    (timer?.state === "RUNNING"
      ? Math.max(
          0,
          Math.floor((now - new Date(timer.startedAt).getTime()) / 1000),
        )
      : 0);
  return [
    Math.floor(seconds / 3600),
    Math.floor((seconds % 3600) / 60),
    seconds % 60,
  ]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

export function GlobalTimer({
  currentDemand,
  canTrack,
  hasStageDock,
  hasDrawerFooter,
  onOpenDemand,
}: {
  currentDemand: CurrentDemand;
  canTrack: boolean;
  hasStageDock: boolean;
  hasDrawerFooter: boolean;
  onOpenDemand: (id: string) => void;
}) {
  const [active, setActive] = useState<ActiveTimer[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());
  const requestBusy = useRef(false);
  const requestSequence = useRef(0);
  async function load() {
    const sequence = ++requestSequence.current;
    try {
      const data = await api<ActiveTimer[]>("/time/active-timers");
      if (sequence === requestSequence.current) setActive(data);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setLoaded(true);
    }
  }
  async function start(demandId: string) {
    if (requestBusy.current) return;
    requestBusy.current = true;
    setBusy(true);
    setError("");
    try {
      await api(`/demands/${demandId}/time/timer/start`, {
        method: "POST",
        body: JSON.stringify({ note: null }),
      });
      window.dispatchEvent(new Event("fluxo:timer-changed"));
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      await load();
      requestBusy.current = false;
      setBusy(false);
    }
  }
  async function change(
    item: ActiveTimer,
    action: "pause" | "resume" | "stop",
  ) {
    if (requestBusy.current) return;
    requestBusy.current = true;
    setBusy(true);
    setError("");
    try {
      await api(`/demands/${item.demandId}/time/timer/${action}`, {
        method: "POST",
        body: JSON.stringify({ expectedRevision: item.timer.revision }),
      });
      window.dispatchEvent(new Event("fluxo:timer-changed"));
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      await load();
      requestBusy.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    void load();
    const listener = () => void load();
    const startListener = (event: Event) => {
      const id = (event as CustomEvent<{ demandId?: string }>).detail?.demandId;
      if (id) void start(id);
    };
    const focus = () => {
      if (!document.hidden) void load();
    };
    const poll = window.setInterval(focus, 15000);
    window.addEventListener("fluxo:timer-changed", listener);
    window.addEventListener("fluxo:timer-start-request", startListener);
    window.addEventListener("focus", focus);
    return () => {
      window.clearInterval(poll);
      window.removeEventListener("fluxo:timer-changed", listener);
      window.removeEventListener("fluxo:timer-start-request", startListener);
      window.removeEventListener("focus", focus);
    };
  }, []);
  const running = active.some((item) => item.timer.state === "RUNNING");
  useEffect(() => {
    if (!running) return;
    setNow(Date.now());
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [running]);
  const idleDemand =
    currentDemand &&
    canTrack &&
    !active.some((item) => item.demandId === currentDemand.id)
      ? currentDemand
      : null;
  if (!loaded || (!active.length && !idleDemand && !error)) return null;
  return (
    <aside
      className={`global-timer-stack${hasStageDock ? " with-stage-dock" : ""}${hasDrawerFooter ? " with-drawer-footer" : ""}`}
      aria-label="Meus timers"
    >
      {error && (
        <div className="timer-stack-error" role="alert">
          {error}
          <button
            onClick={() => setError("")}
            aria-label="Fechar aviso do timer"
          >
            ×
          </button>
        </div>
      )}
      {active.length === 2 && (
        <small className="timer-parallel-note">
          2 timers abertos · tempos contabilizados por demanda
        </small>
      )}
      {active.map((item) => (
        <div className="global-timer active" key={item.timer.id}>
          <button
            className={`timer-orb ${item.timer.state === "RUNNING" ? "running" : ""}`}
            type="button"
            disabled={busy || !canTrack}
            onClick={() =>
              void change(
                item,
                item.timer.state === "RUNNING" ? "pause" : "resume",
              )
            }
            aria-label={`${item.timer.state === "RUNNING" ? "Pausar" : "Continuar"} timer de ${item.demandTitle}`}
          >
            <ActionIcon
              src={
                item.timer.state === "RUNNING"
                  ? pauseActionIcon
                  : playActionIcon
              }
            />
          </button>
          <div className="global-timer-copy">
            <strong>{clockLabel(item.timer, now)}</strong>
            <span title={item.demandTitle}>
              {item.demandPublicId} ·{" "}
              {item.timer.state === "RUNNING" ? "Em andamento" : "Pausado"}
            </span>
            <small className="timer-demand-title" title={item.demandTitle}>
              {item.demandTitle}
            </small>
          </div>
          <button
            className="timer-finish"
            type="button"
            disabled={busy || !canTrack}
            onClick={() => void change(item, "stop")}
            aria-label={`Concluir timer de ${item.demandTitle}`}
          >
            ✓
          </button>
          {currentDemand?.id !== item.demandId && (
            <button
              className="timer-open-card"
              type="button"
              onClick={() => onOpenDemand(item.demandId)}
            >
              Abrir card
            </button>
          )}
        </div>
      ))}
      {idleDemand && (
        <div className="global-timer">
          <button
            className="timer-orb"
            type="button"
            disabled={busy || active.length >= 2}
            onClick={() => void start(idleDemand.id)}
            aria-label={`Iniciar timer de ${idleDemand.title}`}
          >
            <ActionIcon src={playActionIcon} />
          </button>
          <div className="global-timer-copy">
            <strong>00:00:00</strong>
            <span>
              {idleDemand.publicId} ·{" "}
              {active.length >= 2
                ? "Conclua um dos timers abertos"
                : "Pronto para iniciar"}
            </span>
          </div>
        </div>
      )}
    </aside>
  );
}
