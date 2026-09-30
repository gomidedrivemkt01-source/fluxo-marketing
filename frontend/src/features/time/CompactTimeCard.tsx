import { useEffect, useState } from "react";

import { api, messageFrom } from "../../api";

type ActiveTimer = {
  id: string;
  state: "RUNNING" | "PAUSED" | "COMPLETED";
  startedAt: string;
  durationMinutes: number | null;
  revision: number;
};

type TimeSummary = {
  totalMinutes: number;
  myTotalMinutes: number;
  activeTimer: ActiveTimer | null;
};

function clockLabel(timer: ActiveTimer, now: number): string {
  const elapsed = timer.state === "RUNNING"
    ? Math.max(0, Math.floor((now - new Date(timer.startedAt).getTime()) / 1000))
    : 0;
  const seconds = (timer.durationMinutes ?? 0) * 60 + elapsed;
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = seconds % 60;
  return [hours, minutes, remaining].map((value) => String(value).padStart(2, "0")).join(":");
}

export function CompactTimeCard({ demandId, canTrack, onOpenAdvanced }: {
  demandId: string;
  canTrack: boolean;
  onOpenAdvanced: () => void;
}) {
  const [summary, setSummary] = useState<TimeSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now());

  async function load() {
    try {
      setSummary(await api<TimeSummary>(`/demands/${demandId}/time`));
      setError("");
    } catch (caught) {
      setError(messageFrom(caught));
    }
  }

  useEffect(() => { void load(); }, [demandId]);
  useEffect(() => {
    if (summary?.activeTimer?.state !== "RUNNING") return;
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [summary?.activeTimer?.id, summary?.activeTimer?.state]);

  async function act(action: "start" | "pause" | "resume" | "stop") {
    setBusy(true); setError("");
    try {
      await api(`/demands/${demandId}/time/timer/${action}`, {
        method: "POST",
        body: JSON.stringify(action === "start" ? { note: null } : { expectedRevision: summary?.activeTimer?.revision }),
      });
      setNow(Date.now());
      await load();
    } catch (caught) {
      setError(messageFrom(caught));
      await load();
    } finally {
      setBusy(false);
    }
  }

  const timer = summary?.activeTimer;
  return <section className="overview-block compact-time-card">
    <header><div><span className="overview-icon">◷</span><span><strong>Timer da demanda</strong><small>{timer ? (timer.state === "PAUSED" ? "Pausado" : "Em andamento") : "Pronto para iniciar"}</small></span></div><button className="overview-gear" onClick={onOpenAdvanced} aria-label="Configurações e registro manual de tempo" title="Configurações e registro manual">⚙</button></header>
    {error && <p className="compact-feature-error">{error}</p>}
    <div className="compact-timer-body">
      <strong>{timer ? clockLabel(timer, now) : "00:00:00"}</strong>
      {!timer ? <button className="timer-play" disabled={!canTrack || busy || !summary} onClick={() => void act("start")}>▶ <span>Iniciar</span></button> : <div>
        <button className="timer-pause" disabled={!canTrack || busy} onClick={() => void act(timer.state === "PAUSED" ? "resume" : "pause")}>{timer.state === "PAUSED" ? "▶ Continuar" : "Ⅱ Pausar"}</button>
        <button className="timer-complete" disabled={!canTrack || busy} onClick={() => void act("stop")}>✓ Concluir</button>
      </div>}
    </div>
    <footer><span>Meu total: <b>{summary?.myTotalMinutes ?? 0} min</b></span><button onClick={onOpenAdvanced}>Ver apontamentos</button></footer>
  </section>;
}
