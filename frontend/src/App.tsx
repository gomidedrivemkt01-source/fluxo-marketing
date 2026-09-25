import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, messageFrom, type Session } from "./api";

type Page = "login" | "register" | "verify-signup" | "forgot" | "verify-recovery" | "reset";
type Company = { id: string; name: string; shortName: string; code: string; color: string; description: string | null; active: boolean; revision: number };
type Category = { id: string; name: string; code: string; color: string; active: boolean; revision: number };
type User = { id: string; profileId: string; name: string; email: string; state: string; role: string | null; revision: number; avatarUrl: string | null };
type Person = { id: string; name: string; avatarUrl: string | null };
type WorkflowStage = { id: string; name: string; code: string; color: string; position: number; active: boolean; revision: number };
type ViewPreferences = { demandView: "kanban" | "list"; showEmptyStages: boolean; stageOrder: string[] };
type Demand = {
  id: string;
  publicId: string;
  title: string;
  description: string | null;
  primaryCompanyId: string | null;
  companyName: string | null;
  companyColor: string | null;
  categoryId: string | null;
  categoryName: string | null;
  categoryColor: string | null;
  status: string;
  priority: string;
  deadlineAt: string | null;
  forecastAt: string | null;
  assigneeId: string | null;
  assigneeName: string | null;
  assigneeAvatarUrl: string | null;
  stageId: string | null;
  stageName: string | null;
  stageCode: string | null;
  stageColor: string | null;
  stagePosition: number | null;
  revision: number;
  createdAt: string;
};
type Profile = { profileId: string; name: string; email: string; timezone: string; role: string | null; revision: number; avatarUrl: string | null; preferences: ViewPreferences };
type WorkspacePage = "overview" | "my-work" | "demands" | "calendar" | "companies" | "team" | "reports" | "intelligence" | "workflows" | "categories" | "users" | "settings" | "profile";
type DailyProposal = { proposalId: string; type: string; payload: Record<string, unknown> };
type DailyItem = {
  id: string;
  ordinal: number;
  itemId: string;
  titleHint: string;
  companyHint: string | null;
  cardIdHint: string | null;
  summary: string;
  sourceExcerpt: string;
  proposals: DailyProposal[];
  action: "pending" | "map" | "create" | "ignore";
  targetDemandId: string | null;
  targetPublicId: string | null;
  targetTitle: string | null;
  newDemandTitle: string | null;
  note: string | null;
};
type DailyImport = {
  id: string;
  filename: string;
  batchId: string;
  sourceDate: string;
  sourceLabel: string;
  state: string;
  totalItems: number;
  reviewedItems: number;
  items: DailyItem[];
};
type MappingChoice = "map" | "create" | "ignore";

const statusNames: Record<string, string> = {
  WAITING_EXECUTION: "Aguardando execução",
  IN_PROGRESS: "Em andamento",
  WAITING_INFORMATION: "Aguardando informação",
  WAITING_APPROVAL: "Aguardando aprovação",
  BLOCKED: "Bloqueada",
  SCHEDULED: "Agendada",
  COMPLETED: "Concluída",
};

const proposalNames: Record<string, string> = {
  ADD_COMMENT: "Adicionar comentário",
  SET_FORECAST: "Atualizar previsão",
  SET_DEADLINE: "Atualizar prazo",
  SET_STATUS: "Atualizar situação",
  SUGGEST_ASSIGNEE: "Sugerir responsável",
  SUGGEST_STAGE: "Sugerir etapa",
};

const roleNames: Record<string, string> = {
  admin: "Administrador",
  coordinator: "Coordenador",
  collaborator: "Colaborador",
  viewer: "Visualizador",
};

function Brand() {
  return (
    <div className="brand" aria-label="Fluxo Marketing">
      <span className="brand-mark" aria-hidden="true"><i /><i /><b /></span>
      <span><strong>Fluxo</strong><small>Marketing</small></span>
    </div>
  );
}

function Field({ label, ...props }: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return <label className="field"><span>{label}</span><input {...props} /></label>;
}

function Notice({ kind = "error", children }: { kind?: "error" | "success"; children: React.ReactNode }) {
  return <div className={`notice ${kind}`} role={kind === "error" ? "alert" : "status"}>{children}</div>;
}

function AuthShell({ children, eyebrow, title, text }: { children: React.ReactNode; eyebrow: string; title: string; text: string }) {
  return (
    <main className="auth-page">
      <section className="auth-story">
        <Brand />
        <div className="story-copy">
          <span className="eyebrow">Operação de Marketing</span>
          <h1>O trabalho visível.<br />O fluxo sob controle.</h1>
          <p>Demandas, responsáveis e decisões em um histórico compartilhado pela equipe.</p>
        </div>
        <div className="story-footer"><span>Ambiente interno</span><span>•</span><span>Acesso individual</span></div>
      </section>
      <section className="auth-panel">
        <div className="auth-card">
          <span className="eyebrow dark">{eyebrow}</span>
          <h2>{title}</h2>
          <p className="helper">{text}</p>
          {children}
        </div>
        <p className="security-note"><span aria-hidden="true">◇</span> Sua sessão é protegida e registrada.</p>
      </section>
    </main>
  );
}

function Login({ onSession, go }: { onSession: (session: Session) => void; go: (page: Page) => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      onSession(await api<Session>("/auth/login", { method: "POST", body: JSON.stringify({ email: data.get("email"), password: data.get("password") }) }));
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <AuthShell eyebrow="Bem-vindo" title="Entre na sua conta" text="Use o e-mail e a senha cadastrados para acessar seu espaço de trabalho.">
    <form onSubmit={submit} className="form-stack">
      {error && <Notice>{error}</Notice>}
      <Field label="E-mail" name="email" type="email" autoComplete="email" placeholder="nome@empresa.com" required />
      <Field label="Senha" name="password" type="password" autoComplete="current-password" placeholder="Sua senha" required />
      <button className="link-button align-right" type="button" onClick={() => go("forgot")}>Esqueci minha senha</button>
      <button className="primary" disabled={busy}>{busy ? "Entrando…" : "Entrar"}</button>
    </form>
    <p className="switch-copy">Ainda não tem acesso? <button className="link-button" onClick={() => go("register")}>Criar cadastro</button></p>
  </AuthShell>;
}

function Register({ continueWith, go }: { continueWith: (email: string) => void; go: (page: Page) => void }) {
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password"));
    if (password !== data.get("confirmPassword")) { setError("As senhas precisam ser iguais."); setBusy(false); return; }
    try {
      await api("/auth/register", { method: "POST", body: JSON.stringify({ name: data.get("name"), email: data.get("email"), password, privacyNoticeVersion: "draft-1" }) });
      continueWith(String(data.get("email")));
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <AuthShell eyebrow="Novo acesso" title="Crie seu cadastro" text="Após confirmar o e-mail, um administrador libera seu acesso à equipe.">
    <form onSubmit={submit} className="form-stack">
      {error && <Notice>{error}</Notice>}
      <Field label="Nome completo" name="name" autoComplete="name" required />
      <Field label="E-mail" name="email" type="email" autoComplete="email" required />
      <Field label="Senha" name="password" type="password" autoComplete="new-password" minLength={12} required />
      <Field label="Confirme a senha" name="confirmPassword" type="password" autoComplete="new-password" minLength={12} required />
      <label className="check"><input name="privacy" type="checkbox" required /><span>Li o aviso de privacidade e entendo o uso dos dados para gestão interna.</span></label>
      <button className="primary" disabled={busy}>{busy ? "Enviando código…" : "Continuar"}</button>
    </form>
    <p className="switch-copy">Já possui cadastro? <button className="link-button" onClick={() => go("login")}>Entrar</button></p>
  </AuthShell>;
}

function Verify({ email, purpose, onSignup, onRecovery, go }: { email: string; purpose: "signup" | "recovery"; onSignup: (session: Session) => void; onRecovery: (token: string) => void; go: (page: Page) => void }) {
  const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const result = await api<Session | { recoveryToken: string }>("/auth/verify-email", { method: "POST", body: JSON.stringify({ email, code: data.get("code"), purpose }) });
      if ("recoveryToken" in result) onRecovery(result.recoveryToken); else onSignup(result);
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function resend() {
    setBusy(true); setError(""); setNotice("");
    try {
      const path = purpose === "signup" ? "/auth/resend-signup" : "/auth/forgot-password";
      const result = await api<{ message: string }>(path, { method: "POST", body: JSON.stringify({ email }) });
      setNotice(result.message);
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <AuthShell eyebrow="Confirmação" title="Digite o código" text={`Enviamos um código numérico para ${email}. Ele expira em poucos minutos.`}>
    <form onSubmit={submit} className="form-stack">
      {error && <Notice>{error}</Notice>}
      {notice && <Notice kind="success">{notice}</Notice>}
      <Field label="Código de 6 a 8 números" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6,8}" minLength={6} maxLength={8} className="code-input" required />
      <button className="primary" disabled={busy}>{busy ? "Confirmando…" : "Confirmar código"}</button>
      <button className="secondary" type="button" disabled={busy} onClick={() => void resend()}>Reenviar código</button>
      <button className="secondary" type="button" onClick={() => go(purpose === "signup" ? "register" : "forgot")}>Voltar</button>
    </form>
  </AuthShell>;
}

function Forgot({ continueWith, go }: { continueWith: (email: string) => void; go: (page: Page) => void }) {
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      await api("/auth/forgot-password", { method: "POST", body: JSON.stringify({ email: data.get("email") }) });
      continueWith(String(data.get("email")));
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <AuthShell eyebrow="Recuperação" title="Recupere seu acesso" text="Informe seu e-mail. Se houver uma conta, enviaremos um código de recuperação.">
    <form onSubmit={submit} className="form-stack">
      {error && <Notice>{error}</Notice>}
      <Field label="E-mail" name="email" type="email" autoComplete="email" required />
      <button className="primary" disabled={busy}>{busy ? "Enviando…" : "Enviar código"}</button>
      <button className="secondary" type="button" onClick={() => go("login")}>Voltar ao login</button>
    </form>
  </AuthShell>;
}

function Reset({ recoveryToken, go }: { recoveryToken: string; go: (page: Page) => void }) {
  const [error, setError] = useState(""); const [success, setSuccess] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget); const password = String(data.get("password"));
    if (password !== data.get("confirmPassword")) { setError("As senhas precisam ser iguais."); setBusy(false); return; }
    try {
      const result = await api<{ message: string }>("/auth/reset-password", { method: "POST", body: JSON.stringify({ recoveryToken, password }) });
      setSuccess(result.message);
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <AuthShell eyebrow="Nova senha" title="Defina uma nova senha" text="Use uma frase longa e exclusiva, com pelo menos 12 caracteres.">
    {success ? <><Notice kind="success">{success}</Notice><button className="primary" onClick={() => go("login")}>Ir para o login</button></> :
      <form onSubmit={submit} className="form-stack">
        {error && <Notice>{error}</Notice>}
        <Field label="Nova senha" name="password" type="password" minLength={12} autoComplete="new-password" required />
        <Field label="Confirme a nova senha" name="confirmPassword" type="password" minLength={12} autoComplete="new-password" required />
        <button className="primary" disabled={busy}>{busy ? "Salvando…" : "Alterar senha"}</button>
      </form>}
  </AuthShell>;
}

function Pending({ session, logout }: { session: Session; logout: () => void }) {
  return <main className="waiting-page"><div className="waiting-card"><Brand /><div className="waiting-icon">⌛</div><span className="eyebrow dark">Cadastro confirmado</span><h1>Acesso aguardando liberação</h1><p>Seu e-mail foi validado. Um administrador precisa incluir <strong>{session.email}</strong> na equipe antes do primeiro acesso.</p><div className="waiting-steps"><span className="done">1</span><b>E-mail confirmado</b><i /><span>2</span><b>Liberação administrativa</b></div><button className="secondary" onClick={logout}>Sair</button></div></main>;
}

function proposalValue(proposal: DailyProposal): string {
  const raw = proposal.payload.value ?? proposal.payload.text ?? proposal.payload.hint;
  if (proposal.type === "SET_STATUS" && typeof raw === "string") return statusNames[raw] ?? raw;
  if ((proposal.type === "SET_FORECAST" || proposal.type === "SET_DEADLINE") && typeof raw === "string") {
    const value = new Date(raw);
    return Number.isNaN(value.getTime()) ? raw : value.toLocaleString("pt-BR");
  }
  return typeof raw === "string" ? raw : JSON.stringify(raw);
}

function DailyImportModal({ demands, initialImport, onClose, onApplied }: { demands: Demand[]; initialImport?: DailyImport | null; onClose: () => void; onApplied: () => void }) {
  const [daily, setDaily] = useState<DailyImport | null>(initialImport ?? null);
  const [activeIndex, setActiveIndex] = useState(() => initialImport?.items.findIndex((item) => item.action === "pending") ?? 0);
  const [choice, setChoice] = useState<MappingChoice>("map");
  const [targetDemandId, setTargetDemandId] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [note, setNote] = useState("");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ message: string; updated: number; created: number; ignored: number } | null>(null);
  const current = daily?.items[activeIndex];

  useEffect(() => {
    if (!current) return;
    const nextChoice: MappingChoice = current.action === "pending" ? "map" : current.action;
    setChoice(nextChoice);
    setTargetDemandId(current.targetDemandId ?? demands.find((demand) => demand.publicId === current.cardIdHint)?.id ?? "");
    setNewTitle(current.newDemandTitle ?? current.titleHint);
    setNote(current.note ?? "");
    setQuery("");
    setError("");
  }, [current?.id, current?.action, current?.targetDemandId, current?.newDemandTitle, current?.note, current?.titleHint, current?.cardIdHint, demands]);

  async function upload(file: File) {
    setBusy(true); setError("");
    try {
      const document = JSON.parse(await file.text()) as unknown;
      const created = await api<DailyImport>("/imports/dailys", { method: "POST", body: JSON.stringify({ filename: file.name, document }) });
      setDaily(created); setActiveIndex(0);
    } catch (caught) {
      if (caught instanceof SyntaxError) setError("O arquivo não contém um JSON válido.");
      else setError(messageFrom(caught));
    } finally { setBusy(false); }
  }

  async function saveChoice() {
    if (!daily || !current) return;
    if (choice === "map" && !targetDemandId) { setError("Escolha o card que receberá esta informação."); return; }
    if (choice === "create" && !newTitle.trim()) { setError("Informe o título do novo card."); return; }
    setBusy(true); setError("");
    try {
      const updated = await api<DailyImport>(`/imports/dailys/${daily.id}/items/${current.id}`, {
        method: "PUT",
        body: JSON.stringify({
          action: choice,
          targetDemandId: choice === "map" ? targetDemandId : null,
          newDemandTitle: choice === "create" ? newTitle.trim() : null,
          note: note.trim() || null,
        }),
      });
      setDaily(updated);
      const nextPending = updated.items.findIndex((item) => item.action === "pending");
      if (nextPending >= 0) setActiveIndex(nextPending);
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }

  async function applyImport() {
    if (!daily) return;
    setBusy(true); setError("");
    try {
      setResult(await api(`/imports/dailys/${daily.id}/apply`, { method: "POST" }));
      onApplied();
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }

  const filteredDemands = demands.filter((demand) => {
    const value = query.trim().toLocaleLowerCase("pt-BR");
    return !value || demand.title.toLocaleLowerCase("pt-BR").includes(value) || demand.publicId.toLocaleLowerCase("pt-BR").includes(value);
  });
  const complete = Boolean(daily && daily.reviewedItems === daily.totalItems);

  return <div className="modal-backdrop" role="presentation">
    <section className="daily-modal" role="dialog" aria-modal="true" aria-labelledby="daily-title">
      <header className="modal-head"><div><span className="eyebrow dark">Importação assistida</span><h2 id="daily-title">Revisar relatório de Daily</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header>
      {!daily ? <div className="upload-step">
        <div className="upload-icon">⇧</div><h3>Selecione o JSON analisado</h3><p>A plataforma valida a estrutura e abre cada demanda para você escolher o card. Nenhum card é alterado durante o upload.</p>
        {error && <Notice>{error}</Notice>}
        <label className={`file-button ${busy ? "disabled" : ""}`}>{busy ? "Validando arquivo…" : "Escolher arquivo JSON"}<input type="file" accept="application/json,.json" disabled={busy} onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void upload(file); }} /></label>
        <small>Formato aceito: Daily Review 2.0, até 200 itens.</small>
      </div> : result ? <div className="apply-success">
        <span>✓</span><h3>Informações aplicadas</h3><p>{result.message}</p><div><b>{result.updated}<small>cards atualizados</small></b><b>{result.created}<small>cards criados</small></b><b>{result.ignored}<small>itens ignorados</small></b></div><button className="primary" onClick={onClose}>Concluir</button>
      </div> : current && <>
        <div className="review-progress"><div><strong>{daily.sourceLabel}</strong><small>{daily.filename}</small></div><div className="progress-copy"><span>{daily.reviewedItems} de {daily.totalItems} revisadas</span><i><b style={{ width: `${(daily.reviewedItems / daily.totalItems) * 100}%` }} /></i></div></div>
        <div className="review-layout">
          <article className="daily-context">
            <div className="item-number">Demanda {current.ordinal} de {daily.totalItems}</div>
            <h3>{current.titleHint}</h3>
            <div className="hint-row">{current.companyHint && <span>Empresa sugerida: <b>{current.companyHint}</b></span>}{current.cardIdHint && <span>Card citado: <b>{current.cardIdHint}</b></span>}</div>
            <div className="context-block"><label>Resumo identificado</label><p>{current.summary}</p></div>
            <details><summary>Ver trecho original do relatório</summary><p>{current.sourceExcerpt}</p></details>
            <div className="proposal-list"><label>Alterações propostas</label>{current.proposals.map((proposal) => <div key={proposal.proposalId}><span>→</span><p><strong>{proposalNames[proposal.type] ?? proposal.type}</strong><small>{proposalValue(proposal)}</small></p></div>)}</div>
          </article>
          <aside className="mapping-panel">
            <div><span className="eyebrow dark">Sua decisão</span><h3>Para onde vai esta informação?</h3><p>Escolha uma opção para liberar o próximo item.</p></div>
            {error && <Notice>{error}</Notice>}
            <div className="choice-tabs" role="group" aria-label="Destino da informação">
              <button className={choice === "map" ? "active" : ""} onClick={() => setChoice("map")}><span>1</span>Associar a card</button>
              <button className={choice === "create" ? "active" : ""} onClick={() => setChoice("create")}><span>2</span>Criar novo card</button>
              <button className={choice === "ignore" ? "active" : ""} onClick={() => setChoice("ignore")}><span>3</span>Ignorar item</button>
            </div>
            {choice === "map" && <div className="choice-content"><label className="field"><span>Buscar por ID ou título</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Ex.: DMD-2026 ou campanha" /></label><label className="field"><span>Card de destino</span><select value={targetDemandId} onChange={(event) => setTargetDemandId(event.target.value)}><option value="">Selecione um card</option>{filteredDemands.map((demand) => <option key={demand.id} value={demand.id}>{demand.publicId} — {demand.title}</option>)}</select></label>{demands.length === 0 && <p className="inline-help">Ainda não há cards. Selecione “Criar novo card”.</p>}</div>}
            {choice === "create" && <div className="choice-content"><label className="field"><span>Título do novo card</span><input value={newTitle} onChange={(event) => setNewTitle(event.target.value)} maxLength={300} /></label><p className="inline-help">O card será criado somente quando toda a importação for aplicada.</p></div>}
            {choice === "ignore" && <div className="choice-content ignore-copy"><strong>Este item não será enviado a nenhum card.</strong><p>Ele continuará registrado na importação para auditoria.</p></div>}
            <label className="field note-field"><span>Observação da associação <small>(opcional)</small></span><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} placeholder="Registre o motivo ou contexto desta decisão." /></label>
          </aside>
        </div>
        <footer className="modal-actions"><div><button className="secondary compact" disabled={activeIndex === 0 || busy} onClick={() => setActiveIndex((value) => Math.max(0, value - 1))}>Anterior</button><button className="secondary compact" disabled={activeIndex === daily.items.length - 1 || busy} onClick={() => setActiveIndex((value) => Math.min(daily.items.length - 1, value + 1))}>Próxima</button></div>{complete ? <button className="primary action-primary" disabled={busy} onClick={() => void applyImport()}>{busy ? "Aplicando…" : "Aplicar todas as informações"}</button> : <button className="primary action-primary" disabled={busy} onClick={() => void saveChoice()}>{busy ? "Salvando…" : current.action === "pending" ? "Confirmar e ir para a próxima" : "Salvar decisão"}</button>}</footer>
      </>}
    </section>
  </div>;
}

const priorityNames: Record<string, string> = { LOW: "Baixa", NORMAL: "Normal", HIGH: "Alta", URGENT: "Urgente" };

const pageTitles: Record<WorkspacePage, { eyebrow: string; title: string }> = {
  overview: { eyebrow: "Operação compartilhada", title: "Início" },
  "my-work": { eyebrow: "Foco pessoal", title: "Meu trabalho" },
  demands: { eyebrow: "Operação", title: "Demandas" },
  calendar: { eyebrow: "Prazos", title: "Calendário" },
  companies: { eyebrow: "Organização", title: "Empresas" },
  team: { eyebrow: "Organização", title: "Equipe" },
  reports: { eyebrow: "Acompanhamento", title: "Relatórios" },
  intelligence: { eyebrow: "Inteligência · Beta", title: "Dailys e importações" },
  workflows: { eyebrow: "Administração", title: "Workflows" },
  categories: { eyebrow: "Administração", title: "Categorias e briefings" },
  users: { eyebrow: "Administração", title: "Usuários e acessos" },
  settings: { eyebrow: "Administração", title: "Configurações" },
  profile: { eyebrow: "Conta", title: "Meu perfil" },
};

function dateLabel(value: string | null): string {
  if (!value) return "Sem prazo";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
}

function AvatarView({ name, url, size = "normal" }: { name: string; url?: string | null; size?: "normal" | "large" }) {
  return <span className={`avatar avatar-${size}`}>{url ? <img src={url} alt="" /> : name.charAt(0).toUpperCase()}</span>;
}

function DemandCard({ demand, onOpen }: { demand: Demand; onOpen: () => void }) {
  return <button className="demand-card" onClick={onOpen}>
    <span className="card-top"><span className="demand-id">{demand.publicId}</span><span className={`priority priority-${demand.priority.toLowerCase()}`}>{priorityNames[demand.priority] ?? demand.priority}</span></span>
    <span className="card-company">{demand.companyColor && <i style={{ background: demand.companyColor }} />}{demand.companyName ?? "Sem empresa"}</span>
    <strong>{demand.title}</strong>
    <span className="card-description">{demand.description || "Sem descrição adicionada."}</span>
    <span className="card-meta"><span className={`demand-status ${demand.status.toLowerCase()}`}>{statusNames[demand.status] ?? demand.status}</span><span className={demand.deadlineAt && new Date(demand.deadlineAt) < new Date() ? "overdue" : ""}>◷ {dateLabel(demand.deadlineAt)}</span></span>
    <span className="card-footer"><span>{demand.categoryColor && <i style={{ background: demand.categoryColor }} />}{demand.categoryName ?? "Sem categoria"}</span><span>rev. {demand.revision}</span></span>
  </button>;
}

function WorkCard({ demand, canEdit, onOpen }: { demand: Demand; canEdit: boolean; onOpen: () => void }) {
  const overdue = Boolean(demand.deadlineAt && new Date(demand.deadlineAt) < new Date() && demand.status !== "COMPLETED");
  return <article className="work-card" draggable={canEdit} onDragStart={(event) => { event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", demand.id); }}>
    <button className="work-card-open" onClick={onOpen}>
      <span className="card-top"><span className="demand-id">{demand.publicId}</span><span className={`priority priority-${demand.priority.toLowerCase()}`}>{priorityNames[demand.priority] ?? demand.priority}</span></span>
      <span className="card-company">{demand.companyColor && <i style={{ background: demand.companyColor }} />}{demand.companyName ?? "Sem empresa"}</span>
      <strong>{demand.title}</strong>
      <span className="work-card-info"><span className={`demand-status ${demand.status.toLowerCase()}`}>{statusNames[demand.status] ?? demand.status}</span><span className={overdue ? "overdue" : ""}>◷ {dateLabel(demand.deadlineAt)}</span></span>
      <span className="work-card-footer"><span>{demand.assigneeName ? <><AvatarView name={demand.assigneeName} url={demand.assigneeAvatarUrl} />{demand.assigneeName}</> : "Sem responsável"}</span><span>{demand.categoryName ?? "Sem categoria"}</span></span>
    </button>
  </article>;
}

function WorkBoard({ demands, stages, people, companies, profile, mine, canEdit, onOpen, onMoveStage, onPreferenceChange, onCalendar }: {
  demands: Demand[];
  stages: WorkflowStage[];
  people: Person[];
  companies: Company[];
  profile: Profile | null;
  mine: boolean;
  canEdit: boolean;
  onOpen: (demand: Demand) => void;
  onMoveStage: (demand: Demand, stageId: string) => void;
  onPreferenceChange: (view: "kanban" | "list", showEmptyStages: boolean) => void;
  onCalendar: () => void;
}) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [company, setCompany] = useState("ALL");
  const [assignee, setAssignee] = useState("ALL");
  const [priority, setPriority] = useState("ALL");
  const preferences = profile?.preferences ?? { demandView: "kanban" as const, showEmptyStages: true, stageOrder: [] };
  const orderedStages = useMemo(() => {
    const order = new Map(preferences.stageOrder.map((id, index) => [id, index]));
    return [...stages].sort((a, b) => (order.get(a.id) ?? a.position + stages.length) - (order.get(b.id) ?? b.position + stages.length));
  }, [stages, preferences.stageOrder]);
  const visible = useMemo(() => demands.filter((demand) => {
    const needle = query.trim().toLocaleLowerCase("pt-BR");
    return (!mine || demand.assigneeId === profile?.profileId)
      && (status === "ALL" || demand.status === status)
      && (company === "ALL" || demand.primaryCompanyId === company)
      && (assignee === "ALL" || (assignee === "NONE" ? !demand.assigneeId : demand.assigneeId === assignee))
      && (priority === "ALL" || demand.priority === priority)
      && (!needle || `${demand.publicId} ${demand.title} ${demand.companyName ?? ""} ${demand.assigneeName ?? ""}`.toLocaleLowerCase("pt-BR").includes(needle));
  }), [demands, mine, profile?.profileId, status, company, assignee, priority, query]);
  const countFor = (stageId: string) => visible.filter((demand) => demand.stageId === stageId).length;
  const shownStages = orderedStages.filter((stage) => preferences.showEmptyStages || countFor(stage.id) > 0);
  function drop(event: React.DragEvent, stageId: string) {
    event.preventDefault();
    const id = event.dataTransfer.getData("text/plain");
    const demand = demands.find((item) => item.id === id);
    if (demand && demand.stageId !== stageId) onMoveStage(demand, stageId);
  }
  return <section className="work-control">
    <div className="work-filterbar">
      <label className="search-box"><span>⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar demanda, código, empresa ou pessoa" /></label>
      <label><span>Empresa</span><select value={company} onChange={(event) => setCompany(event.target.value)}><option value="ALL">Todas</option>{companies.map((item) => <option value={item.id} key={item.id}>{item.shortName}</option>)}</select></label>
      {!mine && <label><span>Responsável</span><select value={assignee} onChange={(event) => setAssignee(event.target.value)}><option value="ALL">Todos</option><option value="NONE">Sem responsável</option>{people.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>}
      <label><span>Situação</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">Todas</option>{Object.entries(statusNames).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label><span>Prioridade</span><select value={priority} onChange={(event) => setPriority(event.target.value)}><option value="ALL">Todas</option>{Object.entries(priorityNames).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
    </div>
    <div className="work-viewbar">
      <div><strong>{mine ? "Meu fluxo de trabalho" : "Controle de demandas"}</strong><span>{visible.length} {visible.length === 1 ? "demanda" : "demandas"}</span></div>
      <div className="view-switch" role="group" aria-label="Formato de visualização"><button className={preferences.demandView === "list" ? "active" : ""} onClick={() => onPreferenceChange("list", preferences.showEmptyStages)}>☷ Lista</button><button className={preferences.demandView === "kanban" ? "active" : ""} onClick={() => onPreferenceChange("kanban", preferences.showEmptyStages)}>▥ Kanban</button><button onClick={onCalendar}>□ Calendário</button></div>
      <label className="empty-toggle"><input type="checkbox" checked={preferences.showEmptyStages} onChange={(event) => onPreferenceChange(preferences.demandView, event.target.checked)} /> Exibir etapas vazias</label>
    </div>
    <div className="stage-strip" aria-label="Etapas do fluxo compartilhado">{orderedStages.map((stage) => <span key={stage.id}><i style={{ background: stage.color }} />{stage.name}<b>{countFor(stage.id)}</b></span>)}</div>
    {mine && <div className="scope-note"><strong>Visão individual</strong><span>Aqui aparecem somente as demandas atribuídas a você. As etapas e qualquer movimentação continuam iguais para toda a equipe.</span></div>}
    {visible.length === 0 ? <div className="empty-state"><span>⌕</span><h3>Nenhuma demanda encontrada</h3><p>Ajuste os filtros ou atribua uma demanda a este usuário.</p></div> : preferences.demandView === "kanban" ? <div className="kanban-board">{shownStages.map((stage) => {
      const items = visible.filter((demand) => demand.stageId === stage.id);
      return <section className="kanban-column" key={stage.id} onDragOver={(event) => { if (canEdit) { event.preventDefault(); event.dataTransfer.dropEffect = "move"; } }} onDrop={(event) => canEdit && drop(event, stage.id)}><header><span><i style={{ background: stage.color }} />{stage.name}</span><b>{items.length}</b></header><div>{items.map((demand) => <WorkCard key={demand.id} demand={demand} canEdit={canEdit} onOpen={() => onOpen(demand)} />)}{items.length === 0 && <p className="column-empty">Solte uma demanda nesta etapa</p>}</div></section>;
    })}</div> : <div className="grouped-list">{shownStages.map((stage) => {
      const items = visible.filter((demand) => demand.stageId === stage.id);
      return <section key={stage.id}><header><span><i style={{ background: stage.color }} />{stage.name}</span><b>{items.length}</b></header>{items.map((demand) => <button key={demand.id} onClick={() => onOpen(demand)}><span className="demand-id">{demand.publicId}</span><strong>{demand.title}</strong><span>{demand.companyName ?? "Sem empresa"}</span><span>{demand.assigneeName ?? "Sem responsável"}</span><span className={demand.deadlineAt && new Date(demand.deadlineAt) < new Date() ? "overdue" : ""}>{dateLabel(demand.deadlineAt)}</span><span className={`priority priority-${demand.priority.toLowerCase()}`}>{priorityNames[demand.priority]}</span></button>)}</section>;
    })}</div>}
  </section>;
}

function ManualDemandModal({ companies, categories, people, stages, onClose, onCreated }: { companies: Company[]; categories: Category[]; people: Person[]; stages: WorkflowStage[]; onClose: () => void; onCreated: (demand: Demand) => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget); const deadline = String(data.get("deadlineAt") || "");
    try {
      const created = await api<Demand>("/demands", { method: "POST", body: JSON.stringify({ title: data.get("title"), description: data.get("description") || null, companyId: data.get("companyId") || null, categoryId: data.get("categoryId") || null, assigneeId: data.get("assigneeId") || null, stageId: data.get("stageId") || null, priority: data.get("priority"), deadlineAt: deadline ? new Date(deadline).toISOString() : null }) });
      onCreated(created);
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <div className="modal-backdrop" role="presentation"><section className="form-modal" role="dialog" aria-modal="true" aria-labelledby="new-demand-title">
    <header className="modal-head"><div><span className="eyebrow dark">Criação manual</span><h2 id="new-demand-title">Nova demanda</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header>
    <form onSubmit={submit} className="modal-form">
      <p className="form-intro">Registre o trabalho no momento em que ele surgir. Os detalhes poderão ser complementados no card.</p>
      {error && <Notice>{error}</Notice>}
      <Field label="Título da demanda" name="title" maxLength={300} autoFocus placeholder="Ex.: Criar campanha de lançamento" required />
      <label className="field"><span>Descrição</span><textarea name="description" rows={4} maxLength={5000} placeholder="Contexto, objetivo e resultado esperado" /></label>
      <div className="form-grid"><label className="field"><span>Empresa</span><select name="companyId"><option value="">Sem empresa definida</option>{companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label><label className="field"><span>Categoria</span><select name="categoryId"><option value="">Sem categoria definida</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label></div>
      <div className="form-grid"><label className="field"><span>Responsável</span><select name="assigneeId"><option value="">Sem responsável</option>{people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label><label className="field"><span>Etapa inicial</span><select name="stageId" defaultValue={stages[0]?.id ?? ""}>{stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></label></div>
      <div className="form-grid"><label className="field"><span>Prioridade</span><select name="priority" defaultValue="NORMAL"><option value="LOW">Baixa</option><option value="NORMAL">Normal</option><option value="HIGH">Alta</option><option value="URGENT">Urgente</option></select></label><Field label="Prazo" name="deadlineAt" type="datetime-local" /></div>
      <footer className="form-actions"><button className="secondary compact" type="button" onClick={onClose}>Cancelar</button><button className="primary action-primary" disabled={busy}>{busy ? "Criando…" : "Criar demanda"}</button></footer>
    </form>
  </section></div>;
}

function CatalogModal({ kind, item, onClose, onSaved }: { kind: "company" | "category"; item?: Company | Category | null; onClose: () => void; onSaved: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const isCompany = kind === "company";
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); const data = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = { name: data.get("name"), code: data.get("code"), color: data.get("color") };
    if (isCompany) { payload.shortName = data.get("shortName"); payload.description = data.get("description") || null; }
    if (item) { payload.expectedRevision = item.revision; payload.active = item.active; }
    const base = isCompany ? "/catalogs/companies" : "/catalogs/categories";
    try { await api(item ? `${base}/${item.id}` : base, { method: item ? "PUT" : "POST", body: JSON.stringify(payload) }); await onSaved(); onClose(); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  const company = item && "shortName" in item ? item : null;
  return <div className="modal-backdrop"><section className="form-modal compact-modal" role="dialog" aria-modal="true"><header className="modal-head"><div><span className="eyebrow dark">{item ? "Editar cadastro" : "Novo cadastro"}</span><h2>{isCompany ? "Empresa" : "Categoria"}</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header><form className="modal-form" onSubmit={submit}>{error && <Notice>{error}</Notice>}<Field label="Nome" name="name" defaultValue={item?.name} required />{isCompany && <Field label="Nome curto" name="shortName" defaultValue={company?.shortName} required />}<Field label="Código" name="code" defaultValue={item?.code} placeholder="EXEMPLO" required /><label className="field color-field"><span>Cor de identificação</span><input name="color" type="color" defaultValue={item?.color ?? (isCompany ? "#155E75" : "#475569")} /></label>{isCompany && <label className="field"><span>Descrição</span><textarea name="description" rows={3} defaultValue={company?.description ?? ""} /></label>}<footer className="form-actions"><button className="secondary compact" type="button" onClick={onClose}>Cancelar</button><button className="primary action-primary" disabled={busy}>{busy ? "Salvando…" : "Salvar"}</button></footer></form></section></div>;
}

function WorkflowStageModal({ stage, nextPosition, onClose, onSaved }: { stage?: WorkflowStage | null; nextPosition: number; onClose: () => void; onSaved: () => Promise<void> }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); const data = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = { name: data.get("name"), code: data.get("code"), color: data.get("color"), position: stage?.position ?? nextPosition };
    if (stage) { payload.expectedRevision = stage.revision; payload.active = data.get("active") === "on"; }
    try { await api(stage ? `/catalogs/workflow-stages/${stage.id}` : "/catalogs/workflow-stages", { method: stage ? "PUT" : "POST", body: JSON.stringify(payload) }); await onSaved(); onClose(); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <div className="modal-backdrop"><section className="form-modal compact-modal" role="dialog" aria-modal="true" aria-labelledby="stage-modal-title"><header className="modal-head"><div><span className="eyebrow dark">Configuração do fluxo</span><h2 id="stage-modal-title">{stage ? "Editar etapa" : "Nova etapa"}</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header><form className="modal-form" onSubmit={submit}>{error && <Notice>{error}</Notice>}<p className="form-intro">O nome e a cor aparecem no Kanban, na lista e dentro de cada demanda.</p><Field label="Nome da etapa" name="name" defaultValue={stage?.name} placeholder="Ex.: Aprovação jurídica" required maxLength={120} /><Field label="Código interno" name="code" defaultValue={stage?.code} placeholder="APROVACAO_JURIDICA" required maxLength={50} /><label className="field color-field"><span>Cor da etapa</span><input name="color" type="color" defaultValue={stage?.color ?? "#475569"} /></label>{stage && <label className="check stage-active-check"><input name="active" type="checkbox" defaultChecked={stage.active} /><span>Etapa ativa e disponível para novas movimentações</span></label>}<footer className="form-actions"><button className="secondary compact" type="button" onClick={onClose}>Cancelar</button><button className="primary action-primary" disabled={busy}>{busy ? "Salvando…" : "Salvar etapa"}</button></footer></form></section></div>;
}

function WorkflowEditor({ stages, demands, onReload }: { stages: WorkflowStage[]; demands: Demand[]; onReload: () => Promise<void> }) {
  const [editing, setEditing] = useState<WorkflowStage | "new" | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const active = stages.filter((stage) => stage.active).sort((a, b) => a.position - b.position);
  const inactive = stages.filter((stage) => !stage.active).sort((a, b) => a.position - b.position);
  async function move(index: number, direction: -1 | 1) {
    const target = index + direction; if (target < 0 || target >= active.length) return;
    const ordered = [...active]; const sourceStage = ordered[index]; const targetStage = ordered[target];
    if (!sourceStage || !targetStage) return;
    ordered[index] = targetStage; ordered[target] = sourceStage;
    setBusy(true); setError("");
    try { await api("/catalogs/workflow-stages/order", { method: "PATCH", body: JSON.stringify({ stages: ordered.map((stage) => ({ id: stage.id, expectedRevision: stage.revision })) }) }); await onReload(); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  const maxPosition = stages.reduce((value, stage) => Math.max(value, stage.position), 0) + 1;
  return <><section className="panel page-panel"><div className="panel-head"><div><span className="eyebrow dark">Fluxo institucional</span><h3>Etapas compartilhadas da operação</h3></div><button className="small-button" onClick={() => setEditing("new")}>+ Nova etapa</button></div><div className="workflow-admin-intro"><strong>Um fluxo para toda a equipe</strong><p>Reordene as etapas abaixo. A mudança é aplicada ao Kanban, à lista e ao detalhe das demandas para todos os usuários.</p></div>{error && <div className="workflow-editor-error"><Notice>{error}</Notice></div>}<div className="workflow-admin-list editable">{active.map((stage, index) => <article key={stage.id}><span>{index + 1}</span><i style={{ background: stage.color }} /><div><strong>{stage.name}</strong><small>{stage.code}</small></div><b>{demands.filter((demand) => demand.stageId === stage.id).length} cards</b><div className="stage-row-actions"><button disabled={busy || index === 0} onClick={() => void move(index, -1)} aria-label={`Mover ${stage.name} para cima`}>↑</button><button disabled={busy || index === active.length - 1} onClick={() => void move(index, 1)} aria-label={`Mover ${stage.name} para baixo`}>↓</button><button onClick={() => setEditing(stage)}>Editar</button></div></article>)}</div>{inactive.length > 0 && <div className="inactive-stages"><span className="eyebrow dark">Etapas inativas</span>{inactive.map((stage) => <button key={stage.id} onClick={() => setEditing(stage)}><i style={{ background: stage.color }} /><span><strong>{stage.name}</strong><small>{stage.code}</small></span><b>Reativar ou editar</b></button>)}</div>}<div className="scope-note"><strong>Proteção operacional</strong><span>Uma etapa que contém demandas não pode ser desativada. Mova os cards antes de retirá-la do fluxo.</span></div></section>{editing && <WorkflowStageModal stage={editing === "new" ? null : editing} nextPosition={maxPosition} onClose={() => setEditing(null)} onSaved={onReload} />}</>;
}

function ProfilePage({ profile, session, onUpdated }: { profile: Profile | null; session: Session; onUpdated: (profile: Profile) => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [success, setSuccess] = useState("");
  if (!profile) return <section className="panel page-panel loading-block"><span className="loader" /></section>;
  const current = profile;
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess(""); const data = new FormData(event.currentTarget);
    try { const updated = await api<Profile>("/users/me", { method: "PUT", body: JSON.stringify({ name: data.get("name"), timezone: data.get("timezone"), expectedRevision: current.revision }) }); onUpdated(updated); setSuccess("Perfil atualizado."); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function upload(file: File) {
    setBusy(true); setError(""); setSuccess(""); const form = new FormData(); form.append("avatar", file);
    try { const updated = await api<Profile>("/users/me/avatar", { method: "POST", body: form }); onUpdated(updated); setSuccess("Foto atualizada."); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function removeAvatar() {
    setBusy(true); setError("");
    try { await api("/users/me/avatar", { method: "DELETE" }); onUpdated({ ...current, avatarUrl: null, revision: current.revision + 1 }); setSuccess("Foto removida."); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <div className="profile-layout"><section className="panel profile-card"><AvatarView name={profile.name} url={profile.avatarUrl} size="large" /><h3>{profile.name}</h3><p>{profile.email}</p><span>{session.role ? roleNames[session.role] : "Sem perfil"}</span><label className="small-button upload-avatar">Alterar foto<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void upload(file); }} /></label>{profile.avatarUrl && <button className="link-button" disabled={busy} onClick={() => void removeAvatar()}>Remover foto</button>}<small>JPG, PNG ou WebP, até 2 MB.</small></section><section className="panel profile-form"><div className="panel-head"><div><span className="eyebrow dark">Dados pessoais</span><h3>Informações do perfil</h3></div></div><form className="modal-form" onSubmit={save}>{error && <Notice>{error}</Notice>}{success && <Notice kind="success">{success}</Notice>}<Field label="Nome completo" name="name" defaultValue={profile.name} required /><Field label="E-mail" value={profile.email} disabled /><label className="field"><span>Fuso horário</span><select name="timezone" defaultValue={profile.timezone}><option value="America/Sao_Paulo">Brasília — São Paulo</option><option value="America/Manaus">Manaus</option><option value="America/Rio_Branco">Rio Branco</option></select></label><div className="profile-note"><strong>Perfil de acesso</strong><span>{session.role ? roleNames[session.role] : "Sem perfil"}</span><small>Alterações de permissão são feitas por um administrador.</small></div><footer className="form-actions"><button className="primary action-primary" disabled={busy}>{busy ? "Salvando…" : "Salvar alterações"}</button></footer></form></section></div>;
}

function DemandDetail({ demand, companies, categories, people, stages, canEdit, onBack, onSaved }: { demand: Demand; companies: Company[]; categories: Category[]; people: Person[]; stages: WorkflowStage[]; canEdit: boolean; onBack: () => void; onSaved: (demand: Demand) => void }) {
  const [tab, setTab] = useState("overview"); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [success, setSuccess] = useState("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess(""); const data = new FormData(event.currentTarget); const deadline = String(data.get("deadlineAt") || "");
    try { const updated = await api<Demand>(`/demands/${demand.id}`, { method: "PUT", body: JSON.stringify({ title: data.get("title"), description: data.get("description") || null, companyId: data.get("companyId") || null, categoryId: data.get("categoryId") || null, assigneeId: data.get("assigneeId") || null, stageId: data.get("stageId") || null, priority: data.get("priority"), status: data.get("status"), deadlineAt: deadline ? new Date(deadline).toISOString() : null, expectedRevision: demand.revision }) }); onSaved(updated); setSuccess("Demanda atualizada."); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function moveTo(stageId: string) {
    if (!canEdit || stageId === demand.stageId) return;
    setBusy(true); setError(""); setSuccess("");
    try { const updated = await api<Demand>(`/demands/${demand.id}/stage`, { method: "PATCH", body: JSON.stringify({ stageId, expectedRevision: demand.revision }) }); onSaved(updated); setSuccess(`Demanda movida para ${updated.stageName}.`); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  const tabs = [{ id: "overview", label: "Visão geral" }, { id: "briefing", label: "Briefing" }, { id: "workflow", label: "Workflow" }, { id: "conversations", label: "Conversas" }, { id: "files", label: "Arquivos" }, { id: "time", label: "Tempo" }, { id: "history", label: "Histórico" }];
  return <><button className="back-button" onClick={onBack}>← Voltar para demandas</button><section className="demand-detail-head"><div><span className="demand-id">{demand.publicId}</span><h2>{demand.title}</h2><p>{demand.companyName ?? "Sem empresa"} · {demand.categoryName ?? "Sem categoria"}</p></div><div className="detail-head-meta"><span className="stage-badge" style={{ borderColor: demand.stageColor ?? undefined }}><i style={{ background: demand.stageColor ?? "#94a3b8" }} />{demand.stageName ?? "Sem etapa"}</span><span className={`demand-status ${demand.status.toLowerCase()}`}>{statusNames[demand.status]}</span></div></section><nav className="detail-tabs" aria-label="Seções da demanda">{tabs.map((item) => <button className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)} key={item.id}>{item.label}{!(["overview", "workflow"].includes(item.id)) && <small>Em breve</small>}</button>)}</nav>{tab === "overview" ? <section className="panel detail-form"><form className="modal-form" onSubmit={save}>{error && <Notice>{error}</Notice>}{success && <Notice kind="success">{success}</Notice>}<div className="form-grid"><Field label="Título" name="title" defaultValue={demand.title} required /><label className="field"><span>Situação</span><select name="status" defaultValue={demand.status}>{Object.entries(statusNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div><label className="field"><span>Descrição</span><textarea name="description" rows={6} defaultValue={demand.description ?? ""} /></label><div className="form-grid"><label className="field"><span>Empresa</span><select name="companyId" defaultValue={demand.primaryCompanyId ?? ""}><option value="">Sem empresa</option>{companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="field"><span>Categoria</span><select name="categoryId" defaultValue={demand.categoryId ?? ""}><option value="">Sem categoria</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div><div className="form-grid"><label className="field"><span>Responsável</span><select name="assigneeId" defaultValue={demand.assigneeId ?? ""}><option value="">Sem responsável</option>{people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label><label className="field"><span>Etapa do workflow</span><select name="stageId" defaultValue={demand.stageId ?? ""}>{stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></label></div><div className="form-grid"><label className="field"><span>Prioridade</span><select name="priority" defaultValue={demand.priority}>{Object.entries(priorityNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><Field label="Prazo" name="deadlineAt" type="datetime-local" defaultValue={demand.deadlineAt ? demand.deadlineAt.slice(0, 16) : ""} /></div><footer className="form-actions"><span className="revision-note">Última revisão: {demand.revision}</span><button className="primary action-primary" disabled={busy || !canEdit}>{busy ? "Salvando…" : "Salvar demanda"}</button></footer></form></section> : tab === "workflow" ? <section className="panel workflow-detail"><div><span className="eyebrow dark">Fluxo compartilhado</span><h3>Alterar etapa da demanda</h3><p>A mudança fica visível para toda a equipe e também atualiza o Kanban.</p></div>{error && <Notice>{error}</Notice>}{success && <Notice kind="success">{success}</Notice>}<div className="workflow-stage-list">{stages.map((stage, index) => <button key={stage.id} className={demand.stageId === stage.id ? "active" : ""} disabled={busy || !canEdit} onClick={() => void moveTo(stage.id)}><span>{index + 1}</span><i style={{ background: stage.color }} /><strong>{stage.name}</strong>{demand.stageId === stage.id && <b>Etapa atual</b>}</button>)}</div></section> : <section className="panel feature-preview"><span>◫</span><h3>{tabs.find((item) => item.id === tab)?.label}</h3><p>Esta seção já faz parte da arquitetura do card e será habilitada nas próximas entregas.</p></section>}</>;
}

function ComingSection({ icon, title, text, items }: { icon: string; title: string; text: string; items: string[] }) {
  return <section className="panel coming-section"><span>{icon}</span><div><h3>{title}</h3><p>{text}</p><ul>{items.map((item) => <li key={item}>✓ {item}</li>)}</ul></div></section>;
}

function Dashboard({ session, logout, onSession }: { session: Session; logout: () => void; onSession: (session: Session) => void }) {
  const validPages = Object.keys(pageTitles) as WorkspacePage[];
  const hashPage = window.location.hash.replace(/^#\/?/, "").split("/")[0] as WorkspacePage;
  const [page, setPage] = useState<WorkspacePage>(validPages.includes(hashPage) ? hashPage : "overview");
  const [companies, setCompanies] = useState<Company[]>([]); const [categories, setCategories] = useState<Category[]>([]); const [stages, setStages] = useState<WorkflowStage[]>([]); const [workflowStages, setWorkflowStages] = useState<WorkflowStage[]>([]); const [people, setPeople] = useState<Person[]>([]); const [users, setUsers] = useState<User[]>([]); const [demands, setDemands] = useState<Demand[]>([]); const [imports, setImports] = useState<DailyImport[]>([]); const [profile, setProfile] = useState<Profile | null>(null); const [error, setError] = useState(""); const [showImport, setShowImport] = useState(false); const [showCreate, setShowCreate] = useState(false); const [resumeImport, setResumeImport] = useState<DailyImport | null>(null); const [catalogModal, setCatalogModal] = useState<{ kind: "company" | "category"; item?: Company | Category | null } | null>(null); const [selectedDemand, setSelectedDemand] = useState<Demand | null>(null); const [approvalRoles, setApprovalRoles] = useState<Record<string, string>>({}); const [approvingUser, setApprovingUser] = useState("");
  const canManage = session.role === "admin" || session.role === "coordinator"; const canCreate = session.role !== "viewer";
  function go(next: WorkspacePage) { setPage(next); setSelectedDemand(null); window.location.hash = next; window.scrollTo({ top: 0 }); }
  function loadData() {
    setError("");
    return Promise.all([api<Company[]>("/catalogs/companies"), api<Category[]>("/catalogs/categories"), api<WorkflowStage[]>("/catalogs/workflow-stages"), canManage ? api<WorkflowStage[]>("/catalogs/workflow-stages?includeInactive=true") : Promise.resolve([] as WorkflowStage[]), api<Person[]>("/users/options"), api<Demand[]>("/demands"), api<Profile>("/users/me"), canManage ? api<User[]>("/users") : Promise.resolve([]), canManage ? api<DailyImport[]>("/imports/dailys") : Promise.resolve([])]).then(([c, k, s, w, o, d, p, u, i]) => { setCompanies(c); setCategories(k); setStages(s); setWorkflowStages(w); setPeople(o); setDemands(d); setProfile(p); setUsers(u); setImports(i); }).catch((caught) => setError(messageFrom(caught)));
  }
  useEffect(() => { void loadData(); }, [session.role]);
  useEffect(() => { const listener = () => { const value = window.location.hash.replace(/^#\/?/, "").split("/")[0] as WorkspacePage; if (validPages.includes(value)) { setPage(value); setSelectedDemand(null); } }; window.addEventListener("hashchange", listener); return () => window.removeEventListener("hashchange", listener); }, []);
  async function approveUser(user: User) { setApprovingUser(user.id); setError(""); try { await api(`/users/${user.id}/approve`, { method: "POST", body: JSON.stringify({ role: approvalRoles[user.id] ?? "collaborator", expectedRevision: user.revision }) }); await loadData(); } catch (caught) { setError(messageFrom(caught)); } finally { setApprovingUser(""); } }
  async function savePreferences(demandView: "kanban" | "list", showEmptyStages: boolean) {
    if (!profile) return;
    const preferences = { ...profile.preferences, demandView, showEmptyStages };
    setProfile({ ...profile, preferences });
    try { const updated = await api<Profile>("/users/me/preferences", { method: "PUT", body: JSON.stringify(preferences) }); setProfile(updated); }
    catch (caught) { setError(messageFrom(caught)); setProfile(profile); }
  }
  async function moveDemand(demand: Demand, stageId: string) {
    setError("");
    try { const updated = await api<Demand>(`/demands/${demand.id}/stage`, { method: "PATCH", body: JSON.stringify({ stageId, expectedRevision: demand.revision }) }); setDemands((items) => items.map((item) => item.id === updated.id ? updated : item)); if (selectedDemand?.id === updated.id) setSelectedDemand(updated); }
    catch (caught) { setError(messageFrom(caught)); }
  }
  const pending = useMemo(() => users.filter((user) => user.state === "pending_approval"), [users]);
  const currentTitle = selectedDemand ? { eyebrow: "Demanda", title: selectedDemand.publicId } : pageTitles[page];
  const navigation: { label: string; links: { id: WorkspacePage; icon: string; label: string; badge?: number; beta?: boolean }[] }[] = [
    { label: "Trabalho", links: [{ id: "overview", icon: "⌂", label: "Início" }, { id: "my-work", icon: "◎", label: "Meu trabalho" }, { id: "demands", icon: "▤", label: "Demandas" }, { id: "calendar", icon: "□", label: "Calendário" }] },
    { label: "Organização", links: [{ id: "companies", icon: "▦", label: "Empresas" }, { id: "team", icon: "○", label: "Equipe" }, { id: "reports", icon: "↗", label: "Relatórios" }] },
    { label: "Inteligência", links: [{ id: "intelligence", icon: "◇", label: "Dailys", badge: imports.filter((item) => item.state === "reviewing").length, beta: true }] },
    ...(canManage ? [{ label: "Administração", links: [{ id: "workflows" as WorkspacePage, icon: "⇄", label: "Workflows" }, { id: "categories" as WorkspacePage, icon: "◆", label: "Categorias" }, { id: "users" as WorkspacePage, icon: "◉", label: "Acessos", badge: pending.length }, { id: "settings" as WorkspacePage, icon: "⚙", label: "Configurações" }] }] : []),
  ];
  let content: React.ReactNode;
  if (selectedDemand) content = <DemandDetail demand={selectedDemand} companies={companies} categories={categories} people={people} stages={stages} canEdit={canCreate} onBack={() => { setSelectedDemand(null); go("demands"); }} onSaved={(updated) => { setSelectedDemand(updated); setDemands((items) => items.map((item) => item.id === updated.id ? updated : item)); }} />;
  else if (page === "overview") content = <><section className="welcome"><div><p className="kicker">Fluxo centralizado</p><h2>Olá, {session.name.split(" ")[0]}.</h2><p>Crie, acompanhe e atualize as demandas da operação em um espaço compartilhado por toda a equipe.</p>{canCreate && <button className="welcome-action" onClick={() => setShowCreate(true)}>+ Criar primeira demanda</button>}</div><div className="pulse"><span>{String(demands.length).padStart(2, "0")}</span><small>cards ativos</small></div></section><section className="stats"><article><span>Demandas abertas</span><strong>{demands.filter((item) => item.status !== "COMPLETED").length}</strong><small>em acompanhamento</small></article><article><span>Em andamento</span><strong>{demands.filter((item) => item.status === "IN_PROGRESS").length}</strong><small>na operação</small></article><article><span>Com prazo</span><strong>{demands.filter((item) => item.deadlineAt).length}</strong><small>planejadas</small></article><article><span>Acessos pendentes</span><strong>{pending.length}</strong><small>aguardando liberação</small></article></section><section className="panel full"><div className="panel-head"><div><span className="eyebrow dark">Últimas movimentações</span><h3>Demandas recentes</h3></div><button className="small-button" onClick={() => go("demands")}>Ver todas</button></div>{demands.length ? <div className="demand-grid">{demands.slice(0, 6).map((demand) => <DemandCard key={demand.id} demand={demand} onOpen={() => setSelectedDemand(demand)} />)}</div> : <div className="empty-state"><span>▤</span><h3>Comece pela primeira demanda</h3><p>Cadastre manualmente o trabalho que precisa ser acompanhado.</p>{canCreate && <button className="primary compact" onClick={() => setShowCreate(true)}>+ Nova demanda</button>}</div>}</section></>;
  else if (page === "demands" || page === "my-work") content = <WorkBoard demands={demands} stages={stages} people={people} companies={companies} profile={profile} mine={page === "my-work"} canEdit={canCreate} onOpen={setSelectedDemand} onMoveStage={(demand, stageId) => void moveDemand(demand, stageId)} onPreferenceChange={(view, showEmpty) => void savePreferences(view, showEmpty)} onCalendar={() => go("calendar")} />;
  else if (page === "calendar") { const scheduled = demands.filter((item) => item.deadlineAt).sort((a, b) => String(a.deadlineAt).localeCompare(String(b.deadlineAt))); content = <section className="panel page-panel"><div className="calendar-head"><strong>Próximos prazos</strong><span>{scheduled.length} demandas planejadas</span></div>{scheduled.length ? <div className="timeline-list">{scheduled.map((demand) => <button key={demand.id} onClick={() => setSelectedDemand(demand)}><time>{dateLabel(demand.deadlineAt)}</time><i style={{ background: demand.companyColor ?? "#94a3b8" }} /><span><strong>{demand.title}</strong><small>{demand.companyName ?? "Sem empresa"} · {statusNames[demand.status]}</small></span><b>{priorityNames[demand.priority]}</b></button>)}</div> : <div className="empty-state"><span>□</span><h3>Nenhum prazo cadastrado</h3><p>Defina prazos nos cards para montar a agenda da operação.</p></div>}</section>; }
  else if (page === "companies") content = <section className="panel page-panel"><div className="panel-head"><div><span className="eyebrow dark">Cadastros ativos</span><h3>Empresas atendidas</h3></div>{canManage && <button className="small-button" onClick={() => setCatalogModal({ kind: "company" })}>+ Nova empresa</button>}</div>{companies.length ? <div className="entity-cards">{companies.map((company) => <article key={company.id}><i style={{ background: company.color }} /><div><strong>{company.name}</strong><span>{company.shortName} · {company.code}</span><p>{company.description || "Sem descrição cadastrada."}</p></div>{canManage && <button className="table-action" onClick={() => setCatalogModal({ kind: "company", item: company })}>Editar</button>}</article>)}</div> : <div className="empty-state"><span>▦</span><h3>Nenhuma empresa cadastrada</h3></div>}</section>;
  else if (page === "team") content = <><ComingSection icon="○" title="Diretório da equipe" text="A estrutura visual está preparada para cargos, capacidade e distribuição de trabalho." items={["Perfil e foto individual", "Cargo e papel de acesso", "Capacidade por período"]} />{canManage && users.length > 0 && <section className="panel full"><div className="panel-head"><div><span className="eyebrow dark">Pessoas cadastradas</span><h3>Equipe atual</h3></div><span className="count">{users.length}</span></div><div className="table-wrap"><table><thead><tr><th>Nome</th><th>E-mail</th><th>Situação</th><th>Perfil</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td>{user.name}</td><td>{user.email}</td><td><span className={`state ${user.state}`}>{user.state === "active" ? "Ativo" : user.state === "suspended" ? "Suspenso" : "Pendente"}</span></td><td>{user.role ? roleNames[user.role] : "A definir"}</td></tr>)}</tbody></table></div></section>}</>;
  else if (page === "reports") content = <><section className="stats"><article><span>Total de demandas</span><strong>{demands.length}</strong><small>registradas</small></article><article><span>Concluídas</span><strong>{demands.filter((item) => item.status === "COMPLETED").length}</strong><small>no período</small></article><article><span>Bloqueadas</span><strong>{demands.filter((item) => item.status === "BLOCKED").length}</strong><small>pedem atenção</small></article><article><span>Urgentes</span><strong>{demands.filter((item) => item.priority === "URGENT").length}</strong><small>prioridade máxima</small></article></section><ComingSection icon="↗" title="Relatórios operacionais" text="Os indicadores iniciais já usam os dados reais das demandas." items={["Volume por empresa e categoria", "Cumprimento de prazos", "Capacidade e tempo apontado"]} /></>;
  else if (page === "intelligence") content = <section className="panel page-panel"><div className="intelligence-hero"><div><span className="beta-chip">Beta</span><h3>Importação assistida de Dailys</h3><p>Envie um JSON analisado e escolha, item por item, qual card receberá a informação. Nenhuma alteração é aplicada sem sua revisão.</p></div>{canManage && <button className="primary action-primary" onClick={() => { setResumeImport(null); setShowImport(true); }}>Importar JSON</button>}</div>{imports.length ? <div className="table-wrap"><table><thead><tr><th>Relatório</th><th>Progresso</th><th>Situação</th><th>Ação</th></tr></thead><tbody>{imports.map((item) => <tr key={item.id}><td><strong>{item.sourceLabel}</strong><small className="table-subtitle">{item.filename}</small></td><td>{item.reviewedItems} de {item.totalItems}</td><td><span className={`import-state ${item.state}`}>{item.state === "applied" ? "Aplicada" : "Em revisão"}</span></td><td>{item.state === "reviewing" ? <button className="table-action" onClick={() => { setResumeImport(item); setShowImport(true); }}>Continuar revisão</button> : "Concluída"}</td></tr>)}</tbody></table></div> : <div className="empty-state"><span>◇</span><h3>Nenhuma importação realizada</h3><p>Este recurso complementa o trabalho manual quando houver um relatório estruturado.</p></div>}</section>;
  else if (page === "categories") content = <section className="panel page-panel"><div className="panel-head"><div><span className="eyebrow dark">Estrutura de entrada</span><h3>Categorias de demanda</h3></div><button className="small-button" onClick={() => setCatalogModal({ kind: "category" })}>+ Nova categoria</button></div><div className="category-table">{categories.map((category) => <button key={category.id} onClick={() => setCatalogModal({ kind: "category", item: category })}><i style={{ background: category.color }} /><span><strong>{category.name}</strong><small>{category.code}</small></span><b>Editar</b></button>)}</div><div className="scope-note"><strong>Próxima evolução</strong><span>Cada categoria terá seu próprio briefing com campos obrigatórios e workflow associado.</span></div></section>;
  else if (page === "users") content = <section className="panel page-panel"><div className="panel-head"><div><span className="eyebrow dark">Controle de acesso</span><h3>Usuários</h3></div><span className="count">{users.length}</span></div>{users.length ? <div className="table-wrap"><table><thead><tr><th>Nome</th><th>E-mail</th><th>Situação</th><th>Perfil</th><th>Ação</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td>{user.name}</td><td>{user.email}</td><td><span className={`state ${user.state}`}>{user.state === "active" ? "Ativo" : user.state === "suspended" ? "Suspenso" : "Pendente"}</span></td><td>{user.state === "pending_approval" && session.role === "admin" ? <select className="role-select" value={approvalRoles[user.id] ?? "collaborator"} onChange={(event) => setApprovalRoles((values) => ({ ...values, [user.id]: event.target.value }))}><option value="collaborator">Colaborador</option><option value="coordinator">Coordenador</option><option value="viewer">Visualizador</option><option value="admin">Administrador</option></select> : user.role ? roleNames[user.role] : "Definir"}</td><td>{user.state === "pending_approval" && session.role === "admin" ? <button className="table-action" disabled={approvingUser === user.id} onClick={() => void approveUser(user)}>{approvingUser === user.id ? "Liberando…" : "Liberar acesso"}</button> : "—"}</td></tr>)}</tbody></table></div> : <div className="empty-state"><p>Nenhum usuário cadastrado.</p></div>}</section>;
  else if (page === "profile") content = <ProfilePage profile={profile} session={session} onUpdated={(updated) => { setProfile(updated); onSession({ ...session, name: updated.name }); }} />;
  else if (page === "workflows") content = <WorkflowEditor stages={workflowStages} demands={demands} onReload={loadData} />;
  else content = <ComingSection icon="⚙" title="Configurações da organização" text="Preferências gerais, notificações e dados institucionais serão concentrados aqui." items={["Preferências de notificação", "Política de privacidade e LGPD", "Parâmetros da organização"]} />;
  return <div className="app-shell"><aside className="sidebar"><Brand /><nav aria-label="Navegação principal">{navigation.map((group) => <div className="nav-group" key={group.label}><small>{group.label}</small>{group.links.map((link) => <button key={link.id} className={!selectedDemand && page === link.id ? "active" : ""} onClick={() => go(link.id)}><span>{link.icon}</span>{link.label}{link.beta && <em>Beta</em>}{Boolean(link.badge) && <b>{link.badge}</b>}</button>)}</div>)}</nav><div className="side-profile"><button className="profile-trigger" onClick={() => go("profile")}><AvatarView name={profile?.name ?? session.name} url={profile?.avatarUrl} /><span><strong>{profile?.name ?? session.name}</strong><small>{session.role ? roleNames[session.role] : "Sem perfil"}</small></span></button><button className="logout-button" onClick={logout} aria-label="Sair">↗</button></div></aside><main className="workspace"><header><div><span className="eyebrow dark">{currentTitle.eyebrow}</span><h1>{currentTitle.title}</h1></div>{canCreate && !selectedDemand && <button className="new-demand-button" onClick={() => setShowCreate(true)}><span>+</span> Nova demanda</button>}</header>{error && <Notice>{error}</Notice>}{content}</main>{showCreate && <ManualDemandModal companies={companies} categories={categories} people={people} stages={stages} onClose={() => setShowCreate(false)} onCreated={(created) => { setDemands((items) => [created, ...items]); setShowCreate(false); setSelectedDemand(created); setPage("demands"); window.location.hash = "demands"; }} />}{catalogModal && <CatalogModal kind={catalogModal.kind} item={catalogModal.item} onClose={() => setCatalogModal(null)} onSaved={loadData} />}{showImport && <DailyImportModal demands={demands} initialImport={resumeImport} onClose={() => { setShowImport(false); setResumeImport(null); void loadData(); }} onApplied={() => { void loadData(); }} />}</div>;
}

export default function App() {
  const [page, setPage] = useState<Page>("login"); const [session, setSession] = useState<Session | null>(null); const [loading, setLoading] = useState(true); const [email, setEmail] = useState(""); const [recoveryToken, setRecoveryToken] = useState("");
  useEffect(() => { api<Session>("/auth/session").then(setSession).catch(() => undefined).finally(() => setLoading(false)); }, []);
  async function logout() { try { await api("/auth/logout", { method: "POST" }); } finally { setSession(null); setPage("login"); } }
  if (loading) return <main className="loading-page"><Brand /><span className="loader" aria-label="Carregando" /></main>;
  if (session?.state === "pending_approval") return <Pending session={session} logout={logout} />;
  if (session?.state === "suspended") return <main className="waiting-page"><div className="waiting-card"><Brand /><h1>Acesso suspenso</h1><p>Fale com um administrador da plataforma para revisar seu acesso.</p><button className="secondary" onClick={logout}>Sair</button></div></main>;
  if (session?.state === "active") return <Dashboard session={session} logout={logout} onSession={setSession} />;
  if (page === "register") return <Register go={setPage} continueWith={(value) => { setEmail(value); setPage("verify-signup"); }} />;
  if (page === "verify-signup") return <Verify email={email} purpose="signup" go={setPage} onSignup={setSession} onRecovery={() => undefined} />;
  if (page === "forgot") return <Forgot go={setPage} continueWith={(value) => { setEmail(value); setPage("verify-recovery"); }} />;
  if (page === "verify-recovery") return <Verify email={email} purpose="recovery" go={setPage} onSignup={() => undefined} onRecovery={(token) => { setRecoveryToken(token); setPage("reset"); }} />;
  if (page === "reset") return <Reset recoveryToken={recoveryToken} go={setPage} />;
  return <Login onSession={setSession} go={setPage} />;
}
