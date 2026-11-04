import { useState } from "react";
import { api, messageFrom } from "../api";
import FunctionsManager from "../features/management/FunctionsManager";
import {
  PersonRemovalDialog,
  ResponsibilityEditor,
  type TeamUser,
} from "../features/management/ManagementDialogs";

export default function TeamPage({
  users,
  isAdmin,
  ownProfileId,
  onReload,
}: {
  users: TeamUser[];
  isAdmin: boolean;
  ownProfileId?: string;
  onReload: () => Promise<void>;
}) {
  const [editing, setEditing] = useState<TeamUser | null>(null);
  const [removing, setRemoving] = useState<TeamUser | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [showFunctions, setShowFunctions] = useState(false);
  async function access(user: TeamUser) {
    setBusy(user.id);
    setError("");
    try {
      await api(`/users/${user.id}`, {
        method: "PUT",
        body: JSON.stringify({
          role: user.role ?? "collaborator",
          state: user.state === "suspended" ? "active" : "suspended",
          expectedRevision: user.revision,
        }),
      });
      await onReload();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy("");
    }
  }
  if (showFunctions)
    return (
      <>
        <button
          className="secondary compact"
          onClick={() => setShowFunctions(false)}
        >
          ← Voltar à equipe
        </button>
        <FunctionsManager onSaved={onReload} />
      </>
    );
  return (
    <section className="panel page-panel">
      <div className="panel-head">
        <div>
          <h3>Equipe</h3>
          <p>
            Abra uma pessoa para editar funções e responsabilidades em todos os
            workflows.
          </p>
        </div>
        <button
          className="secondary compact"
          onClick={() => setShowFunctions(true)}
        >
          Gerenciar funções
        </button>
      </div>
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Pessoa</th>
              <th>Situação</th>
              <th>Perfil de acesso</th>
              <th>Ações</th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr key={user.id}>
                <td>
                  <button
                    className="team-person-button"
                    onClick={() => setEditing(user)}
                  >
                    {user.avatarUrl ? (
                      <img src={user.avatarUrl} alt="" />
                    ) : (
                      <span>{user.name.slice(0, 1)}</span>
                    )}
                    <span>
                      <strong>{user.name}</strong>
                      <small>{user.email}</small>
                    </span>
                  </button>
                </td>
                <td>
                  {user.state === "active"
                    ? "Ativo"
                    : user.state === "suspended"
                      ? "Acesso removido"
                      : "Aguardando aprovação"}
                </td>
                <td>
                  {(
                    {
                      admin: "Administrador",
                      coordinator: "Coordenador",
                      collaborator: "Colaborador",
                      viewer: "Visualizador",
                    } as Record<string, string>
                  )[user.role ?? ""] ?? "Não definido"}
                </td>
                <td>
                  <div className="access-actions">
                    <button
                      className="table-action"
                      onClick={() => setEditing(user)}
                    >
                      Funções e etapas
                    </button>
                    {isAdmin &&
                      user.profileId !== ownProfileId &&
                      user.state !== "pending_approval" && (
                        <>
                          <button
                            className="table-action"
                            disabled={busy === user.id}
                            onClick={() => void access(user)}
                          >
                            {user.state === "suspended"
                              ? "Reativar acesso"
                              : "Remover acesso"}
                          </button>
                          {user.state === "suspended" && (
                            <button
                              className="access-remove"
                              disabled={busy === user.id}
                              onClick={() => setRemoving(user)}
                            >
                              Excluir cadastro
                            </button>
                          )}
                        </>
                      )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!users.length && (
          <p className="management-body">Nenhuma pessoa cadastrada.</p>
        )}
      </div>
      {editing && (
        <ResponsibilityEditor
          person={editing}
          onClose={() => setEditing(null)}
          onSaved={onReload}
        />
      )}
      {removing && (
        <PersonRemovalDialog
          person={removing}
          onClose={() => setRemoving(null)}
          onSaved={onReload}
        />
      )}
    </section>
  );
}
