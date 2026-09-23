import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, messageFrom, type Session } from "./api";

type Page = "login" | "register" | "verify-signup" | "forgot" | "verify-recovery" | "reset";
type Company = { id: string; name: string; shortName: string; code: string; color: string; active: boolean; revision: number };
type Category = { id: string; name: string; code: string; color: string; active: boolean; revision: number };
type User = { id: string; name: string; email: string; state: string; role: string | null; revision: number };
type Demand = {
  id: string;
  publicId: string;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  deadlineAt: string | null;
  forecastAt: string | null;
  revision: number;
  createdAt: string;
};
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
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const result = await api<Session | { recoveryToken: string }>("/auth/verify-email", { method: "POST", body: JSON.stringify({ email, code: data.get("code"), purpose }) });
      if ("recoveryToken" in result) onRecovery(result.recoveryToken); else onSignup(result);
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <AuthShell eyebrow="Confirmação" title="Digite o código" text={`Enviamos um código numérico para ${email}. Ele expira em poucos minutos.`}>
    <form onSubmit={submit} className="form-stack">
      {error && <Notice>{error}</Notice>}
      <Field label="Código de 6 a 8 números" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6,8}" minLength={6} maxLength={8} className="code-input" required />
      <button className="primary" disabled={busy}>{busy ? "Confirmando…" : "Confirmar código"}</button>
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

function Dashboard({ session, logout }: { session: Session; logout: () => void }) {
  const [companies, setCompanies] = useState<Company[]>([]); const [categories, setCategories] = useState<Category[]>([]); const [users, setUsers] = useState<User[]>([]); const [demands, setDemands] = useState<Demand[]>([]); const [imports, setImports] = useState<DailyImport[]>([]); const [error, setError] = useState(""); const [showImport, setShowImport] = useState(false); const [resumeImport, setResumeImport] = useState<DailyImport | null>(null); const [approvalRoles, setApprovalRoles] = useState<Record<string, string>>({}); const [approvingUser, setApprovingUser] = useState("");
  const canImport = session.role === "admin" || session.role === "coordinator";
  function loadData() {
    setError("");
    return Promise.all([
      api<Company[]>("/catalogs/companies"),
      api<Category[]>("/catalogs/categories"),
      api<Demand[]>("/demands"),
      canImport ? api<User[]>("/users") : Promise.resolve([]),
      canImport ? api<DailyImport[]>("/imports/dailys") : Promise.resolve([]),
    ]).then(([c, k, d, u, i]) => { setCompanies(c); setCategories(k); setDemands(d); setUsers(u); setImports(i); }).catch((caught) => setError(messageFrom(caught)));
  }
  useEffect(() => { void loadData(); }, [session.role]);
  async function approveUser(user: User) {
    setApprovingUser(user.id); setError("");
    try {
      await api(`/users/${user.id}/approve`, { method: "POST", body: JSON.stringify({ role: approvalRoles[user.id] ?? "collaborator", expectedRevision: user.revision }) });
      await loadData();
    } catch (caught) { setError(messageFrom(caught)); } finally { setApprovingUser(""); }
  }
  const pending = useMemo(() => users.filter((user) => user.state === "pending_approval"), [users]);
  return <div className="app-shell">
    <aside className="sidebar"><Brand /><nav aria-label="Navegação principal"><a className="active" href="#overview"><span>⌂</span>Visão geral</a><a href="#demands"><span>▤</span>Demandas</a>{canImport && <a href="#imports"><span>⇄</span>Importações{imports.some((item) => item.state === "reviewing") && <b>{imports.filter((item) => item.state === "reviewing").length}</b>}</a>}<a href="#companies"><span>▦</span>Empresas</a><a href="#categories"><span>◇</span>Categorias</a>{canImport && <a href="#users"><span>○</span>Usuários{pending.length > 0 && <b>{pending.length}</b>}</a>}</nav><div className="side-profile"><span className="avatar">{session.name.charAt(0).toUpperCase()}</span><span><strong>{session.name}</strong><small>{session.role ? roleNames[session.role] : "Sem perfil"}</small></span><button onClick={logout} aria-label="Sair">↗</button></div></aside>
    <main className="workspace" id="overview"><header><div><span className="eyebrow dark">Operação compartilhada</span><h1>Visão geral</h1></div>{canImport ? <button className="import-button" onClick={() => { setResumeImport(null); setShowImport(true); }}><span>⇧</span>Importar Daily</button> : <div className="phase"><span>MVP</span><strong>Operação segura</strong></div>}</header>
      {error && <Notice>{error}</Notice>}
      <section className="welcome"><div><p className="kicker">Fluxo centralizado</p><h2>Boa jornada, {session.name.split(" ")[0]}.</h2><p>Revise Dailys, associe cada informação ao card correto e mantenha o histórico visível para toda a equipe.</p></div><div className="pulse"><span>{String(demands.length).padStart(2, "0")}</span><small>cards ativos</small></div></section>
      <section className="stats"><article><span>Demandas</span><strong>{demands.length}</strong><small>cards ativos</small></article><article><span>Empresas</span><strong>{companies.length}</strong><small>cadastros ativos</small></article><article><span>Categorias</span><strong>{categories.length}</strong><small>tipos de demanda</small></article><article><span>Acessos pendentes</span><strong>{pending.length}</strong><small>aguardando liberação</small></article></section>
      <section className="panel full" id="demands"><div className="panel-head"><div><span className="eyebrow dark">Operação</span><h3>Demandas recentes</h3></div><span className="count">{demands.length}</span></div>{demands.length ? <div className="demand-grid">{demands.map((demand) => <article key={demand.id}><div><span className="demand-id">{demand.publicId}</span><span className={`demand-status ${demand.status.toLowerCase()}`}>{statusNames[demand.status] ?? demand.status}</span></div><h4>{demand.title}</h4><p>{demand.description || "Sem descrição adicionada."}</p><footer><span>Prioridade {demand.priority.toLocaleLowerCase("pt-BR")}</span><span>rev. {demand.revision}</span></footer></article>)}</div> : <div className="empty demand-empty"><span>▤</span><p>Nenhum card criado. Uma importação pode criar o primeiro.</p>{canImport && <button className="small-button" onClick={() => setShowImport(true)}>Importar Daily</button>}</div>}</section>
      {canImport && <section className="panel full" id="imports"><div className="panel-head"><div><span className="eyebrow dark">Revisão manual</span><h3>Importações de Dailys</h3></div><button className="small-button" onClick={() => { setResumeImport(null); setShowImport(true); }}>Nova importação</button></div>{imports.length ? <div className="table-wrap"><table><thead><tr><th>Relatório</th><th>Itens revisados</th><th>Situação</th><th>Ação</th></tr></thead><tbody>{imports.map((item) => <tr key={item.id}><td><strong>{item.sourceLabel}</strong><small className="table-subtitle">{item.filename}</small></td><td>{item.reviewedItems} de {item.totalItems}</td><td><span className={`import-state ${item.state}`}>{item.state === "applied" ? "Aplicada" : "Em revisão"}</span></td><td>{item.state === "reviewing" ? <button className="table-action" onClick={() => { setResumeImport(item); setShowImport(true); }}>Continuar revisão</button> : "Concluída"}</td></tr>)}</tbody></table></div> : <div className="empty"><p>Nenhuma Daily enviada.</p></div>}</section>}
      <section className="dashboard-grid"><article className="panel" id="companies"><div className="panel-head"><div><span className="eyebrow dark">Estrutura</span><h3>Empresas</h3></div><span className="count">{companies.length}</span></div>{companies.length ? <ul className="entity-list">{companies.slice(0, 5).map((company) => <li key={company.id}><i style={{ background: company.color }} /><span><strong>{company.name}</strong><small>{company.code}</small></span><b>Ativa</b></li>)}</ul> : <div className="empty"><span>▦</span><p>Nenhuma empresa cadastrada.</p></div>}</article>
        <article className="panel" id="categories"><div className="panel-head"><div><span className="eyebrow dark">Catálogo</span><h3>Categorias iniciais</h3></div><span className="count">{categories.length}</span></div><div className="tag-list">{categories.map((category) => <span key={category.id}><i style={{ background: category.color }} />{category.name}</span>)}</div></article></section>
      {canImport && <section className="panel full" id="users"><div className="panel-head"><div><span className="eyebrow dark">Equipe</span><h3>Usuários</h3></div><span className="count">{users.length}</span></div>{users.length ? <div className="table-wrap"><table><thead><tr><th>Nome</th><th>E-mail</th><th>Situação</th><th>Perfil</th>{session.role === "admin" && <th>Ação</th>}</tr></thead><tbody>{users.map((user) => <tr key={user.id}><td>{user.name}</td><td>{user.email}</td><td><span className={`state ${user.state}`}>{user.state === "active" ? "Ativo" : user.state === "suspended" ? "Suspenso" : "Pendente"}</span></td><td>{user.state === "pending_approval" && session.role === "admin" ? <select className="role-select" value={approvalRoles[user.id] ?? "collaborator"} onChange={(event) => setApprovalRoles((values) => ({ ...values, [user.id]: event.target.value }))}><option value="collaborator">Colaborador</option><option value="coordinator">Coordenador</option><option value="viewer">Visualizador</option><option value="admin">Administrador</option></select> : user.role ? roleNames[user.role] : "Definir"}</td>{session.role === "admin" && <td>{user.state === "pending_approval" ? <button className="table-action" disabled={approvingUser === user.id} onClick={() => void approveUser(user)}>{approvingUser === user.id ? "Liberando…" : "Liberar acesso"}</button> : "—"}</td>}</tr>)}</tbody></table></div> : <div className="empty"><p>Nenhum usuário cadastrado.</p></div>}</section>}
    </main>
    {showImport && <DailyImportModal demands={demands} initialImport={resumeImport} onClose={() => { setShowImport(false); setResumeImport(null); void loadData(); }} onApplied={() => { void loadData(); }} />}
  </div>;
}

export default function App() {
  const [page, setPage] = useState<Page>("login"); const [session, setSession] = useState<Session | null>(null); const [loading, setLoading] = useState(true); const [email, setEmail] = useState(""); const [recoveryToken, setRecoveryToken] = useState("");
  useEffect(() => { api<Session>("/auth/session").then(setSession).catch(() => undefined).finally(() => setLoading(false)); }, []);
  async function logout() { try { await api("/auth/logout", { method: "POST" }); } finally { setSession(null); setPage("login"); } }
  if (loading) return <main className="loading-page"><Brand /><span className="loader" aria-label="Carregando" /></main>;
  if (session?.state === "pending_approval") return <Pending session={session} logout={logout} />;
  if (session?.state === "suspended") return <main className="waiting-page"><div className="waiting-card"><Brand /><h1>Acesso suspenso</h1><p>Fale com um administrador da plataforma para revisar seu acesso.</p><button className="secondary" onClick={logout}>Sair</button></div></main>;
  if (session?.state === "active") return <Dashboard session={session} logout={logout} />;
  if (page === "register") return <Register go={setPage} continueWith={(value) => { setEmail(value); setPage("verify-signup"); }} />;
  if (page === "verify-signup") return <Verify email={email} purpose="signup" go={setPage} onSignup={setSession} onRecovery={() => undefined} />;
  if (page === "forgot") return <Forgot go={setPage} continueWith={(value) => { setEmail(value); setPage("verify-recovery"); }} />;
  if (page === "verify-recovery") return <Verify email={email} purpose="recovery" go={setPage} onSignup={() => undefined} onRecovery={(token) => { setRecoveryToken(token); setPage("reset"); }} />;
  if (page === "reset") return <Reset recoveryToken={recoveryToken} go={setPage} />;
  return <Login onSession={setSession} go={setPage} />;
}
