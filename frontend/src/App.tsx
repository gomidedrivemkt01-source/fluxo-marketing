import { lazy, Suspense, type FormEvent, useEffect, useState } from "react";
import type React from "react";
import { api, AUTH_EXPIRED_EVENT, messageFrom, type Session } from "./api";

const WorkspaceApp = lazy(() => import("./WorkspaceApp"));
type Page = "login" | "register" | "forgot";
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

function PasswordField({ label, ...props }: Omit<React.InputHTMLAttributes<HTMLInputElement>, "type"> & { label: string }) {
  const [visible, setVisible] = useState(false);
  return <label className="field"><span>{label}</span><span className="password-input"><input {...props} type={visible ? "text" : "password"} /><button type="button" onClick={() => setVisible((value) => !value)} aria-label={visible ? "Ocultar senha" : "Mostrar senha"} title={visible ? "Ocultar senha" : "Mostrar senha"}>{visible ? "◉" : "◎"}</button></span></label>;
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
      <PasswordField label="Senha" name="password" autoComplete="current-password" placeholder="Sua senha" required />
      <button className="link-button align-right" type="button" onClick={() => go("forgot")}>Esqueci minha senha</button>
      <button className="primary" disabled={busy}>{busy ? "Entrando…" : "Entrar"}</button>
    </form>
    <p className="switch-copy">Ainda não tem acesso? <button className="link-button" onClick={() => go("register")}>Criar cadastro</button></p>
  </AuthShell>;
}

function Register({ onSession, go }: { onSession: (session: Session) => void; go: (page: Page) => void }) {
  const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password"));
    if (password !== data.get("confirmPassword")) { setError("As senhas precisam ser iguais."); setBusy(false); return; }
    try {
      onSession(await api<Session>("/auth/register", { method: "POST", body: JSON.stringify({ name: data.get("name"), email: data.get("email"), password, privacyNoticeVersion: "draft-1" }) }));
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <AuthShell eyebrow="Novo acesso" title="Crie seu cadastro" text="Depois do cadastro, um administrador libera seu acesso à equipe.">
    <form onSubmit={submit} className="form-stack">
      {error && <Notice>{error}</Notice>}
      <Field label="Nome completo" name="name" autoComplete="name" required />
      <Field label="E-mail" name="email" type="email" autoComplete="email" required />
      <PasswordField label="Senha" name="password" autoComplete="new-password" minLength={12} maxLength={72} required />
      <PasswordField label="Confirme a senha" name="confirmPassword" autoComplete="new-password" minLength={12} maxLength={72} required />
      <label className="check"><input name="privacy" type="checkbox" required /><span>Li o aviso de privacidade e entendo o uso dos dados para gestão interna.</span></label>
      <button className="primary" disabled={busy}>{busy ? "Criando cadastro…" : "Criar cadastro"}</button>
    </form>
    <p className="switch-copy">Já possui cadastro? <button className="link-button" onClick={() => go("login")}>Entrar</button></p>
  </AuthShell>;
}

function Forgot({ go }: { go: (page: Page) => void }) {
  return <AuthShell eyebrow="Recuperação" title="Recupere seu acesso" text="Peça a um administrador da plataforma para gerar uma senha temporária. No próximo login, você define uma nova senha.">
    <button className="primary" onClick={() => go("login")}>Voltar ao login</button>
  </AuthShell>;
}

function ChangePasswordForm({ forced = false, onChanged }: { forced?: boolean; onChanged: (session: Session) => void }) {
  const [error, setError] = useState(""); const [success, setSuccess] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess("");
    const form = event.currentTarget; const data = new FormData(form); const password = String(data.get("password"));
    if (password !== data.get("confirmPassword")) { setError("As senhas precisam ser iguais."); setBusy(false); return; }
    try {
      const session = await api<Session>("/auth/change-password", { method: "POST", body: JSON.stringify({ currentPassword: data.get("currentPassword"), password }) });
      form.reset(); setSuccess("Senha alterada. As outras sessões foram encerradas."); onChanged(session);
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <form onSubmit={submit} className="form-stack">
    {error && <Notice>{error}</Notice>}
    {success && <Notice kind="success">{success}</Notice>}
    <PasswordField label={forced ? "Senha temporária" : "Senha atual"} name="currentPassword" autoComplete="current-password" required />
    <PasswordField label="Nova senha" name="password" minLength={12} maxLength={72} autoComplete="new-password" required />
    <PasswordField label="Confirme a nova senha" name="confirmPassword" minLength={12} maxLength={72} autoComplete="new-password" required />
    <button className="primary" disabled={busy}>{busy ? "Salvando…" : "Alterar senha"}</button>
  </form>;
}

function ForcedPasswordChange({ onSession, logout }: { onSession: (session: Session) => void; logout: () => void }) {
  return <AuthShell eyebrow="Nova senha" title="Defina uma nova senha" text="Você entrou com uma senha temporária. Escolha uma senha pessoal com pelo menos 12 caracteres para continuar.">
    <ChangePasswordForm forced onChanged={onSession} />
    <button className="secondary" type="button" onClick={logout}>Sair</button>
  </AuthShell>;
}

function Pending({ session, logout }: { session: Session; logout: () => void }) {
  return <main className="waiting-page"><div className="waiting-card"><Brand /><div className="waiting-icon">⌛</div><span className="eyebrow dark">Cadastro recebido</span><h1>Acesso aguardando liberação</h1><p>Um administrador precisa incluir <strong>{session.email}</strong> na equipe antes do primeiro acesso.</p><div className="waiting-steps"><span className="done">1</span><b>Cadastro criado</b><i /><span>2</span><b>Liberação administrativa</b></div><button className="secondary" onClick={logout}>Sair</button></div></main>;
}

export default function App() {
  const [page, setPage] = useState<Page>("login");
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { api<Session>("/auth/session").then(setSession).catch(() => undefined).finally(() => setLoading(false)); }, []);
  useEffect(() => { const expire = () => { setSession(null); setPage("login"); }; window.addEventListener(AUTH_EXPIRED_EVENT, expire); return () => window.removeEventListener(AUTH_EXPIRED_EVENT, expire); }, []);
  async function logout() { try { await api("/auth/logout", { method: "POST" }); } finally { setSession(null); setPage("login"); } }
  if (loading) return <main className="loading-page"><Brand /><span className="loader" aria-label="Carregando" /></main>;
  if (session?.mustChangePassword) return <ForcedPasswordChange onSession={setSession} logout={logout} />;
  if (session?.state === "pending_approval") return <Pending session={session} logout={logout} />;
  if (session?.state === "suspended") return <main className="waiting-page"><div className="waiting-card"><Brand /><h1>Acesso suspenso</h1><p>Fale com um administrador da plataforma para revisar seu acesso.</p><button className="secondary" onClick={logout}>Sair</button></div></main>;
  if (session?.state === "active") return <Suspense fallback={<main className="loading-page"><Brand /><span className="loader" aria-label="Carregando área de trabalho" /></main>}><WorkspaceApp session={session} logout={logout} onSession={setSession} /></Suspense>;
  if (page === "register") return <Register go={setPage} onSession={setSession} />;
  if (page === "forgot") return <Forgot go={setPage} />;
  return <Login onSession={setSession} go={setPage} />;
}
