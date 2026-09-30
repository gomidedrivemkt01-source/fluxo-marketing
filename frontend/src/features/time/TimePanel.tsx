import { FormEvent, useEffect, useMemo, useState } from "react";

import { api, messageFrom } from "../../api";

type TimeEntry = {
  id: string;
  userId: string;
  userName: string;
  source: "MANUAL" | "TIMER";
  state: "RUNNING" | "PAUSED" | "COMPLETED";
  startedAt: string;
  endedAt: string | null;
  durationMinutes: number | null;
  note: string | null;
  revision: number;
  canEdit: boolean;
  createdAt: string;
};

type TimeSummary = {
  expectedEffortMinutes: number | null;
  totalMinutes: number;
  myTotalMinutes: number;
  activeTimer: TimeEntry | null;
  entries: TimeEntry[];
  demandRevision: number;
};

type TimeEstimate = {
  expectedEffortMinutes: number | null;
  demandRevision: number;
};

type TimePanelProps = {
  demandId: string;
  canTrack: boolean;
  canEditEstimate: boolean;
  onEstimateSaved: (expectedEffortMinutes: number | null, demandRevision: number) => void;
};

function durationLabel(minutes: number | null): string {
  if (minutes === null) return "Em andamento";
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;
  if (hours && remaining) return `${hours}h ${remaining}min`;
  if (hours) return `${hours}h`;
  return `${remaining}min`;
}

function dateLabel(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function localDateTimeValue(date = new Date()): string {
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function runningLabel(startedAt: string, now: number, accumulatedMinutes = 0): string {
  const seconds = accumulatedMinutes * 60 + Math.max(0, Math.floor((now - new Date(startedAt).getTime()) / 1000));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remaining = seconds % 60;
  return [hours, minutes, remaining].map((value) => String(value).padStart(2, "0")).join(":");
}

export function TimePanel({
  demandId,
  canTrack,
  canEditEstimate,
  onEstimateSaved,
}: TimePanelProps) {
  const [summary, setSummary] = useState<TimeSummary | null>(null);
  const [estimate, setEstimate] = useState("");
  const [timerNote, setTimerNote] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [now, setNow] = useState(Date.now());
  const [editingId, setEditingId] = useState("");
  const [editMinutes, setEditMinutes] = useState("");
  const [editNote, setEditNote] = useState("");

  async function load() {
    setError("");
    try {
      const data = await api<TimeSummary>(`/demands/${demandId}/time`);
      setSummary(data);
      setEstimate(data.expectedEffortMinutes?.toString() ?? "");
    } catch (caught) {
      setError(messageFrom(caught));
    }
  }

  useEffect(() => {
    setSummary(null);
    setEditingId("");
    void load();
  }, [demandId]);

  useEffect(() => {
    if (!summary?.activeTimer) return;
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, [summary?.activeTimer?.id]);

  const progress = useMemo(() => {
    if (!summary?.expectedEffortMinutes) return 0;
    return Math.min(100, Math.round((summary.totalMinutes / summary.expectedEffortMinutes) * 100));
  }, [summary?.expectedEffortMinutes, summary?.totalMinutes]);

  async function saveEstimate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!summary) return;
    const minutes = estimate ? Number(estimate) : null;
    setBusy("estimate");
    setError("");
    setSuccess("");
    try {
      const updated = await api<TimeEstimate>(`/demands/${demandId}/time/estimate`, {
        method: "PUT",
        body: JSON.stringify({
          expectedEffortMinutes: minutes,
          expectedRevision: summary.demandRevision,
        }),
      });
      onEstimateSaved(updated.expectedEffortMinutes, updated.demandRevision);
      setSuccess("Esforço previsto atualizado.");
      await load();
    } catch (caught) {
      setError(messageFrom(caught));
      await load();
    } finally {
      setBusy("");
    }
  }

  async function startTimer() {
    setBusy("timer");
    setError("");
    setSuccess("");
    try {
      await api(`/demands/${demandId}/time/timer/start`, {
        method: "POST",
        body: JSON.stringify({ note: timerNote.trim() || null }),
      });
      setTimerNote("");
      setNow(Date.now());
      await load();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy("");
    }
  }

  async function stopTimer() {
    if (!summary?.activeTimer) return;
    setBusy("timer");
    setError("");
    setSuccess("");
    try {
      await api(`/demands/${demandId}/time/timer/stop`, {
        method: "POST",
        body: JSON.stringify({ expectedRevision: summary.activeTimer.revision }),
      });
      setSuccess("Timer encerrado e tempo registrado.");
      await load();
    } catch (caught) {
      setError(messageFrom(caught));
      await load();
    } finally {
      setBusy("");
    }
  }

  async function changeTimer(action: "pause" | "resume") {
    if (!summary?.activeTimer) return;
    setBusy("timer"); setError(""); setSuccess("");
    try {
      await api(`/demands/${demandId}/time/timer/${action}`, {
        method: "POST",
        body: JSON.stringify({ expectedRevision: summary.activeTimer.revision }),
      });
      setSuccess(action === "pause" ? "Timer pausado." : "Timer retomado.");
      setNow(Date.now());
      await load();
    } catch (caught) {
      setError(messageFrom(caught));
      await load();
    } finally {
      setBusy("");
    }
  }

  async function createManual(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const startedAt = String(data.get("startedAt"));
    setBusy("manual");
    setError("");
    setSuccess("");
    try {
      await api(`/demands/${demandId}/time/entries`, {
        method: "POST",
        body: JSON.stringify({
          startedAt: new Date(startedAt).toISOString(),
          durationMinutes: Number(data.get("durationMinutes")),
          note: String(data.get("note") ?? "").trim() || null,
        }),
      });
      form.reset();
      const started = form.elements.namedItem("startedAt") as HTMLInputElement | null;
      if (started) started.value = localDateTimeValue();
      setSuccess("Tempo adicionado ao histórico.");
      await load();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy("");
    }
  }

  function beginEdit(entry: TimeEntry) {
    setEditingId(entry.id);
    setEditMinutes(String(entry.durationMinutes ?? ""));
    setEditNote(entry.note ?? "");
  }

  async function updateEntry(entry: TimeEntry) {
    setBusy(entry.id);
    setError("");
    setSuccess("");
    try {
      await api(`/demands/${demandId}/time/entries/${entry.id}`, {
        method: "PUT",
        body: JSON.stringify({
          startedAt: entry.startedAt,
          durationMinutes: Number(editMinutes),
          note: editNote.trim() || null,
          expectedRevision: entry.revision,
        }),
      });
      setEditingId("");
      setSuccess("Apontamento atualizado.");
      await load();
    } catch (caught) {
      setError(messageFrom(caught));
      await load();
    } finally {
      setBusy("");
    }
  }

  async function removeEntry(entry: TimeEntry) {
    if (!window.confirm("Remover este apontamento de tempo da demanda?")) return;
    setBusy(entry.id);
    setError("");
    setSuccess("");
    try {
      await api(`/demands/${demandId}/time/entries/${entry.id}`, {
        method: "DELETE",
        body: JSON.stringify({ expectedRevision: entry.revision }),
      });
      setSuccess("Apontamento removido.");
      await load();
    } catch (caught) {
      setError(messageFrom(caught));
      await load();
    } finally {
      setBusy("");
    }
  }

  if (!summary) {
    return (
      <section className="panel time-panel time-loading">
        {error ? (
          <div className="feature-preview">
            <span>!</span>
            <h3>Não foi possível carregar os tempos</h3>
            <p>{error}</p>
            <button className="secondary compact" onClick={() => void load()}>
              Tentar novamente
            </button>
          </div>
        ) : (
          <span className="loader" aria-label="Carregando tempos" />
        )}
      </section>
    );
  }

  const exceeded = Boolean(
    summary.expectedEffortMinutes && summary.totalMinutes > summary.expectedEffortMinutes,
  );

  return (
    <section className="panel time-panel">
      <header className="time-head">
        <div>
          <span className="eyebrow dark">Capacidade e execução</span>
          <h3>Tempo e esforço</h3>
          <p>Compare a estimativa de trabalho humano com o tempo registrado pela equipe.</p>
        </div>
        <span>{summary.entries.length} {summary.entries.length === 1 ? "registro" : "registros"}</span>
      </header>

      {error && <div className="activity-error">{error}</div>}
      {success && <div className="time-success">{success}</div>}

      <div className="time-summary-grid">
        <article>
          <span>Esforço previsto</span>
          <strong>{summary.expectedEffortMinutes ? durationLabel(summary.expectedEffortMinutes) : "—"}</strong>
          <small>Estimativa total da demanda</small>
        </article>
        <article className={exceeded ? "exceeded" : ""}>
          <span>Tempo realizado</span>
          <strong>{durationLabel(summary.totalMinutes)}</strong>
          <small>{summary.expectedEffortMinutes ? `${progress}% do previsto` : "Sem estimativa para comparar"}</small>
        </article>
        <article>
          <span>Meu tempo</span>
          <strong>{durationLabel(summary.myTotalMinutes)}</strong>
          <small>Seus apontamentos concluídos</small>
        </article>
      </div>

      {summary.expectedEffortMinutes && (
        <div className={`time-progress ${exceeded ? "exceeded" : ""}`}>
          <i><b style={{ width: `${progress}%` }} /></i>
          <span>{exceeded ? "O realizado ultrapassou a estimativa" : `${progress}% realizado`}</span>
        </div>
      )}

      <div className="time-controls">
        <section className="timer-card">
          <div>
            <span className="eyebrow dark">Cronômetro</span>
            <h4>{summary.activeTimer ? (summary.activeTimer.state === "PAUSED" ? "Timer pausado" : "Timer em andamento") : "Iniciar trabalho"}</h4>
          </div>
          {summary.activeTimer ? (
            <>
              <strong className="timer-clock">{summary.activeTimer.state === "PAUSED" ? durationLabel(summary.activeTimer.durationMinutes) : runningLabel(summary.activeTimer.startedAt, now, summary.activeTimer.durationMinutes ?? 0)}</strong>
              <p>{summary.activeTimer.note || "Sem observação"}</p>
              <div className="timer-action-row"><button className="timer-pause" disabled={busy === "timer"} onClick={() => void changeTimer(summary.activeTimer?.state === "PAUSED" ? "resume" : "pause")}>{summary.activeTimer.state === "PAUSED" ? "▶ Continuar" : "Ⅱ Pausar"}</button><button className="timer-stop" disabled={busy === "timer"} onClick={() => void stopTimer()}>✓ {busy === "timer" ? "Salvando…" : "Concluir"}</button></div>
            </>
          ) : (
            <>
              <label className="field">
                <span>Observação opcional</span>
                <input
                  value={timerNote}
                  maxLength={1000}
                  placeholder="Ex.: criação do roteiro"
                  disabled={!canTrack || busy === "timer"}
                  onChange={(event) => setTimerNote(event.target.value)}
                />
              </label>
              <button
                className="timer-start"
                disabled={!canTrack || busy === "timer"}
                onClick={() => void startTimer()}
              >
                ▶ {busy === "timer" ? "Iniciando…" : "Iniciar timer"}
              </button>
              <small>Você pode manter apenas um timer ativo em toda a plataforma.</small>
            </>
          )}
        </section>

        <form className="manual-time-form" onSubmit={createManual}>
          <div>
            <span className="eyebrow dark">Registro manual</span>
            <h4>Adicionar tempo concluído</h4>
          </div>
          <div className="time-form-grid">
            <label className="field">
              <span>Início</span>
              <input
                name="startedAt"
                type="datetime-local"
                defaultValue={localDateTimeValue()}
                disabled={!canTrack}
                required
              />
            </label>
            <label className="field">
              <span>Minutos</span>
              <input
                name="durationMinutes"
                type="number"
                min={1}
                max={1440}
                placeholder="60"
                disabled={!canTrack}
                required
              />
            </label>
          </div>
          <label className="field">
            <span>Observação opcional</span>
            <input name="note" maxLength={1000} placeholder="O que foi realizado" disabled={!canTrack} />
          </label>
          <button className="secondary time-submit" disabled={!canTrack || busy === "manual"}>
            {busy === "manual" ? "Adicionando…" : "+ Adicionar tempo"}
          </button>
        </form>
      </div>

      <form className="estimate-form" onSubmit={saveEstimate}>
        <div>
          <strong>Esforço previsto da demanda</strong>
          <span>Informe a estimativa em minutos. Esta medida é separada da duração de calendário da etapa.</span>
        </div>
        <label>
          <input
            type="number"
            min={1}
            max={100000}
            value={estimate}
            placeholder="Sem estimativa"
            disabled={!canEditEstimate}
            onChange={(event) => setEstimate(event.target.value)}
          />
          <span>min</span>
        </label>
        <button className="secondary compact" disabled={!canEditEstimate || busy === "estimate"}>
          {busy === "estimate" ? "Salvando…" : "Salvar estimativa"}
        </button>
      </form>

      <div className="time-history">
        <header>
          <div>
            <span className="eyebrow dark">Histórico</span>
            <h4>Apontamentos da equipe</h4>
          </div>
          <span>Total · {durationLabel(summary.totalMinutes)}</span>
        </header>
        {!summary.entries.length ? (
          <div className="time-empty">
            <span>◷</span>
            <strong>Nenhum tempo registrado</strong>
            <p>Use o timer ou adicione um período concluído manualmente.</p>
          </div>
        ) : (
          <div className="time-entry-list">
            {summary.entries.map((entry) => (
              <article className={entry.state === "RUNNING" ? "running" : entry.state === "PAUSED" ? "paused" : ""} key={entry.id}>
                <span className="time-source">{entry.source === "TIMER" ? "◷" : "+"}</span>
                {editingId === entry.id ? (
                  <div className="time-entry-edit">
                    <div>
                      <label className="field">
                        <span>Minutos</span>
                        <input
                          type="number"
                          min={1}
                          max={1440}
                          value={editMinutes}
                          onChange={(event) => setEditMinutes(event.target.value)}
                        />
                      </label>
                      <label className="field">
                        <span>Observação</span>
                        <input
                          maxLength={1000}
                          value={editNote}
                          onChange={(event) => setEditNote(event.target.value)}
                        />
                      </label>
                    </div>
                    <footer>
                      <button className="secondary compact" onClick={() => setEditingId("")}>Cancelar</button>
                      <button
                        className="primary compact"
                        disabled={!editMinutes || busy === entry.id}
                        onClick={() => void updateEntry(entry)}
                      >
                        Salvar
                      </button>
                    </footer>
                  </div>
                ) : (
                  <>
                    <div className="time-entry-copy">
                      <strong>{entry.userName}<em>{entry.source === "TIMER" ? "Timer" : "Manual"}</em></strong>
                      <span>{dateLabel(entry.startedAt)}{entry.note ? ` · ${entry.note}` : ""}</span>
                    </div>
                    <b>{entry.state === "RUNNING" ? runningLabel(entry.startedAt, now, entry.durationMinutes ?? 0) : durationLabel(entry.durationMinutes)}</b>
                    {entry.canEdit && entry.state === "COMPLETED" && (
                      <div className="time-entry-actions">
                        <button disabled={busy === entry.id} onClick={() => beginEdit(entry)}>Editar</button>
                        <button disabled={busy === entry.id} onClick={() => void removeEntry(entry)}>Remover</button>
                      </div>
                    )}
                  </>
                )}
              </article>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
