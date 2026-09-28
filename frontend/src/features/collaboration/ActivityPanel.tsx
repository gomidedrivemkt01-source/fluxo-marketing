import { FormEvent, useEffect, useMemo, useState } from "react";

import { api, messageFrom } from "../../api";

type ActivityItem = {
  id: string;
  itemType: "comment" | "event";
  kind: string;
  summary: string;
  content: string | null;
  actorId: string;
  actorName: string;
  actorAvatarUrl: string | null;
  revision: number | null;
  editedAt: string | null;
  deletedAt: string | null;
  canEdit: boolean;
  canDelete: boolean;
  createdAt: string;
};

type ActivityPage = { items: ActivityItem[]; nextCursor: string | null };
type Watcher = {
  id: string;
  name: string;
  avatarUrl: string | null;
  addedAt: string;
  isCurrentUser: boolean;
};

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

function ActivityAvatar({ name, url }: { name: string; url: string | null }) {
  return (
    <span className="activity-avatar" aria-label={name} title={name}>
      {url ? <img src={url} alt="" /> : initials(name)}
    </span>
  );
}

function activityDate(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function ActivityPanel({ demandId, canComment }: { demandId: string; canComment: boolean }) {
  const [activity, setActivity] = useState<ActivityPage | null>(null);
  const [watchers, setWatchers] = useState<Watcher[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<ActivityItem | null>(null);

  const following = useMemo(
    () => watchers?.some((watcher) => watcher.isCurrentUser) ?? false,
    [watchers],
  );

  async function load() {
    setError("");
    try {
      const [activityPage, watcherList] = await Promise.all([
        api<ActivityPage>(`/demands/${demandId}/activity`),
        api<Watcher[]>(`/demands/${demandId}/watchers`),
      ]);
      setActivity(activityPage);
      setWatchers(watcherList);
    } catch (caught) {
      setError(messageFrom(caught));
    }
  }

  useEffect(() => {
    setActivity(null);
    setWatchers(null);
    void load();
  }, [demandId]);

  async function submitComment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const content = String(new FormData(form).get("content") ?? "").trim();
    if (!content) return;
    setBusy(true);
    setError("");
    try {
      const created = await api<ActivityItem>(`/demands/${demandId}/comments`, {
        method: "POST",
        body: JSON.stringify({ content }),
      });
      setActivity((current) => ({
        items: [created, ...(current?.items ?? [])],
        nextCursor: current?.nextCursor ?? null,
      }));
      form.reset();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing?.revision) return;
    const content = String(new FormData(event.currentTarget).get("content") ?? "").trim();
    if (!content) return;
    setBusy(true);
    setError("");
    try {
      const updated = await api<ActivityItem>(
        `/demands/${demandId}/comments/${editing.id}`,
        {
          method: "PUT",
          body: JSON.stringify({ content, expectedRevision: editing.revision }),
        },
      );
      setActivity((current) =>
        current
          ? { ...current, items: current.items.map((item) => (item.id === updated.id ? updated : item)) }
          : current,
      );
      setEditing(null);
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  async function removeComment(item: ActivityItem) {
    if (!item.revision || !window.confirm("Remover este comentário da atividade?")) return;
    setBusy(true);
    setError("");
    try {
      await api(`/demands/${demandId}/comments/${item.id}`, {
        method: "DELETE",
        body: JSON.stringify({ expectedRevision: item.revision }),
      });
      await load();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  async function toggleFollowing() {
    setBusy(true);
    setError("");
    try {
      await api(`/demands/${demandId}/watchers/me`, {
        method: following ? "DELETE" : "PUT",
      });
      await load();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  async function loadMore() {
    if (!activity?.nextCursor) return;
    setBusy(true);
    setError("");
    try {
      const page = await api<ActivityPage>(
        `/demands/${demandId}/activity?before=${encodeURIComponent(activity.nextCursor)}`,
      );
      setActivity((current) => {
        if (!current) return page;
        const known = new Set(current.items.map((item) => `${item.itemType}:${item.id}`));
        return {
          items: [...current.items, ...page.items.filter((item) => !known.has(`${item.itemType}:${item.id}`))],
          nextCursor: page.nextCursor,
        };
      });
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy(false);
    }
  }

  if (!activity || !watchers) {
    return (
      <section className="panel activity-panel activity-loading">
        {error ? (
          <div className="feature-preview">
            <span>!</span>
            <h3>Não foi possível carregar a atividade</h3>
            <p>{error}</p>
            <button className="secondary compact" onClick={() => void load()}>
              Tentar novamente
            </button>
          </div>
        ) : (
          <span className="loader" aria-label="Carregando atividade" />
        )}
      </section>
    );
  }

  return (
    <section className="panel activity-panel">
      <header className="activity-head">
        <div>
          <span className="eyebrow dark">Colaboração</span>
          <h3>Atividade da demanda</h3>
          <p>Comentários e alterações importantes permanecem no mesmo histórico.</p>
        </div>
        <div className="watcher-control">
          <div className="watcher-stack" aria-label={`${watchers.length} acompanhantes`}>
            {watchers.slice(0, 4).map((watcher) => (
              <ActivityAvatar key={watcher.id} name={watcher.name} url={watcher.avatarUrl} />
            ))}
            {watchers.length > 4 && <span className="watcher-more">+{watchers.length - 4}</span>}
          </div>
          <button
            className={following ? "secondary compact following" : "secondary compact"}
            disabled={busy || !canComment}
            onClick={() => void toggleFollowing()}
          >
            {following ? "Acompanhando" : "Acompanhar"}
          </button>
        </div>
      </header>

      {canComment && (
        <form className="comment-composer" onSubmit={submitComment}>
          <textarea
            name="content"
            rows={3}
            maxLength={5000}
            placeholder="Registre uma decisão, dúvida ou atualização para a equipe…"
            aria-label="Novo comentário"
            required
          />
          <footer>
            <span>O comentário ficará visível para todos os membros com acesso à demanda.</span>
            <button className="primary action-primary" disabled={busy}>
              {busy ? "Publicando…" : "Comentar"}
            </button>
          </footer>
        </form>
      )}

      {error && <div className="activity-error">{error}</div>}

      <div className="activity-feed">
        {!activity.items.length ? (
          <div className="activity-empty">
            <span>◌</span>
            <strong>Nenhuma atividade registrada</strong>
            <p>O primeiro comentário ou movimento da demanda aparecerá aqui.</p>
          </div>
        ) : (
          activity.items.map((item) => (
            <article
              className={item.itemType === "comment" ? "activity-item comment-item" : "activity-item event-item"}
              key={`${item.itemType}:${item.id}`}
            >
              {item.itemType === "comment" ? (
                <ActivityAvatar name={item.actorName} url={item.actorAvatarUrl} />
              ) : (
                <span className="event-icon">↻</span>
              )}
              <div className="activity-body">
                <div className="activity-meta">
                  <strong>{item.actorName}</strong>
                  <time>{activityDate(item.createdAt)}</time>
                  {item.editedAt && !item.deletedAt && <em>Editado</em>}
                </div>
                {editing?.id === item.id ? (
                  <form className="comment-edit" onSubmit={saveEdit}>
                    <textarea name="content" rows={4} maxLength={5000} defaultValue={item.content ?? ""} required />
                    <div>
                      <button type="button" className="secondary compact" onClick={() => setEditing(null)}>
                        Cancelar
                      </button>
                      <button className="primary compact" disabled={busy}>
                        Salvar edição
                      </button>
                    </div>
                  </form>
                ) : item.itemType === "comment" ? (
                  <p className={item.deletedAt ? "comment-deleted" : "comment-text"}>
                    {item.deletedAt ? "Comentário removido." : item.content}
                  </p>
                ) : (
                  <p className="event-summary">{item.summary}</p>
                )}
                {item.itemType === "comment" && !item.deletedAt && editing?.id !== item.id && (
                  <div className="comment-actions">
                    {item.canEdit && <button onClick={() => setEditing(item)}>Editar</button>}
                    {item.canDelete && <button onClick={() => void removeComment(item)}>Remover</button>}
                  </div>
                )}
              </div>
            </article>
          ))
        )}
      </div>

      {activity.nextCursor && (
        <button className="activity-more" disabled={busy} onClick={() => void loadMore()}>
          {busy ? "Carregando…" : "Carregar atividades anteriores"}
        </button>
      )}
    </section>
  );
}
