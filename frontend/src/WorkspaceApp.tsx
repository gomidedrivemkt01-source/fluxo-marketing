import { type CSSProperties, FormEvent, lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { api, AUTH_EXPIRED_EVENT, messageFrom, type Session } from "./api";
import accessIcon from "./assets/navigation/access.svg";
import calendarIcon from "./assets/navigation/calendar.svg";
import categoriesIcon from "./assets/navigation/categories.svg";
import companiesIcon from "./assets/navigation/companies.svg";
import dailyIcon from "./assets/navigation/daily.svg";
import demandsIcon from "./assets/navigation/demands.svg";
import homeIcon from "./assets/navigation/home.svg";
import myWorkIcon from "./assets/navigation/my-work.svg";
import reportsIcon from "./assets/navigation/reports.svg";
import settingsIcon from "./assets/navigation/settings.svg";
import teamIcon from "./assets/navigation/team.svg";
import workflowIcon from "./assets/navigation/workflow.svg";
import kanbanViewIcon from "./assets/views/kanban.svg";
import listViewIcon from "./assets/views/list.svg";
import allFocusIcon from "./assets/focus/all.svg";
import inboxFocusIcon from "./assets/focus/inbox.svg";
import todayFocusIcon from "./assets/focus/today.svg";
import upcomingFocusIcon from "./assets/focus/upcoming.svg";
import overdueFocusIcon from "./assets/focus/overdue.svg";
import waitingFocusIcon from "./assets/focus/waiting.svg";
import delegatedFocusIcon from "./assets/focus/delegated.svg";
import additionalActionIcon from "./assets/actions/additional.svg";
import fastActionIcon from "./assets/actions/fast.svg";
import playActionIcon from "./assets/actions/play.svg";
import { ActionIcon } from "./components/ActionIcon";
import { focusCounts, matchesFocus, type FocusView } from "./features/focus/focus";
import { buildSavedView, type SavedView, type SavedViewFilters } from "./features/focus/savedViews";
import { GlobalTimer } from "./features/time/GlobalTimer";

const loadActivityPanel = () => import("./features/collaboration/ActivityPanel").then((module) => ({ default: module.ActivityPanel }));
const loadFilesPanel = () => import("./features/files/FilesPanel").then((module) => ({ default: module.FilesPanel }));
const loadTimePanel = () => import("./features/time/TimePanel").then((module) => ({ default: module.TimePanel }));
const loadCalendarRoute = () => import("./pages/CalendarPage");
const loadReportsRoute = () => import("./pages/ReportsPage");
const loadWorkflowRoute = () => import("./pages/WorkflowPage");
const loadGovernanceSettingsRoute = () => import("./features/governance/GovernanceSettings").then((module) => ({ default: module.GovernanceSettings }));
const ActivityPanel = lazy(loadActivityPanel);
const FilesPanel = lazy(loadFilesPanel);
const TimePanel = lazy(loadTimePanel);
const CalendarRoute = lazy(loadCalendarRoute);
const ReportsRoute = lazy(loadReportsRoute);
const WorkflowRoute = lazy(loadWorkflowRoute);
const GovernanceSettingsRoute = lazy(loadGovernanceSettingsRoute);

type Page = "login" | "register" | "verify-signup" | "forgot" | "verify-recovery" | "reset";
export type Company = { id: string; name: string; shortName: string; code: string; color: string; description: string | null; active: boolean; revision: number };
export type Category = { id: string; name: string; code: string; color: string; defaultWorkflowId: string | null; active: boolean; revision: number };
type User = { id: string; profileId: string; name: string; email: string; state: string; role: string | null; revision: number; avatarUrl: string | null };
export type Person = { id: string; name: string; avatarUrl: string | null };
export type Workflow = { id: string; name: string; code: string; description: string | null; isDefault: boolean; lifecycleState: "DRAFT" | "PUBLISHED" | "RETIRED"; timeBasis: "ELAPSED" | "BUSINESS"; publishedAt: string | null; active: boolean; revision: number };
export type WorkflowStage = { id: string; workflowId: string | null; name: string; code: string; color: string; position: number; defaultAssigneeId: string | null; ownerRoleId: string | null; fallbackUserId: string | null; expectedDurationHours: number | null; slaHours: number | null; acceptanceRule: string | null; conditionRule: Record<string, unknown>; active: boolean; revision: number };
export type JobRole = { id: string; code: string; name: string; description: string | null; active: boolean; revision: number };
export type JobRoleAssignment = { id: string; roleId: string; profileId: string; profileName: string; priority: number; isFallback: boolean; active: boolean };
export type WorkflowBlueprintPreview = { blueprint: string; categories: number; stages: number; categoryFields: number; matchedCategories: string[]; missingCategories: string[]; existingWorkflows: Record<string, string>; safeToApply: boolean; workflowsCreated?: number; stagesCreated?: number; checklistsCreated?: number; briefingVersionsCreated?: number; roleAssignmentsCreated?: number; workflowsPublished?: number; bindingsCreated?: number; briefingVersionsPublished?: number; rolesWithoutPeople?: string[]; existingCardsMigrated?: number };
type BriefingFieldTemplate = { id: string; label: string; key: string; helpText: string | null; fieldType: "text" | "long_text" | "number" | "date" | "select"; options: string[]; required: boolean; position: number; active: boolean; revision: number };
export type ChecklistTemplateItem = { id: string; title: string; description: string | null; position: number; required: boolean; active: boolean; revision: number };
type DemandBriefing = { categoryId: string | null; categoryName: string | null; fields: (BriefingFieldTemplate & { value: string | null })[] };
type DemandChecklist = { stageId: string | null; stageName: string | null; completed: number; total: number; items: { id: string; title: string; description: string | null; position: number; required: boolean; completed: boolean; completedByName: string | null; completedAt: string | null; source: "template" | "custom" }[] };
type DemandTimelineStage = { id: string; name: string; code: string; color: string; position: number; state: "completed" | "current" | "upcoming" | "skipped"; enteredAt: string | null; leftAt: string | null; deadlineAt: string | null; forecastAt: string | null; risk: "none" | "overdue" | "at_risk" | "on_track" | "unscheduled"; revision: number; expectedDurationHours: number | null; assigneeId: string | null; assigneeName: string | null; assigneeAvatarUrl: string | null };
type DemandTimeline = { workflowId: string; workflowName: string; version: number; stages: DemandTimelineStage[] };
type PersonalColumn = { id: string; name: string; color: string };
type InterfaceColors = { sidebar: string; background: string; surface: string; text: string; primary: string; accent: string; highlight: string };
type InterfaceTheme = { id: string; name: string; colors: InterfaceColors };
type ViewPreferences = { demandView: "kanban" | "list"; showEmptyStages: boolean; stageOrder: string[]; focusView: FocusView; savedViews: SavedView[]; personalColumns: PersonalColumn[]; personalPlacements: Record<string, string>; activeThemeId: string; themeProfiles: InterfaceTheme[] };
type DemandDetailTab = "overview" | "briefing" | "checklist" | "workflow" | "activity" | "time";
export type Demand = {
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
  expectedEffortMinutes: number | null;
  coverImageUrl: string | null;
  assigneeId: string | null;
  assigneeName: string | null;
  assigneeAvatarUrl: string | null;
  createdById: string;
  createdByName: string;
  stageId: string | null;
  stageName: string | null;
  stageCode: string | null;
  stageColor: string | null;
  stagePosition: number | null;
  workflowId: string | null;
  workflowName: string | null;
  workflowVersion: number | null;
  revision: number;
  createdAt: string;
};
type Profile = { profileId: string; name: string; email: string; timezone: string; role: string | null; revision: number; avatarUrl: string | null; preferences: ViewPreferences };
type WorkspacePageData = { companies?: Company[] | null; categories?: Category[] | null; workflows?: Workflow[] | null; stages?: WorkflowStage[] | null; people?: Person[] | null; demands?: Demand[] | null; profile: Profile };
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
export type ReportBreakdown = { id: string; label: string; color: string | null; count: number; overdue: number; totalMinutes: number };
export type ReportTrendPoint = { date: string; created: number; completed: number; trackedMinutes: number };
export type ReportCapacity = { profileId: string; profileName: string; activeDemands: number; expectedMinutes: number; trackedMinutes: number };
export type ReportStagePerformance = { stageId: string; stageName: string; color: string; visits: number; averageHours: number; totalHours: number; slaHours: number | null; withinSla: number; breachedSla: number; slaRate: number | null; returns: number };
export type OperationalReport = {
  periodDays: number;
  periodStartedAt: string;
  periodEndedAt: string;
  generatedAt: string;
  scope: "team" | "person";
  scopeProfileId: string | null;
  scopeProfileName: string | null;
  canViewTeam: boolean;
  summary: { totalDemands: number; createdInPeriod: number; completedDemands: number; overdue: number; dueSoon: number; blocked: number; unassigned: number; urgent: number; trackedMinutes: number; expectedMinutes: number };
  byStatus: ReportBreakdown[];
  byCompany: ReportBreakdown[];
  byCategory: ReportBreakdown[];
  byAssignee: ReportBreakdown[];
  byStage: ReportBreakdown[];
  trendGranularity: "day" | "week" | "month";
  trend: ReportTrendPoint[];
  capacity: ReportCapacity[];
  stagePerformance: ReportStagePerformance[];
  attention: { id: string; publicId: string; title: string; companyName: string | null; assigneeName: string | null; stageName: string | null; status: string; priority: string; deadlineAt: string | null; reasons: string[] }[];
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

const builtInThemes: InterfaceTheme[] = [
  { id: "platform-default", name: "Padrão Fluxo", colors: { sidebar: "#0A1F2F", background: "#EDF2F4", surface: "#FFFFFF", text: "#0A1F2F", primary: "#087F76", accent: "#37C8B7", highlight: "#EE9B4B" } },
  { id: "builtin-ocean", name: "Oceano Executivo", colors: { sidebar: "#071D38", background: "#EAF2F8", surface: "#FFFFFF", text: "#102A43", primary: "#2563EB", accent: "#38BDF8", highlight: "#F59E0B" } },
  { id: "builtin-forest", name: "Floresta Serena", colors: { sidebar: "#102A23", background: "#EEF5F1", surface: "#FBFEFC", text: "#16352C", primary: "#217A5B", accent: "#62C6A0", highlight: "#D89A3D" } },
  { id: "builtin-terracotta", name: "Terracota Editorial", colors: { sidebar: "#3A211F", background: "#F8EFEA", surface: "#FFFDFC", text: "#3D2926", primary: "#B9563F", accent: "#E88A6F", highlight: "#D6A33C" } },
  { id: "builtin-violet", name: "Violeta Noturno", colors: { sidebar: "#12101E", background: "#1B1925", surface: "#272433", text: "#F4F0FA", primary: "#9B7ED9", accent: "#C7A7FF", highlight: "#F0A45D" } },
  { id: "builtin-graphite", name: "Grafite Minimalista", colors: { sidebar: "#121416", background: "#1C2023", surface: "#272C30", text: "#EEF2F3", primary: "#68C0B3", accent: "#9DD9D0", highlight: "#E6A35C" } },
];
const platformTheme = builtInThemes[0]!;

function contrastColor(hex: string): string {
  const value = hex.replace("#", "");
  const channels = [0, 2, 4].map((index) => {
    const channel = Number.parseInt(value.slice(index, index + 2), 16) / 255;
    return channel <= .03928 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
  });
  const luminance = channels[0]! * .2126 + channels[1]! * .7152 + channels[2]! * .0722;
  const darkLuminance = .012;
  return 1.05 / (luminance + .05) >= (luminance + .05) / (darkLuminance + .05) ? "#FFFFFF" : "#10202A";
}

function selectedTheme(preferences: ViewPreferences | undefined): InterfaceTheme {
  return builtInThemes.find((theme) => theme.id === preferences?.activeThemeId)
    ?? preferences?.themeProfiles.find((theme) => theme.id === preferences.activeThemeId)
    ?? platformTheme;
}

function themeStyle(preferences: ViewPreferences | undefined): CSSProperties {
  const selected = selectedTheme(preferences);
  return {
    "--sidebar": selected.colors.sidebar,
    "--app-bg": selected.colors.background,
    "--surface": selected.colors.surface,
    "--ink": selected.colors.text,
    "--ink-soft": `color-mix(in srgb, ${selected.colors.sidebar} 78%, ${selected.colors.accent})`,
    "--teal-dark": selected.colors.primary,
    "--teal": selected.colors.accent,
    "--orange": selected.colors.highlight,
    "--line": `color-mix(in srgb, ${selected.colors.text} 15%, ${selected.colors.surface})`,
    "--line-strong": `color-mix(in srgb, ${selected.colors.text} 25%, ${selected.colors.surface})`,
    "--muted": `color-mix(in srgb, ${selected.colors.text} 62%, ${selected.colors.surface})`,
    "--subtle": `color-mix(in srgb, ${selected.colors.text} 44%, ${selected.colors.surface})`,
    "--surface-soft": `color-mix(in srgb, ${selected.colors.surface} 88%, ${selected.colors.background})`,
    "--surface-muted": `color-mix(in srgb, ${selected.colors.surface} 72%, ${selected.colors.background})`,
    "--surface-hover": `color-mix(in srgb, ${selected.colors.accent} 10%, ${selected.colors.surface})`,
    "--on-primary": contrastColor(selected.colors.primary),
    "--on-sidebar": contrastColor(selected.colors.sidebar),
    "--sidebar-muted": `color-mix(in srgb, ${contrastColor(selected.colors.sidebar)} 62%, ${selected.colors.sidebar})`,
    "--shadow-color": `color-mix(in srgb, ${selected.colors.text} 18%, transparent)`,
  } as CSSProperties;
}

const focusOptions: { id: FocusView; label: string; icon: string }[] = [
  { id: "all", label: "Todos", icon: allFocusIcon },
  { id: "inbox", label: "Inbox", icon: inboxFocusIcon },
  { id: "today", label: "Hoje", icon: todayFocusIcon },
  { id: "upcoming", label: "Próximos", icon: upcomingFocusIcon },
  { id: "overdue", label: "Atrasadas", icon: overdueFocusIcon },
  { id: "waiting", label: "Aguardando", icon: waitingFocusIcon },
  { id: "delegated", label: "Delegadas", icon: delegatedFocusIcon },
];

function quickDeadline(schedule: string): string | null {
  if (schedule === "none") return null;
  const deadline = new Date();
  if (schedule === "tomorrow") deadline.setDate(deadline.getDate() + 1);
  deadline.setHours(17, 0, 0, 0);
  return deadline.toISOString();
}

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
      <PasswordField label="Senha" name="password" autoComplete="new-password" minLength={12} required />
      <PasswordField label="Confirme a senha" name="confirmPassword" autoComplete="new-password" minLength={12} required />
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
        <PasswordField label="Nova senha" name="password" minLength={12} autoComplete="new-password" required />
        <PasswordField label="Confirme a nova senha" name="confirmPassword" minLength={12} autoComplete="new-password" required />
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

const pageTitles: Record<WorkspacePage, string> = {
  overview: "Início",
  "my-work": "Meu trabalho",
  demands: "Demandas",
  calendar: "Calendário",
  companies: "Empresas",
  team: "Equipe",
  reports: "Relatórios",
  intelligence: "Dailys e importações",
  workflows: "Workflows",
  categories: "Categorias e briefings",
  users: "Usuários e acessos",
  settings: "Configurações",
  profile: "Meu perfil",
};

const workspacePages = Object.keys(pageTitles) as WorkspacePage[];

function pageFromLocation(): WorkspacePage {
  const legacyHash = window.location.hash.replace(/^#\/?/, "").split("/")[0] as WorkspacePage;
  if (workspacePages.includes(legacyHash)) return legacyHash;
  const pathPage = window.location.pathname.replace(/^\/+|\/+$/g, "").split("/")[0] as WorkspacePage;
  return workspacePages.includes(pathPage) ? pathPage : "overview";
}

function pageUrl(page: WorkspacePage): string {
  return `/${page}${window.location.search}`;
}

function preloadPageModule(page: WorkspacePage): void {
  if (page === "calendar") void loadCalendarRoute();
  else if (page === "reports") void loadReportsRoute();
  else if (page === "workflows") void loadWorkflowRoute();
  else if (page === "settings") void loadGovernanceSettingsRoute();
}

function dateLabel(value: string | null): string {
  if (!value) return "Sem prazo";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value));
}

function AvatarView({ name, url, size = "normal" }: { name: string; url?: string | null; size?: "normal" | "large" }) {
  return <span className={`avatar avatar-${size}`}>{url ? <img src={url} alt="" loading="lazy" decoding="async" /> : name.charAt(0).toUpperCase()}</span>;
}

function CardCover({ demand, variant }: { demand: Demand; variant: "demand" | "work" }) {
  if (!demand.coverImageUrl) return null;
  return <span className={`card-cover ${variant}-card-cover`}><img src={demand.coverImageUrl} alt="" loading="lazy" decoding="async" fetchPriority="low" onError={(event) => { event.currentTarget.parentElement!.hidden = true; }} /></span>;
}

function DemandCard({ demand, onOpen }: { demand: Demand; onOpen: () => void }) {
  return <button className="demand-card" onClick={onOpen}>
    <CardCover demand={demand} variant="demand" />
    <span className="card-top"><span /><span className={`priority priority-${demand.priority.toLowerCase()}`}>{priorityNames[demand.priority] ?? demand.priority}</span></span>
    <span className="card-company">{demand.companyColor && <i style={{ background: demand.companyColor }} />}{demand.companyName ?? "Sem empresa"}</span>
    <strong>{demand.title}</strong>
    <span className="card-description">{demand.description || "Sem descrição adicionada."}</span>
    <span className="card-meta"><span className={`demand-status ${demand.status.toLowerCase()}`}>{statusNames[demand.status] ?? demand.status}</span><span className={demand.deadlineAt && new Date(demand.deadlineAt) < new Date() ? "overdue" : ""}>◷ {dateLabel(demand.deadlineAt)}</span></span>
    <span className="card-footer"><span>{demand.categoryColor && <i style={{ background: demand.categoryColor }} />}{demand.categoryName ?? "Sem categoria"}</span><span className="card-code">{demand.publicId}</span></span>
  </button>;
}

function WorkCard({ demand, canEdit, canTrack, onOpen, onTimerStart, dragging = false, onDragStart, onDragEnd }: { demand: Demand; canEdit: boolean; canTrack: boolean; onOpen: () => void; onTimerStart: () => void; dragging?: boolean; onDragStart?: (event: React.DragEvent<HTMLElement>) => void; onDragEnd?: () => void }) {
  const overdue = Boolean(demand.deadlineAt && new Date(demand.deadlineAt) < new Date() && demand.status !== "COMPLETED");
  return <article className={`work-card${dragging ? " dragging" : ""}`} draggable={canEdit} onDragStart={onDragStart} onDragEnd={onDragEnd}>
    {canTrack && <button className="work-card-timer" type="button" draggable={false} onPointerDown={(event) => event.stopPropagation()} onClick={(event) => { event.stopPropagation(); onTimerStart(); }} aria-label={`Iniciar timer de ${demand.title}`} title="Iniciar timer"><ActionIcon src={playActionIcon} /></button>}
    <button className="work-card-open" onClick={onOpen}>
      <CardCover demand={demand} variant="work" />
      <span className="work-card-priority"><span className={`priority priority-${demand.priority.toLowerCase()}`}>{priorityNames[demand.priority] ?? demand.priority}</span></span>
      <span className="card-company">{demand.companyColor && <i style={{ background: demand.companyColor }} />}{demand.companyName ?? "Sem empresa"}</span>
      <strong>{demand.title}</strong>
      <span className="work-card-info"><span className={`demand-status ${demand.status.toLowerCase()}`}>{statusNames[demand.status] ?? demand.status}</span><span className={overdue ? "overdue" : ""}>◷ {dateLabel(demand.deadlineAt)}</span></span>
      <span className="work-card-footer"><span>{demand.assigneeName ? <><AvatarView name={demand.assigneeName} url={demand.assigneeAvatarUrl} />{demand.assigneeName}</> : "Sem responsável"}</span><span className="work-card-footer-meta"><span>{demand.categoryName ?? "Sem categoria"}</span><code>{demand.publicId}</code></span></span>
    </button>
  </article>;
}

function PersonalColumnsModal({ preferences, onClose, onSave }: { preferences: ViewPreferences; onClose: () => void; onSave: (preferences: ViewPreferences) => void }) {
  const [columns, setColumns] = useState(preferences.personalColumns);
  const [error, setError] = useState("");
  function move(index: number, direction: -1 | 1) { const target = index + direction; if (target < 0 || target >= columns.length) return; const next = [...columns]; [next[index], next[target]] = [next[target]!, next[index]!]; setColumns(next); }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!columns.length) { setError("Mantenha ao menos uma coluna."); return; }
    const validIds = new Set(columns.map((column) => column.id)); const fallback = columns[0]!.id;
    onSave({ ...preferences, personalColumns: columns, personalPlacements: Object.fromEntries(Object.entries(preferences.personalPlacements).map(([demandId, columnId]) => [demandId, validIds.has(columnId) ? columnId : fallback])) });
    onClose();
  }
  return <div className="modal-backdrop"><section className="form-modal compact-modal personal-columns-modal" role="dialog" aria-modal="true"><header className="modal-head"><div><span className="eyebrow dark">Área de trabalho pessoal</span><h2>Minhas colunas</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header><form className="modal-form" onSubmit={submit}>{error && <Notice>{error}</Notice>}<p className="form-intro">Estas colunas organizam apenas a sua visão. O workflow compartilhado de cada demanda continua igual.</p><div className="personal-column-editor">{columns.map((column, index) => <div key={column.id}><input type="color" value={column.color} onChange={(event) => setColumns((items) => items.map((item) => item.id === column.id ? { ...item, color: event.target.value } : item))} aria-label={`Cor de ${column.name}`} /><input value={column.name} minLength={2} maxLength={40} onChange={(event) => setColumns((items) => items.map((item) => item.id === column.id ? { ...item, name: event.target.value } : item))} required /><button type="button" disabled={index === 0} onClick={() => move(index, -1)}>↑</button><button type="button" disabled={index === columns.length - 1} onClick={() => move(index, 1)}>↓</button><button type="button" disabled={columns.length === 1} onClick={() => setColumns((items) => items.filter((item) => item.id !== column.id))}>×</button></div>)}</div><button className="secondary compact add-personal-column" type="button" disabled={columns.length >= 12} onClick={() => setColumns((items) => [...items, { id: crypto.randomUUID(), name: `Nova coluna ${items.length + 1}`, color: "#64748B" }])}>+ Adicionar coluna</button><footer className="form-actions"><button className="secondary compact" type="button" onClick={onClose}>Cancelar</button><button className="primary action-primary">Salvar colunas</button></footer></form></section></div>;
}

function WorkBoard({ demands, stages, people, companies, profile, mine, canEdit, onOpen, onPreferenceChange, onCalendar }: {
  demands: Demand[];
  stages: WorkflowStage[];
  people: Person[];
  companies: Company[];
  profile: Profile | null;
  mine: boolean;
  canEdit: boolean;
  onOpen: (demand: Demand) => void;
  onPreferenceChange: (preferences: ViewPreferences) => void;
  onCalendar: () => void;
}) {
  const defaultColumns: PersonalColumn[] = [
    { id: "inbox", name: "Entrada", color: "#64748B" },
    { id: "planned", name: "Planejado", color: "#2563EB" },
    { id: "doing", name: "Em andamento", color: "#0F766E" },
    { id: "review", name: "Revisar", color: "#D97706" },
    { id: "done", name: "Concluído", color: "#15803D" },
  ];
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("ALL");
  const [company, setCompany] = useState("ALL");
  const [assignees, setAssignees] = useState<string[]>([]);
  const [priority, setPriority] = useState("ALL");
  const [stage, setStage] = useState("ALL");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [showSaveView, setShowSaveView] = useState(false);
  const [showColumns, setShowColumns] = useState(false);
  const [draggedDemandId, setDraggedDemandId] = useState("");
  const [dragTargetId, setDragTargetId] = useState("");
  const [droppedColumnId, setDroppedColumnId] = useState("");
  const [visibleLimit, setVisibleLimit] = useState(48);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const preferences = profile?.preferences ?? {
    demandView: "kanban" as const,
    showEmptyStages: true,
    stageOrder: [],
    focusView: "all" as const,
    savedViews: [],
    personalColumns: defaultColumns,
    personalPlacements: {},
    activeThemeId: platformTheme.id,
    themeProfiles: [],
  };
  const counts = useMemo(() => profile ? focusCounts(demands, profile.profileId, profile.timezone) : null, [demands, profile]);
  const stageNames = useMemo(() => [...new Set(stages.filter((item) => item.active).map((item) => item.name))].sort((a, b) => a.localeCompare(b, "pt-BR")), [stages]);
  const visible = useMemo(() => demands.filter((demand) => {
    const needle = query.trim().toLocaleLowerCase("pt-BR");
    const matchesAssignee = !assignees.length
      || (assignees.includes("UNASSIGNED") && !demand.assigneeId)
      || Boolean(demand.assigneeId && assignees.includes(demand.assigneeId));
    return (!mine || Boolean(profile && matchesFocus(demand, preferences.focusView, profile.profileId, profile.timezone)))
      && (status === "ALL" || demand.status === status)
      && (company === "ALL" || demand.primaryCompanyId === company)
      && matchesAssignee
      && (priority === "ALL" || demand.priority === priority)
      && (stage === "ALL" || demand.stageName === stage)
      && (!needle || `${demand.publicId} ${demand.title} ${demand.companyName ?? ""} ${demand.assigneeName ?? ""}`.toLocaleLowerCase("pt-BR").includes(needle));
  }), [demands, mine, profile, preferences.focusView, status, company, assignees, priority, stage, query]);
  const personalColumns = preferences.personalColumns.length ? preferences.personalColumns : defaultColumns;
  const placements = preferences.personalPlacements;
  const currentFilters: SavedViewFilters = { query, companyId: company, status, priority, focusView: preferences.focusView };
  const activeSavedId = stage === "ALL" ? preferences.savedViews.find((view) => view.query === query.trim() && view.companyId === company && view.status === status && view.priority === priority && view.focusView === preferences.focusView)?.id : undefined;
  const activeFilterCount = (company !== "ALL" ? 1 : 0) + (status !== "ALL" ? 1 : 0) + (priority !== "ALL" ? 1 : 0) + (stage !== "ALL" ? 1 : 0) + assignees.length;
  const currentFocus = focusOptions.find((item) => item.id === preferences.focusView) ?? focusOptions[0]!;
  const galleryActive = !mine && preferences.demandView === "kanban";
  const personalKanbanActive = mine && preferences.demandView === "kanban";

  useEffect(() => { setVisibleLimit(48); }, [query, status, company, assignees, priority, stage, mine, preferences.focusView]);
  useEffect(() => {
    if (!galleryActive || visibleLimit >= visible.length || !loadMoreRef.current) return;
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setVisibleLimit((limit) => Math.min(limit + 48, visible.length));
    }, { rootMargin: "700px 0px" });
    observer.observe(loadMoreRef.current);
    return () => observer.disconnect();
  }, [galleryActive, visible.length, visibleLimit]);

  function beginDrag(event: React.DragEvent<HTMLElement>, demandId: string) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", demandId);
    setDraggedDemandId(demandId);
  }
  function finishDrag() { setDraggedDemandId(""); setDragTargetId(""); }
  function celebrateDrop(columnId: string) {
    setDroppedColumnId(columnId);
    window.setTimeout(() => setDroppedColumnId((current) => current === columnId ? "" : current), 520);
  }
  function dropPersonal(event: React.DragEvent, columnId: string) {
    event.preventDefault();
    setDragTargetId("");
    setDraggedDemandId("");
    const demandId = event.dataTransfer.getData("text/plain");
    if (demandId) {
      onPreferenceChange({ ...preferences, personalPlacements: { ...preferences.personalPlacements, [demandId]: columnId } });
      celebrateDrop(columnId);
    }
  }
  function applySavedView(view: SavedView) {
    setQuery(view.query);
    setCompany(view.companyId);
    setStatus(view.status);
    setPriority(view.priority);
    setStage("ALL");
    onPreferenceChange({ ...preferences, focusView: view.focusView });
  }
  function clearFilters() {
    setQuery("");
    setCompany("ALL");
    setStatus("ALL");
    setPriority("ALL");
    setStage("ALL");
    setAssignees([]);
    if (mine) onPreferenceChange({ ...preferences, focusView: "all" });
  }
  function saveCurrentView(name: string) {
    if (preferences.savedViews.length >= 12) throw new Error("Você pode manter até 12 visões salvas.");
    if (preferences.savedViews.some((view) => view.name.toLocaleLowerCase("pt-BR") === name.trim().toLocaleLowerCase("pt-BR"))) throw new Error("Já existe uma visão com esse nome.");
    onPreferenceChange({ ...preferences, savedViews: [...preferences.savedViews, buildSavedView(crypto.randomUUID(), name, currentFilters)] });
    setShowSaveView(false);
  }
  function removeSavedView(id: string) {
    onPreferenceChange({ ...preferences, savedViews: preferences.savedViews.filter((view) => view.id !== id) });
  }
  function toggleAssignee(id: string) {
    setAssignees((items) => items.includes(id) ? items.filter((value) => value !== id) : [...items, id]);
  }
  function startTimer(demandId: string) {
    window.dispatchEvent(new CustomEvent("fluxo:timer-start-request", { detail: { demandId } }));
  }
  function closeViewMenu(event: React.MouseEvent<HTMLButtonElement>) {
    event.currentTarget.closest("details")?.removeAttribute("open");
  }

  const flatList = <div className="flat-demand-list">{visible.map((demand) => <button key={demand.id} onClick={() => onOpen(demand)}><span className="demand-id">{demand.publicId}</span><strong>{demand.title}</strong><span>{demand.assigneeName ?? "Sem responsável"}</span><span>{demand.stageName ?? "Sem etapa"}</span><span className={`priority priority-${demand.priority.toLowerCase()}`}>{priorityNames[demand.priority]}</span></button>)}</div>;
  const gallery = <div className="demand-gallery">{visible.slice(0, visibleLimit).map((demand) => <WorkCard key={demand.id} demand={demand} canEdit={false} canTrack={canEdit} onOpen={() => onOpen(demand)} onTimerStart={() => startTimer(demand.id)} />)}{visibleLimit < visible.length && <div className="gallery-load-sentinel" ref={loadMoreRef}><span>Exibindo {visibleLimit} de {visible.length}</span><button type="button" className="secondary compact" onClick={() => setVisibleLimit((limit) => Math.min(limit + 48, visible.length))}>Carregar mais demandas</button></div>}</div>;
  const personalBoard = preferences.demandView === "kanban"
    ? <div className="kanban-board personal-kanban">{personalColumns.map((column) => {
      const items = visible.filter((demand) => (placements[demand.id] ?? personalColumns[0]?.id) === column.id);
      const animated = `${dragTargetId === column.id ? " drag-over" : ""}${droppedColumnId === column.id ? " drop-complete" : ""}`;
      return <section className={`kanban-column${animated}`} key={column.id} onDragEnter={() => { if (draggedDemandId) setDragTargetId(column.id); }} onDragOver={(event) => { event.preventDefault(); event.dataTransfer.dropEffect = "move"; }} onDrop={(event) => dropPersonal(event, column.id)}><header><span><i style={{ background: column.color }} />{column.name}</span><b>{items.length}</b></header><div>{items.map((demand) => <WorkCard key={demand.id} demand={demand} canEdit canTrack={canEdit} dragging={draggedDemandId === demand.id} onDragStart={(event) => beginDrag(event, demand.id)} onDragEnd={finishDrag} onOpen={() => onOpen(demand)} onTimerStart={() => startTimer(demand.id)} />)}{!items.length && <p className="column-empty">Solte uma demanda aqui</p>}</div></section>;
    })}</div>
    : <div className="grouped-list personal-list">{personalColumns.map((column) => {
      const items = visible.filter((demand) => (placements[demand.id] ?? personalColumns[0]?.id) === column.id);
      return <section key={column.id}><header><span><i style={{ background: column.color }} />{column.name}</span><b>{items.length}</b></header>{items.map((demand) => <button key={demand.id} onClick={() => onOpen(demand)}><span className="demand-id">{demand.publicId}</span><strong>{demand.title}</strong><span>{demand.companyName ?? "Sem empresa"}</span><span>{demand.stageName ?? "Sem etapa"}</span><span>{dateLabel(demand.deadlineAt)}</span><span className={`priority priority-${demand.priority.toLowerCase()}`}>{priorityNames[demand.priority]}</span></button>)}</section>;
    })}</div>;

  return <section className={`work-control${galleryActive ? " gallery-active" : ""}${personalKanbanActive ? " personal-kanban-active" : ""}`}>
    <div className="work-toolbar">
      <div className="work-toolbar-heading"><strong>{mine ? `Área de trabalho · ${profile?.name ?? ""}` : "Controle de demandas"}</strong><span>{visible.length} {visible.length === 1 ? "demanda" : "demandas"}</span></div>
      <label className="work-search"><span aria-hidden="true">⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Buscar demanda, código, empresa ou pessoa" /></label>
      <div className="work-toolbar-actions">
        {mine && <label className="compact-focus"><span>Foco</span><select value={preferences.focusView} onChange={(event) => onPreferenceChange({ ...preferences, focusView: event.target.value as FocusView })}>{focusOptions.map((item) => <option value={item.id} key={item.id}>{item.label} · {counts?.[item.id] ?? 0}</option>)}</select><ThemeIcon src={currentFocus.icon} className="focus-icon" /></label>}
        <button className={`filter-toggle${filtersOpen ? " active" : ""}`} type="button" aria-expanded={filtersOpen} onClick={() => setFiltersOpen((open) => !open)}><span aria-hidden="true">≡</span> Filtros{activeFilterCount > 0 && <b>{activeFilterCount}</b>}</button>
        <details className="view-menu"><summary><ThemeIcon src={preferences.demandView === "list" ? listViewIcon : kanbanViewIcon} className="view-icon" /><span>{preferences.demandView === "list" ? "Lista" : mine ? "Kanban" : "Galeria"}</span></summary><div><button className={preferences.demandView === "kanban" ? "active" : ""} onClick={(event) => { onPreferenceChange({ ...preferences, demandView: "kanban" }); closeViewMenu(event); }}><ThemeIcon src={kanbanViewIcon} className="view-icon" />{mine ? "Kanban" : "Galeria"}</button><button className={preferences.demandView === "list" ? "active" : ""} onClick={(event) => { onPreferenceChange({ ...preferences, demandView: "list" }); closeViewMenu(event); }}><ThemeIcon src={listViewIcon} className="view-icon" />Lista</button><button onClick={(event) => { closeViewMenu(event); onCalendar(); }}><ThemeIcon src={calendarIcon} className="view-icon" />Calendário</button>{mine && <button onClick={(event) => { closeViewMenu(event); setShowColumns(true); }}>⚙ Minhas colunas</button>}</div></details>
      </div>
    </div>
    {filtersOpen && <div className="work-filter-panel">
      <label><span>Empresa</span><select value={company} onChange={(event) => setCompany(event.target.value)}><option value="ALL">Todas</option>{companies.map((item) => <option value={item.id} key={item.id}>{item.shortName}</option>)}</select></label>
      {!mine && <div className="assignee-options"><span>Responsáveis</span><div><label><input type="checkbox" checked={assignees.includes("UNASSIGNED")} onChange={() => toggleAssignee("UNASSIGNED")} /> Sem responsável</label>{people.map((person) => <label key={person.id}><input type="checkbox" checked={assignees.includes(person.id)} onChange={() => toggleAssignee(person.id)} /> {person.name}</label>)}</div></div>}
      <label><span>Situação</span><select value={status} onChange={(event) => setStatus(event.target.value)}><option value="ALL">Todas</option>{Object.entries(statusNames).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label><span>Prioridade</span><select value={priority} onChange={(event) => setPriority(event.target.value)}><option value="ALL">Todas</option>{Object.entries(priorityNames).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label><span>Etapa</span><select value={stage} onChange={(event) => setStage(event.target.value)}><option value="ALL">Todas</option>{stageNames.map((name) => <option value={name} key={name}>{name}</option>)}</select></label>
      {mine && <div className="saved-views compact-saved-views"><div><strong>Visões salvas</strong><small>Filtros pessoais sincronizados</small></div><div className="saved-view-list">{preferences.savedViews.map((view) => <span className={`saved-view-chip ${activeSavedId === view.id ? "active" : ""}`} key={view.id}><button onClick={() => applySavedView(view)}>{view.name}</button><button onClick={() => removeSavedView(view.id)} aria-label={`Excluir visão ${view.name}`}>×</button></span>)}</div><button onClick={() => setShowSaveView(true)}>+ Salvar visão</button></div>}
      <div className="filter-panel-actions"><button type="button" onClick={clearFilters}>Limpar filtros</button><button type="button" onClick={() => setFiltersOpen(false)}>Aplicar</button></div>
    </div>}
    {mine && preferences.demandView === "kanban" && <div className="scope-note"><strong>Organização pessoal</strong><span>Mova os cards entre suas colunas sem alterar o workflow compartilhado.</span></div>}
    <div className="work-results">{!visible.length ? <div className="empty-state"><span>⌕</span><h3>Nenhuma demanda encontrada</h3><p>Ajuste os filtros para ampliar o resultado.</p></div> : mine ? personalBoard : preferences.demandView === "kanban" ? gallery : flatList}</div>
    {showSaveView && <SaveViewModal filters={currentFilters} onClose={() => setShowSaveView(false)} onSave={saveCurrentView} />}
    {showColumns && <PersonalColumnsModal preferences={preferences} onClose={() => setShowColumns(false)} onSave={onPreferenceChange} />}
  </section>;
}
function toInputDate(value: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function ThemeIcon({ src, className }: { src: string; className: string }) {
  return <span className={className} style={{ "--icon-source": `url("${src}")` } as CSSProperties} aria-hidden="true" />;
}

function NavIcon({ src }: { src: string }) {
  return <ThemeIcon src={src} className="nav-icon" />;
}

function SaveViewModal({ filters, onClose, onSave }: { filters: SavedViewFilters; onClose: () => void; onSave: (name: string) => void }) {
  const [error, setError] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    try { onSave(String(new FormData(event.currentTarget).get("name") ?? "")); }
    catch (caught) { setError(messageFrom(caught)); }
  }
  const focusLabel = focusOptions.find((item) => item.id === filters.focusView)?.label ?? "Todos";
  return <div className="modal-backdrop" role="presentation"><section className="form-modal compact-modal saved-view-modal" role="dialog" aria-modal="true" aria-labelledby="saved-view-title"><header className="modal-head"><div><span className="eyebrow dark">Preferência pessoal</span><h2 id="saved-view-title">Salvar visão</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header><form className="modal-form" onSubmit={submit}>{error && <Notice>{error}</Notice>}<Field label="Nome da visão" name="name" autoFocus minLength={2} maxLength={40} placeholder="Ex.: Urgentes de hoje" required /><div className="saved-view-summary"><strong>Filtros que serão lembrados</strong><span>Foco: {focusLabel}</span><span>Busca: {filters.query || "qualquer texto"}</span><span>Situação e prioridade: {statusNames[filters.status] ?? "todas"} · {priorityNames[filters.priority] ?? "todas"}</span></div><footer className="form-actions"><button className="secondary compact" type="button" onClick={onClose}>Cancelar</button><button className="primary action-primary">Salvar visão</button></footer></form></section></div>;
}

function ManualDemandModal({ companies, categories, workflows, people, stages, onClose, onCreated }: { companies: Company[]; categories: Category[]; workflows: Workflow[]; people: Person[]; stages: WorkflowStage[]; onClose: () => void; onCreated: (demand: Demand) => void }) {
  const initialWorkflow = workflows.find((item) => item.isDefault)?.id ?? workflows[0]?.id ?? "";
  const [workflowId, setWorkflowId] = useState(initialWorkflow);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const workflowStages = stages.filter((stage) => stage.workflowId === workflowId && stage.active).sort((a, b) => a.position - b.position);
  function changeCategory(value: string) { const category = categories.find((item) => item.id === value); if (category?.defaultWorkflowId) setWorkflowId(category.defaultWorkflowId); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget); const deadline = String(data.get("deadlineAt") || "");
    try {
      const created = await api<Demand>("/demands", { method: "POST", body: JSON.stringify({ title: data.get("title"), description: data.get("description") || null, companyId: data.get("companyId") || null, categoryId: data.get("categoryId") || null, workflowId: data.get("workflowId") || null, assigneeId: data.get("assigneeId") || null, stageId: data.get("stageId") || null, priority: data.get("priority"), deadlineAt: deadline ? new Date(deadline).toISOString() : null }) });
      onCreated(created);
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <div className="modal-backdrop" role="presentation"><section className="form-modal" role="dialog" aria-modal="true" aria-labelledby="new-demand-title"><header className="modal-head"><div><span className="eyebrow dark">Criação manual</span><h2 id="new-demand-title">Nova demanda</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header><form onSubmit={submit} className="modal-form"><p className="form-intro">A categoria sugere o workflow padrão. Você pode escolher outro fluxo somente para este card.</p>{error && <Notice>{error}</Notice>}<Field label="Título da demanda" name="title" maxLength={300} autoFocus placeholder="Ex.: Criar campanha de lançamento" required /><label className="field"><span>Descrição</span><textarea name="description" rows={4} maxLength={5000} placeholder="Contexto, objetivo e resultado esperado" /></label><div className="form-grid"><label className="field"><span>Empresa</span><select name="companyId"><option value="">Sem empresa definida</option>{companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label><label className="field"><span>Categoria</span><select name="categoryId" onChange={(event) => changeCategory(event.target.value)}><option value="">Sem categoria definida</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label></div><div className="form-grid"><label className="field"><span>Workflow</span><select name="workflowId" value={workflowId} onChange={(event) => setWorkflowId(event.target.value)} required>{workflows.map((workflow) => <option key={workflow.id} value={workflow.id}>{workflow.name}{workflow.isDefault ? " · padrão" : ""}</option>)}</select><small>O fluxo pode ser diferente do padrão da categoria neste card.</small></label><label className="field"><span>Etapa inicial</span><select name="stageId" key={workflowId} defaultValue={workflowStages[0]?.id ?? ""}><option value="">Sem etapa</option>{workflowStages.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></label></div><div className="form-grid"><label className="field"><span>Responsável</span><select name="assigneeId"><option value="">Sem responsável</option>{people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label><label className="field"><span>Prioridade</span><select name="priority" defaultValue="NORMAL"><option value="LOW">Baixa</option><option value="NORMAL">Normal</option><option value="HIGH">Alta</option><option value="URGENT">Urgente</option></select></label></div><Field label="Prazo" name="deadlineAt" type="datetime-local" /><footer className="form-actions"><button className="secondary compact" type="button" onClick={onClose}>Cancelar</button><button className="primary action-primary" disabled={busy}>{busy ? "Criando…" : "Criar demanda"}</button></footer></form></section></div>;
}
function QuickCaptureModal({ onClose, onCreate }: { onClose: () => void; onCreate: (title: string, deadlineAt: string | null) => Promise<void> }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      await onCreate(String(data.get("title") ?? ""), quickDeadline(String(data.get("schedule") ?? "none")));
      onClose();
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <div className="modal-backdrop quick-capture-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}><section className="form-modal quick-capture-modal" role="dialog" aria-modal="true" aria-labelledby="quick-capture-title"><header className="modal-head"><div><span className="eyebrow dark">Captura global · tecla Q</span><h2 id="quick-capture-title">Adicionar ao meu trabalho</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header><form className="modal-form" onSubmit={submit}>{error && <Notice>{error}</Notice>}<Field label="O que precisa ser feito?" name="title" autoFocus minLength={2} maxLength={300} placeholder="Digite o título da demanda" required /><label className="field"><span>Prazo rápido</span><select name="schedule"><option value="none">Sem prazo · enviar para Inbox</option><option value="today">Hoje · 17h</option><option value="tomorrow">Amanhã · 17h</option></select></label><p className="form-intro">A demanda será atribuída a você na primeira etapa do fluxo. Complete os demais campos no painel que abrir em seguida.</p><footer className="form-actions"><button className="secondary compact" type="button" onClick={onClose}>Cancelar</button><button className="primary action-primary" disabled={busy}>{busy ? "Adicionando…" : "+ Adicionar"}</button></footer></form></section></div>;
}

function TaskDrawer({ demand, companies, categories, people, stages, canEdit, canDelete, onClose, onOpenFull, onSaved, onRemoved }: {
  demand: Demand;
  companies: Company[];
  categories: Category[];
  people: Person[];
  stages: WorkflowStage[];
  canEdit: boolean;
  canDelete: boolean;
  onClose: () => void;
  onOpenFull: (tab: DemandDetailTab) => void;
  onSaved: (demand: Demand) => void;
  onRemoved: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [success, setSuccess] = useState("");
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess("");
    const data = new FormData(event.currentTarget); const deadline = String(data.get("deadlineAt") || "");
    try {
      const updated = await api<Demand>(`/demands/${demand.id}`, { method: "PUT", body: JSON.stringify({ title: data.get("title"), description: data.get("description") || null, companyId: data.get("companyId") || null, categoryId: data.get("categoryId") || null, assigneeId: data.get("assigneeId") || null, stageId: data.get("stageId") || null, priority: data.get("priority"), status: data.get("status"), deadlineAt: deadline ? new Date(deadline).toISOString() : null, expectedRevision: demand.revision }) });
      onSaved(updated); setSuccess("Alterações salvas.");
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function removeDrawerDemand(mode: "archive" | "delete") {
    const message = mode === "archive" ? `Arquivar “${demand.title}”? Ela poderá ser restaurada nas Configurações.` : `Enviar “${demand.title}” para a lixeira recuperável?`;
    if (!window.confirm(message)) return;
    setBusy(true); setError("");
    try {
      if (mode === "archive") await api(`/demands/${demand.id}/archive`, { method: "POST", body: JSON.stringify({ expectedRevision: demand.revision }) });
      else await api(`/demands/${demand.id}?expectedRevision=${demand.revision}`, { method: "DELETE" });
      await onRemoved();
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <div className="drawer-backdrop" role="presentation" onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}><aside className="task-drawer" role="dialog" aria-modal="true" aria-labelledby="task-drawer-title">
    <header><div><span className="demand-id">{demand.publicId}</span><h2 id="task-drawer-title">Consulta rápida</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header>
    <div className="drawer-context"><span className="stage-badge" style={{ borderColor: demand.stageColor ?? undefined }}><i style={{ background: demand.stageColor ?? "#94a3b8" }} />{demand.stageName ?? "Sem etapa"}</span><small>Criada por {demand.createdByName}</small></div>
    <nav className="drawer-shortcuts" aria-label="Atalhos do card"><span>Continuar no card</span><button type="button" onClick={() => onOpenFull("activity")}>Atividade</button><button type="button" onClick={() => onOpenFull("checklist")}>Checklist</button><button type="button" onClick={() => onOpenFull("time")}>Tempo</button></nav>
    <form className="drawer-form" onSubmit={save}>
      <div className="drawer-form-body">
        {error && <Notice>{error}</Notice>}{success && <Notice kind="success">{success}</Notice>}
        <Field label="Título" name="title" defaultValue={demand.title} required disabled={!canEdit} />
        <label className="field"><span>Situação</span><select name="status" defaultValue={demand.status} disabled={!canEdit}>{Object.entries(statusNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="field"><span>Descrição</span><textarea name="description" rows={5} defaultValue={demand.description ?? ""} disabled={!canEdit} /></label>
        <div className="form-grid"><label className="field"><span>Empresa</span><select name="companyId" defaultValue={demand.primaryCompanyId ?? ""} disabled={!canEdit}><option value="">Sem empresa</option>{companies.map((company) => <option key={company.id} value={company.id}>{company.name}</option>)}</select></label><label className="field"><span>Categoria</span><select name="categoryId" defaultValue={demand.categoryId ?? ""} disabled={!canEdit}><option value="">Sem categoria</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}</select></label></div>
        <div className="form-grid"><label className="field"><span>Responsável</span><select name="assigneeId" defaultValue={demand.assigneeId ?? ""} disabled={!canEdit}><option value="">Sem responsável</option>{people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select></label><label className="field"><span>Etapa</span><select name="stageId" defaultValue={demand.stageId ?? ""} disabled={!canEdit}>{stages.map((stage) => <option key={stage.id} value={stage.id}>{stage.name}</option>)}</select></label></div>
        <div className="form-grid"><label className="field"><span>Prioridade</span><select name="priority" defaultValue={demand.priority} disabled={!canEdit}>{Object.entries(priorityNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><Field label="Prazo" name="deadlineAt" type="datetime-local" defaultValue={demand.deadlineAt ? demand.deadlineAt.slice(0, 16) : ""} disabled={!canEdit} /></div>
      </div>
      <footer><button className="secondary compact" type="button" onClick={() => onOpenFull("overview")}>Abrir card completo</button><span className="drawer-remove-actions">{canEdit && <button className="secondary compact" type="button" disabled={busy} onClick={() => void removeDrawerDemand("archive")}>Arquivar</button>}{canDelete && <button className="secondary compact danger-text" type="button" disabled={busy} onClick={() => void removeDrawerDemand("delete")}>Excluir</button>}</span>{canEdit && <button className="primary action-primary" disabled={busy}>{busy ? "Salvando…" : "Salvar"}</button>}</footer>
    </form>
  </aside></div>;
}

function CatalogModal({ kind, item, workflows, onClose, onSaved }: { kind: "company" | "category"; item?: Company | Category | null; workflows: Workflow[]; onClose: () => void; onSaved: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const isCompany = kind === "company";
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); const data = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = { name: data.get("name"), code: data.get("code"), color: data.get("color") };
    if (isCompany) { payload.shortName = data.get("shortName"); payload.description = data.get("description") || null; }
    else payload.defaultWorkflowId = data.get("defaultWorkflowId") || null;
    if (item) { payload.expectedRevision = item.revision; payload.active = item.active; }
    const base = isCompany ? "/catalogs/companies" : "/catalogs/categories";
    try { await api(item ? `${base}/${item.id}` : base, { method: item ? "PUT" : "POST", body: JSON.stringify(payload) }); await onSaved(); onClose(); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  const company = item && "shortName" in item ? item : null;
  const category = item && "defaultWorkflowId" in item ? item : null;
  return <div className="modal-backdrop"><section className="form-modal compact-modal" role="dialog" aria-modal="true"><header className="modal-head"><div><span className="eyebrow dark">{item ? "Editar cadastro" : "Novo cadastro"}</span><h2>{isCompany ? "Empresa" : "Categoria"}</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header><form className="modal-form" onSubmit={submit}>{error && <Notice>{error}</Notice>}<Field label="Nome" name="name" defaultValue={item?.name} required />{isCompany && <Field label="Nome curto" name="shortName" defaultValue={company?.shortName} required />}<Field label="Código" name="code" defaultValue={item?.code} placeholder="EXEMPLO" required /><label className="field color-field"><span>Cor de identificação</span><input name="color" type="color" defaultValue={item?.color ?? (isCompany ? "#155E75" : "#475569")} /></label>{isCompany ? <label className="field"><span>Descrição</span><textarea name="description" rows={3} defaultValue={company?.description ?? ""} /></label> : <label className="field"><span>Workflow padrão</span><select name="defaultWorkflowId" defaultValue={category?.defaultWorkflowId ?? workflows.find((workflow) => workflow.isDefault)?.id ?? ""}><option value="">Sem workflow vinculado</option>{workflows.map((workflow) => <option key={workflow.id} value={workflow.id} disabled={workflow.lifecycleState !== "PUBLISHED"}>{workflow.name}{workflow.lifecycleState === "DRAFT" ? " · rascunho" : ""}</option>)}</select><small>Rascunhos ficam visíveis para conferência e são liberados após a publicação.</small></label>}<footer className="form-actions"><button className="secondary compact" type="button" onClick={onClose}>Cancelar</button><button className="primary action-primary" disabled={busy}>{busy ? "Salvando…" : "Salvar"}</button></footer></form></section></div>;
}

function BriefingTemplateModal({ category, onClose }: { category: Category; onClose: () => void }) {
  const [items, setItems] = useState<BriefingFieldTemplate[]>([]); const [editing, setEditing] = useState<BriefingFieldTemplate | "new" | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  async function load() { try { setItems(await api<BriefingFieldTemplate[]>(`/catalogs/categories/${category.id}/briefing-fields`)); } catch (caught) { setError(messageFrom(caught)); } }
  useEffect(() => { void load(); }, [category.id]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); const data = new FormData(event.currentTarget); const current = editing === "new" ? null : editing;
    const options = String(data.get("options") || "").split("\n").map((value) => value.trim()).filter(Boolean);
    const payload: Record<string, unknown> = { label: data.get("label"), key: data.get("key"), helpText: data.get("helpText") || null, fieldType: data.get("fieldType"), options, required: data.get("required") === "on", position: current?.position ?? items.length + 1 };
    if (current) { payload.expectedRevision = current.revision; payload.active = data.get("active") === "on"; }
    try { await api(current ? `/catalogs/briefing-fields/${current.id}` : `/catalogs/categories/${category.id}/briefing-fields`, { method: current ? "PUT" : "POST", body: JSON.stringify(payload) }); await load(); setEditing(null); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  const current = editing === "new" ? null : editing;
  return <div className="modal-backdrop"><section className="form-modal template-modal" role="dialog" aria-modal="true"><header className="modal-head"><div><span className="eyebrow dark">Modelo por categoria</span><h2>Briefing · {category.name}</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header>{editing ? <form className="modal-form" onSubmit={submit}>{error && <Notice>{error}</Notice>}<div className="form-grid"><Field label="Pergunta" name="label" defaultValue={current?.label} placeholder="Ex.: Qual é o objetivo?" required /><Field label="Chave interna" name="key" defaultValue={current?.key} placeholder="objetivo" required /></div><label className="field"><span>Tipo de resposta</span><select name="fieldType" defaultValue={current?.fieldType ?? "text"}><option value="text">Texto curto</option><option value="long_text">Texto longo</option><option value="number">Número</option><option value="date">Data</option><option value="select">Seleção</option></select></label><label className="field"><span>Texto de ajuda</span><textarea name="helpText" rows={2} defaultValue={current?.helpText ?? ""} /></label><label className="field"><span>Opções de seleção <small>uma por linha</small></span><textarea name="options" rows={4} defaultValue={current?.options.join("\n") ?? ""} /></label><label className="check stage-active-check"><input name="required" type="checkbox" defaultChecked={current?.required} /><span>Resposta obrigatória</span></label>{current && <label className="check stage-active-check"><input name="active" type="checkbox" defaultChecked={current.active} /><span>Campo ativo no briefing</span></label>}<footer className="form-actions"><button className="secondary compact" type="button" onClick={() => setEditing(null)}>Voltar</button><button className="primary action-primary" disabled={busy}>{busy ? "Salvando…" : "Salvar campo"}</button></footer></form> : <div className="template-body">{error && <Notice>{error}</Notice>}<div className="template-intro"><p>Monte as perguntas que aparecerão nas demandas desta categoria.</p><button className="small-button" onClick={() => setEditing("new")}>+ Novo campo</button></div>{items.length ? <div className="template-list">{items.map((item) => <button key={item.id} className={!item.active ? "inactive" : ""} onClick={() => setEditing(item)}><span>{item.position}</span><div><strong>{item.label}{item.required && <b>Obrigatório</b>}</strong><small>{item.fieldType.replace("_", " ")} · {item.key}</small></div><em>{item.active ? "Editar" : "Inativo"}</em></button>)}</div> : <div className="empty-state compact-empty"><span>▤</span><h3>Briefing ainda sem campos</h3><p>Adicione as perguntas necessárias para iniciar este tipo de trabalho.</p></div>}</div>}</section></div>;
}

const interfaceColorFields: { key: keyof InterfaceColors; label: string; description: string }[] = [
  { key: "sidebar", label: "Menu lateral", description: "Fundo da navegação principal" },
  { key: "background", label: "Fundo da interface", description: "Área externa dos painéis" },
  { key: "surface", label: "Cards e painéis", description: "Superfícies de conteúdo" },
  { key: "text", label: "Texto principal", description: "Títulos e informações relevantes" },
  { key: "primary", label: "Ações principais", description: "Botões e estados selecionados" },
  { key: "accent", label: "Acentos", description: "Ícones e detalhes de apoio" },
  { key: "highlight", label: "Destaques", description: "Alertas e indicadores especiais" },
];

function InterfaceThemeModal({ preferences, onClose, onSave }: { preferences: ViewPreferences; onClose: () => void; onSave: (preferences: ViewPreferences) => Promise<void> }) {
  const selected = selectedTheme(preferences);
  const [editing, setEditing] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [colors, setColors] = useState<InterfaceColors>({ ...selected.colors });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const themes = [...builtInThemes, ...preferences.themeProfiles];
  function openEditor(theme: InterfaceTheme, editExisting = false) {
    if (!editExisting && preferences.themeProfiles.length >= 8) { setError("Você pode manter até 8 perfis de cores personalizados."); return; }
    setEditingId(editExisting ? theme.id : null);
    setName(editExisting ? theme.name : `${theme.name} personalizado`);
    setColors({ ...theme.colors });
    setError(""); setEditing(true);
  }
  async function activate(themeId: string) {
    setBusy(true); setError("");
    try { await onSave({ ...preferences, activeThemeId: themeId }); onClose(); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function saveEditor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError("");
    const cleanName = name.trim();
    if (cleanName.length < 2) { setError("Informe um nome para o perfil."); return; }
    if (!editingId && preferences.themeProfiles.length >= 8) { setError("Você pode manter até 8 perfis de cores personalizados."); return; }
    if (themes.some((theme) => theme.id !== editingId && theme.name.toLocaleLowerCase("pt-BR") === cleanName.toLocaleLowerCase("pt-BR"))) { setError("Já existe um perfil com esse nome."); return; }
    const theme: InterfaceTheme = { id: editingId ?? crypto.randomUUID(), name: cleanName, colors };
    const themeProfiles = editingId
      ? preferences.themeProfiles.map((item) => item.id === editingId ? theme : item)
      : [...preferences.themeProfiles, theme];
    setBusy(true);
    try { await onSave({ ...preferences, activeThemeId: theme.id, themeProfiles }); onClose(); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function remove(themeId: string) {
    setBusy(true); setError("");
    try {
      await onSave({ ...preferences, activeThemeId: platformTheme.id, themeProfiles: preferences.themeProfiles.filter((theme) => theme.id !== themeId) });
      setConfirmDeleteId(null);
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  function themeRow(theme: InterfaceTheme, fixed: boolean) {
    const active = selected.id === theme.id;
    return <article className={active ? "active" : ""} key={theme.id}>
      <div className="theme-swatches" aria-hidden="true">{Object.values(theme.colors).map((color, index) => <i key={`${color}-${index}`} style={{ background: color }} />)}</div>
      <div><strong>{theme.name}</strong><span>{fixed ? "Paleta fixa da plataforma" : "Modelo personalizado editável"}</span></div>
      <div className="theme-profile-actions">
        {active ? <b>Em uso</b> : <button disabled={busy} onClick={() => void activate(theme.id)}>Usar</button>}
        <button disabled={busy} onClick={() => openEditor(theme)}>Duplicar</button>
        {!fixed && <button disabled={busy} onClick={() => openEditor(theme, true)}>Editar</button>}
        {!fixed && <button className="theme-delete" disabled={busy} onClick={() => confirmDeleteId === theme.id ? void remove(theme.id) : setConfirmDeleteId(theme.id)}>{confirmDeleteId === theme.id ? "Confirmar exclusão" : "Excluir"}</button>}
      </div>
    </article>;
  }
  return <div className="modal-backdrop theme-backdrop" role="presentation"><section className="form-modal theme-modal" role="dialog" aria-modal="true" aria-labelledby="theme-modal-title"><header className="modal-head"><div><span className="eyebrow dark">Preferência individual</span><h2 id="theme-modal-title">Editar interface</h2></div><button className="icon-button" onClick={onClose} aria-label="Fechar">×</button></header>{error && <div className="theme-error"><Notice>{error}</Notice></div>}{editing ? <form className="theme-create" onSubmit={saveEditor}><div className="theme-create-head"><div><strong>{editingId ? "Editar perfil personalizado" : "Novo perfil personalizado"}</strong><span>A paleta gera automaticamente superfícies, campos, bordas e contrastes da interface.</span></div><button type="button" className="link-button" onClick={() => { setEditing(false); setEditingId(null); setError(""); }}>Voltar aos perfis</button></div><label className="field"><span>Nome do perfil</span><input value={name} onChange={(event) => setName(event.target.value)} maxLength={40} placeholder="Ex.: Azul executivo" autoFocus required /></label><div className="theme-color-grid">{interfaceColorFields.map((field) => <label className="theme-color-field" key={field.key}><input type="color" value={colors[field.key]} onChange={(event) => setColors((current) => ({ ...current, [field.key]: event.target.value.toUpperCase() }))} aria-label={field.label} /><span><strong>{field.label}</strong><small>{field.description}</small></span><code>{colors[field.key].toUpperCase()}</code></label>)}</div><footer className="form-actions"><button className="secondary compact" type="button" onClick={() => setEditing(false)}>Cancelar</button><button className="primary action-primary" disabled={busy}>{busy ? "Salvando…" : editingId ? "Salvar alterações" : "Salvar e aplicar perfil"}</button></footer></form> : <div className="theme-library"><div className="theme-library-intro"><div><strong>Paletas da plataforma</strong><span>Seis estilos prontos e protegidos. Use diretamente ou duplique para personalizar.</span></div><button className="small-button" onClick={() => openEditor(selected)}>+ Novo perfil</button></div><section className="theme-library-section"><header><strong>Estilos prontos</strong><span>{builtInThemes.length}</span></header><div className="theme-profile-list">{builtInThemes.map((theme) => themeRow(theme, true))}</div></section><section className="theme-library-section custom"><header><div><strong>Meus perfis</strong><small>Até 8 modelos personalizados</small></div><span>{preferences.themeProfiles.length}</span></header>{preferences.themeProfiles.length ? <div className="theme-profile-list">{preferences.themeProfiles.map((theme) => themeRow(theme, false))}</div> : <div className="theme-library-empty"><strong>Nenhum perfil personalizado</strong><span>Duplique uma paleta pronta ou crie um perfil baseado no tema atual.</span></div>}</section></div>}</section></div>;
}

function ProfilePage({ profile, session, onUpdated }: { profile: Profile | null; session: Session; onUpdated: (profile: Profile) => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [success, setSuccess] = useState(""); const [showTheme, setShowTheme] = useState(false);
  if (!profile) return <section className="panel page-panel loading-block"><span className="loader" /></section>;
  const current = profile;
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess(""); const data = new FormData(event.currentTarget);
    try { const updated = await api<Profile>("/users/me", { method: "PUT", body: JSON.stringify({ name: data.get("name"), timezone: data.get("timezone"), expectedRevision: current.revision }) }); onUpdated(updated); setSuccess("Perfil atualizado."); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function saveTheme(preferences: ViewPreferences) {
    setError(""); setSuccess("");
    try { const updated = await api<Profile>("/users/me/preferences", { method: "PUT", body: JSON.stringify(preferences) }); onUpdated(updated); setSuccess("Perfil de interface aplicado."); }
    catch (caught) { setError(messageFrom(caught)); throw caught; }
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
  return <><div className="profile-layout"><section className="panel profile-card"><AvatarView name={profile.name} url={profile.avatarUrl} size="large" /><h3>{profile.name}</h3><p>{profile.email}</p><span>{session.role ? roleNames[session.role] : "Sem perfil"}</span><label className="small-button upload-avatar">Alterar foto<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} onChange={(event) => { const file = event.currentTarget.files?.[0]; if (file) void upload(file); }} /></label>{profile.avatarUrl && <button className="link-button" disabled={busy} onClick={() => void removeAvatar()}>Remover foto</button>}<button className="secondary compact edit-interface-button" onClick={() => setShowTheme(true)}>Editar interface</button><small>Foto: JPG, PNG ou WebP, até 2 MB.</small></section><section className="panel profile-form"><div className="panel-head"><div><span className="eyebrow dark">Dados pessoais</span><h3>Informações do perfil</h3></div></div><form className="modal-form" onSubmit={save}>{error && <Notice>{error}</Notice>}{success && <Notice kind="success">{success}</Notice>}<Field label="Nome completo" name="name" defaultValue={profile.name} required /><Field label="E-mail" value={profile.email} disabled /><label className="field"><span>Fuso horário</span><select name="timezone" defaultValue={profile.timezone}><option value="America/Sao_Paulo">Brasília — São Paulo</option><option value="America/Manaus">Manaus</option><option value="America/Rio_Branco">Rio Branco</option></select></label><div className="profile-note"><strong>Perfil de acesso</strong><span>{session.role ? roleNames[session.role] : "Sem perfil"}</span><small>Alterações de permissão são feitas por um administrador.</small></div><footer className="form-actions"><button className="primary action-primary" disabled={busy}>{busy ? "Salvando…" : "Salvar alterações"}</button></footer></form></section></div>{showTheme && <InterfaceThemeModal preferences={profile.preferences} onClose={() => setShowTheme(false)} onSave={saveTheme} />}</>;
}

function BriefingPanel({ demand, canEdit, onSaved }: { demand: Demand; canEdit: boolean; onSaved: (demand: Demand) => void }) {
  const [briefing, setBriefing] = useState<DemandBriefing | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState(""); const [success, setSuccess] = useState("");
  async function load() { setError(""); try { setBriefing(await api<DemandBriefing>(`/demands/${demand.id}/briefing`)); } catch (caught) { setError(messageFrom(caught)); } }
  useEffect(() => { void load(); }, [demand.id, demand.categoryId]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!briefing) return; setBusy(true); setError(""); setSuccess(""); const data = new FormData(event.currentTarget);
    try { const updated = await api<Demand>(`/demands/${demand.id}/briefing`, { method: "PUT", body: JSON.stringify({ expectedRevision: demand.revision, answers: briefing.fields.map((field) => ({ fieldId: field.id, value: data.get(field.id) || null })) }) }); onSaved(updated); setSuccess("Briefing atualizado."); await load(); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  if (!briefing && error) return <section className="panel feature-preview"><span>!</span><h3>Não foi possível carregar o briefing</h3><p>{error}</p><button className="secondary compact" onClick={() => void load()}>Tentar novamente</button></section>;
  if (!briefing) return <section className="panel feature-loading"><span className="loader" /></section>;
  if (!briefing.categoryId) return <section className="panel feature-preview"><span>▤</span><h3>Selecione uma categoria</h3><p>O modelo de briefing é definido pela categoria da demanda. Escolha uma categoria na visão geral para continuar.</p></section>;
  if (!briefing.fields.length) return <section className="panel feature-preview"><span>▤</span><h3>Briefing sem modelo</h3><p>A categoria {briefing.categoryName} ainda não possui perguntas configuradas.</p></section>;
  return <section className="panel work-content-panel"><div className="work-content-head"><div><span className="eyebrow dark">Modelo da categoria</span><h3>Briefing · {briefing.categoryName}</h3><p>As respostas ficam salvas no card e disponíveis para toda a equipe.</p></div><span>{briefing.fields.filter((field) => field.value).length}/{briefing.fields.length} preenchidos</span></div><form className="modal-form" onSubmit={save}>{error && <Notice>{error}</Notice>}{success && <Notice kind="success">{success}</Notice>}{briefing.fields.map((field) => <label className="field" key={field.id}><span>{field.label}{field.required && <b className="required-mark"> Obrigatório</b>}</span>{field.fieldType === "long_text" ? <textarea name={field.id} rows={5} defaultValue={field.value ?? ""} required={field.required} disabled={!canEdit} /> : field.fieldType === "select" ? <select name={field.id} defaultValue={field.value ?? ""} required={field.required} disabled={!canEdit}><option value="">Selecione</option>{field.options.map((option) => <option value={option} key={option}>{option}</option>)}</select> : <input name={field.id} type={field.fieldType === "number" ? "number" : field.fieldType === "date" ? "date" : "text"} defaultValue={field.value ?? ""} required={field.required} disabled={!canEdit} />}{field.helpText && <small>{field.helpText}</small>}</label>)}<footer className="form-actions"><span className="revision-note">Revisão do card: {demand.revision}</span><button className="primary action-primary" disabled={busy || !canEdit}>{busy ? "Salvando…" : "Salvar briefing"}</button></footer></form></section>;
}

function ChecklistPanel({ demand, canEdit, onSaved, compact = false }: { demand: Demand; canEdit: boolean; onSaved: (demand: Demand) => void; compact?: boolean }) {
  const [checklist, setChecklist] = useState<DemandChecklist | null>(null);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  async function load() { setError(""); try { setChecklist(await api<DemandChecklist>(`/demands/${demand.id}/checklist`)); } catch (caught) { setError(messageFrom(caught)); } }
  useEffect(() => { void load(); }, [demand.id, demand.stageId]);
  async function toggle(item: DemandChecklist["items"][number], completed: boolean) {
    setBusyId(item.id); setError("");
    const path = item.source === "custom" ? `checklist-items/${item.id}` : `checklist/${item.id}`;
    try { const updated = await api<Demand>(`/demands/${demand.id}/${path}`, { method: "PATCH", body: JSON.stringify({ completed, expectedRevision: demand.revision }) }); onSaved(updated); await load(); }
    catch (caught) { setError(messageFrom(caught)); await load(); } finally { setBusyId(""); }
  }
  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const title = String(new FormData(form).get("title") ?? "").trim(); if (!title) return;
    setBusyId("new"); setError("");
    try { const updated = await api<Demand>(`/demands/${demand.id}/checklist-items`, { method: "POST", body: JSON.stringify({ title, expectedRevision: demand.revision }) }); onSaved(updated); form.reset(); await load(); }
    catch (caught) { setError(messageFrom(caught)); await load(); } finally { setBusyId(""); }
  }
  async function remove(item: DemandChecklist["items"][number]) {
    setBusyId(item.id); setError("");
    try { const updated = await api<Demand>(`/demands/${demand.id}/checklist-items/${item.id}`, { method: "DELETE", body: JSON.stringify({ expectedRevision: demand.revision }) }); onSaved(updated); await load(); }
    catch (caught) { setError(messageFrom(caught)); await load(); } finally { setBusyId(""); }
  }
  const shellClass = compact ? "overview-block compact-checklist" : "panel work-content-panel";
  if (!checklist && error) return <section className={`${shellClass} feature-preview`}><span>!</span><h3>Não foi possível carregar o checklist</h3><p>{error}</p><button className="secondary compact" onClick={() => void load()}>Tentar novamente</button></section>;
  if (!checklist) return <section className={`${shellClass} feature-loading`}><span className="loader" /></section>;
  const percent = checklist.total ? Math.round((checklist.completed / checklist.total) * 100) : 0;
  return <section className={shellClass}>
    <div className="work-content-head"><div><span className="eyebrow dark">Checklist do card</span><h3>{checklist.stageName ? `Etapa · ${checklist.stageName}` : "Itens a fazer"}</h3>{!compact && <p>O modelo da etapa e os itens livres ficam reunidos nesta lista.</p>}</div><span>{checklist.completed}/{checklist.total} concluídos</span></div>
    {checklist.total > 0 && <div className="checklist-progress"><i><b style={{ width: `${percent}%` }} /></i><strong>{percent}%</strong></div>}
    {error && <div className="work-content-error"><Notice>{error}</Notice></div>}
    <div className="demand-checklist">{checklist.items.map((item) => <label className={item.completed ? "done" : ""} key={`${item.source}:${item.id}`}><input type="checkbox" checked={item.completed} disabled={!canEdit || busyId === item.id} onChange={(event) => void toggle(item, event.target.checked)} /><span><strong>{item.title}{item.required && <b>Obrigatório</b>}</strong>{item.description && <small>{item.description}</small>}{item.completedByName && <em>Concluído por {item.completedByName}</em>}</span>{item.source === "custom" && canEdit && <button type="button" className="checklist-remove" disabled={busyId === item.id} onClick={(event) => { event.preventDefault(); void remove(item); }} aria-label={`Remover ${item.title}`}>×</button>}</label>)}</div>
    {canEdit && <form className="checklist-add" onSubmit={add}><input name="title" minLength={2} maxLength={240} placeholder="+ Adicionar item ao checklist" aria-label="Novo item do checklist" required /><button disabled={busyId === "new"}>{busyId === "new" ? "Adicionando…" : "Adicionar"}</button></form>}
    {!checklist.items.length && <p className="checklist-empty">Adicione um item livre agora. Os modelos configurados para a etapa também aparecem aqui.</p>}
  </section>;
}
function timelineDate(value: string | null): string {
  if (!value) return "Sem previsão";
  return new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function WorkflowTimelineView({ timeline, compact = false, canEdit, busy, onOpen, onAction, onSchedule }: { timeline: DemandTimeline; compact?: boolean; canEdit: boolean; busy: boolean; onOpen?: () => void; onAction?: (action: "advance" | "return" | "skip") => void; onSchedule?: (stageId: string, deadlineAt: string | null, forecastAt: string | null) => Promise<boolean> }) {
  const [editingStageId, setEditingStageId] = useState<string | null>(null);
  const currentIndex = timeline.stages.findIndex((stage) => stage.state === "current");
  const shown = compact && timeline.stages.length > 4 ? timeline.stages.slice(Math.max(0, currentIndex - 1), Math.min(timeline.stages.length, currentIndex + 3)) : timeline.stages;
  const stateNames: Record<DemandTimelineStage["state"], string> = { completed: "Concluída", current: "Em andamento", upcoming: "Prevista", skipped: "Pulada" };
  const riskNames: Record<DemandTimelineStage["risk"], string> = { none: "", overdue: "Prazo vencido", at_risk: "Em risco", on_track: "No prazo", unscheduled: "Sem agenda" };
  return <section className={`${compact ? "overview-block" : "panel work-content-panel"} demand-timeline${compact ? " compact-timeline" : ""}`}>
    <header><div><span className="overview-icon">↗</span><span><strong>{timeline.workflowName}</strong><small>Versão {timeline.version} preservada neste card</small></span></div>{compact && <button className="timeline-version" type="button" onClick={onOpen}>Ver fluxo</button>}</header>
    <div className="demand-timeline-list">{shown.map((stage) => <div key={stage.id} className={`timeline-row ${stage.state}`}><span className="timeline-rail"><i style={{ background: stage.color }} /></span><span className="timeline-copy"><strong>{stage.name}</strong><small>{stage.assigneeName ?? "Sem responsável"} · {stage.expectedDurationHours ? `${stage.expectedDurationHours}h previstas` : "sem duração padrão"}</small>{!compact && <span className="timeline-dates"><small>Prazo: {timelineDate(stage.deadlineAt)}</small><small>Previsão: {timelineDate(stage.forecastAt)}</small></span>}</span><span className="timeline-meta"><b>{stateNames[stage.state]}</b><small>{stage.state === "completed" ? timelineDate(stage.leftAt) : timelineDate(stage.forecastAt)}</small>{stage.risk !== "none" && <em className={`timeline-risk ${stage.risk}`}>{riskNames[stage.risk]}</em>}{!compact && canEdit && <button type="button" className="timeline-edit" disabled={busy} onClick={() => setEditingStageId(editingStageId === stage.id ? null : stage.id)}>⚙ Ajustar</button>}</span>{!compact && editingStageId === stage.id && <form className="timeline-schedule" onSubmit={(event) => { event.preventDefault(); if (!onSchedule) return; const data = new FormData(event.currentTarget); void onSchedule(stage.id, data.get("stageDeadline") ? new Date(String(data.get("stageDeadline"))).toISOString() : null, data.get("stageForecast") ? new Date(String(data.get("stageForecast"))).toISOString() : null).then((saved) => { if (saved) setEditingStageId(null); }); }}><Field label="Prazo da etapa" name="stageDeadline" type="datetime-local" defaultValue={toInputDate(stage.deadlineAt)} /><Field label="Previsão da etapa" name="stageForecast" type="datetime-local" defaultValue={toInputDate(stage.forecastAt)} /><button className="primary compact" disabled={busy}>{busy ? "Salvando…" : "Salvar agenda"}</button></form>}</div>)}</div>
    {compact && timeline.stages.length > shown.length && <footer className="timeline-more">{timeline.stages.length - shown.length} etapas adicionais na visão avançada</footer>}
  </section>;
}

function DemandStageDock({ demand, timeline, people, canEdit, busy, onAction, onReassign }: { demand: Demand; timeline: DemandTimeline; people: Person[]; canEdit: boolean; busy: boolean; onAction: (action: "advance" | "return", targetStageId?: string, comment?: string) => Promise<boolean>; onReassign: (assigneeId: string | null) => Promise<boolean> }) {
  const [expanded, setExpanded] = useState(false);
  const [returnTargetId, setReturnTargetId] = useState<string | null>(null);
  const [comment, setComment] = useState("");
  const currentIndex = timeline.stages.findIndex((stage) => stage.state === "current");
  const current = timeline.stages[currentIndex];
  if (!current) return null;
  const isLast = currentIndex === timeline.stages.length - 1;
  const returnTarget = timeline.stages.find((stage) => stage.id === returnTargetId);
  async function submitReturn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!returnTargetId || comment.trim().length < 3) return;
    if (await onAction("return", returnTargetId, comment.trim())) {
      setComment(""); setReturnTargetId(null); setExpanded(false);
    }
  }
  return <>
    {expanded && <div className="stage-dock-popover">
      <header><div><span>Escolher etapa da demanda</span><strong>{timeline.workflowName}</strong></div><button type="button" onClick={() => { setExpanded(false); setReturnTargetId(null); }}>×</button></header>
      <div className="stage-dock-list">{timeline.stages.map((stage, index) => <div key={stage.id} className={`stage-dock-list-item ${stage.state}${index !== currentIndex ? " actionable" : ""}${stage.id === returnTargetId ? " selected" : ""}`}><button type="button" disabled={!canEdit || busy || index === currentIndex} onClick={() => { if (index < currentIndex) { setComment(""); setReturnTargetId(stage.id); } else { setReturnTargetId(null); void onAction("advance", stage.id).then((saved) => { if (saved) setExpanded(false); }); } }}><i style={{ background: stage.color }} /><span><strong>{stage.name}</strong><small>{stage.assigneeName ?? "Sem responsável"} · {timelineDate(stage.deadlineAt)}</small></span><b>{stage.state === "current" ? "Atual" : index < currentIndex ? "Retornar" : "Mover"}</b></button>{stage.state === "current" && <label className="stage-dock-assignee"><span>Responsável da etapa atual</span><select aria-label="Responsável da etapa atual" value={stage.assigneeId ?? ""} disabled={!canEdit || busy} onChange={(event) => void onReassign(event.target.value || null)}><option value="">Sem responsável</option>{people.map((person) => <option key={person.id} value={person.id}>{person.name}</option>)}</select><small>O prazo vencido será preservado no histórico.</small></label>}</div>)}</div>
      {returnTarget && <form className="stage-return-form" onSubmit={submitReturn}><strong>Retornar para {returnTarget.name}</strong><p>A justificativa será publicada no chat para orientar a pessoa responsável por essa etapa.</p><textarea value={comment} onChange={(event) => setComment(event.target.value)} minLength={3} maxLength={2000} rows={3} placeholder="O que precisa ser corrigido ou melhorado?" autoFocus required /><div><button type="button" onClick={() => setReturnTargetId(null)}>Cancelar</button><button className="primary" disabled={busy || comment.trim().length < 3}>{busy ? "Retornando…" : "Confirmar retorno"}</button></div></form>}
    </div>}
    <aside className="demand-stage-dock">
      <button type="button" className="stage-dock-current" onClick={() => setExpanded((value) => !value)} aria-expanded={expanded}><i style={{ background: current.color }} /><AvatarView name={current.assigneeName ?? "Sem responsável"} url={current.assigneeAvatarUrl} /><span><small>Etapa atual</small><strong>{current.name}</strong><em>{current.assigneeName ?? "Sem responsável"}</em></span><b>⌃</b></button>
      <div className="stage-dock-deadlines"><span><small>Etapa até</small><strong>{timelineDate(current.deadlineAt)}</strong></span><span><small>Demanda até</small><strong>{timelineDate(demand.deadlineAt)}</strong></span></div>
      {canEdit && <button type="button" className="stage-dock-advance" disabled={busy} onClick={() => void onAction("advance")}><span>{isLast ? "✓" : "→"}</span>{busy ? "Atualizando…" : isLast ? "Concluir demanda" : "Concluir etapa"}</button>}
    </aside>
  </>;
}

function DemandDetail({ demand, companies, categories, workflows, people, stages, canEdit, canEditEstimate, canDelete, initialTab, onBack, onSaved, onRemoved }: { demand: Demand; companies: Company[]; categories: Category[]; workflows: Workflow[]; people: Person[]; stages: WorkflowStage[]; canEdit: boolean; canEditEstimate: boolean; canDelete: boolean; initialTab: DemandDetailTab; onBack: () => void; onSaved: (demand: Demand) => void; onRemoved: () => Promise<void> }) {
  const [tab, setTab] = useState<DemandDetailTab>(initialTab);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [timeline, setTimeline] = useState<DemandTimeline | null>(null);
  const [timelineError, setTimelineError] = useState("");
  const [selectedWorkflowId, setSelectedWorkflowId] = useState(demand.workflowId ?? workflows.find((item) => item.isDefault)?.id ?? "");
  useEffect(() => { setTimelineError(""); api<DemandTimeline>(`/demands/${demand.id}/timeline`).then(setTimeline).catch((caught) => setTimelineError(messageFrom(caught))); }, [demand.id, demand.revision]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError(""); setSuccess("");
    const data = new FormData(event.currentTarget); const deadline = String(data.get("deadlineAt") || "");
    const selectedStages = stages.filter((stage) => stage.workflowId === selectedWorkflowId && stage.active).sort((a, b) => a.position - b.position);
    const stageId = selectedWorkflowId === demand.workflowId ? demand.stageId : selectedStages[0]?.id ?? null;
    try {
      const updated = await api<Demand>(`/demands/${demand.id}`, { method: "PUT", body: JSON.stringify({ title: data.get("title"), description: data.get("description") || null, companyId: data.get("companyId") || null, categoryId: data.get("categoryId") || null, workflowId: data.get("workflowId") || null, assigneeId: demand.assigneeId, stageId, priority: data.get("priority"), status: data.get("status"), deadlineAt: deadline ? new Date(deadline).toISOString() : null, expectedRevision: demand.revision }) });
      onSaved(updated); setSuccess("Demanda atualizada.");
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function runWorkflowAction(action: "advance" | "return", targetStageId?: string, comment?: string): Promise<boolean> {
    if (!canEdit) return false;
    setBusy(true); setError(""); setSuccess("");
    try { const updated = await api<Demand>(`/demands/${demand.id}/workflow-actions`, { method: "POST", body: JSON.stringify({ action, targetStageId: targetStageId || null, comment: comment || null, expectedRevision: demand.revision }) }); onSaved(updated); setSuccess(action === "advance" && updated.status === "COMPLETED" ? "Demanda concluída." : `Workflow atualizado: ${updated.stageName}.`); return true; }
    catch (caught) { const message = messageFrom(caught); setError(message); if (message.toLocaleLowerCase().includes("checklist")) setTab("checklist"); return false; } finally { setBusy(false); }
  }
  async function reassignCurrentStage(assigneeId: string | null): Promise<boolean> {
    if (!canEdit) return false;
    setBusy(true); setError(""); setSuccess("");
    try {
      const updated = await api<Demand>(`/demands/${demand.id}/assignee`, { method: "PATCH", body: JSON.stringify({ assigneeId, expectedRevision: demand.revision }) });
      onSaved(updated);
      setSuccess(updated.assigneeName ? `Responsável alterado para ${updated.assigneeName}.` : "A etapa atual ficou sem responsável.");
      return true;
    } catch (caught) { setError(messageFrom(caught)); return false; } finally { setBusy(false); }
  }
  async function saveStageSchedule(stageId: string, deadlineAt: string | null, forecastAt: string | null) {
    if (!canEdit) return false;
    setBusy(true); setError(""); setSuccess("");
    try { const updated = await api<Demand>(`/demands/${demand.id}/timeline/${stageId}`, { method: "PATCH", body: JSON.stringify({ deadlineAt, forecastAt, expectedRevision: demand.revision }) }); onSaved(updated); setSuccess("Agenda da etapa atualizada."); return true; }
    catch (caught) { setError(messageFrom(caught)); return false; } finally { setBusy(false); }
  }
  async function refreshDemandFiles() {
    try { onSaved(await api<Demand>(`/demands/${demand.id}`)); }
    catch (caught) { setError(messageFrom(caught)); }
  }
  async function removeDemand(mode: "archive" | "delete") {
    const message = mode === "archive" ? `Arquivar “${demand.title}”? Ela sairá das áreas operacionais e poderá ser restaurada nas Configurações.` : `Enviar “${demand.title}” para a lixeira? O histórico será preservado e um administrador poderá restaurá-la.`;
    if (!window.confirm(message)) return;
    setBusy(true); setError(""); setSuccess("");
    try {
      if (mode === "archive") await api(`/demands/${demand.id}/archive`, { method: "POST", body: JSON.stringify({ expectedRevision: demand.revision }) });
      else await api(`/demands/${demand.id}?expectedRevision=${demand.revision}`, { method: "DELETE" });
      await onRemoved();
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  async function remove(mode: "archive" | "delete") {
    const message = mode === "archive" ? `Arquivar “${demand.title}”? Ela poderá ser restaurada nas Configurações.` : `Enviar “${demand.title}” para a lixeira recuperável?`;
    if (!window.confirm(message)) return;
    setBusy(true); setError("");
    try {
      if (mode === "archive") await api(`/demands/${demand.id}/archive`, { method: "POST", body: JSON.stringify({ expectedRevision: demand.revision }) });
      else await api(`/demands/${demand.id}?expectedRevision=${demand.revision}`, { method: "DELETE" });
      await onRemoved();
    } catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  const tabs: { id: DemandDetailTab; label: string }[] = [{ id: "overview", label: "Visão geral" }, { id: "briefing", label: "Briefing" }, { id: "checklist", label: "Checklist" }, { id: "workflow", label: "Workflow" }, { id: "activity", label: "Atividade" }, { id: "time", label: "Tempo" }];
  const editForm = <section className="panel detail-form overview-block">
    <div className="overview-section-title"><div><span className="eyebrow dark">Dados essenciais</span><h3>Resumo da demanda</h3></div><span className={`demand-status ${demand.status.toLowerCase()}`}>{statusNames[demand.status]}</span></div>
    <form className="modal-form" onSubmit={save}>
      {error && <Notice>{error}</Notice>}{success && <Notice kind="success">{success}</Notice>}
      <div className="form-grid"><Field label="Título" name="title" defaultValue={demand.title} required /><label className="field"><span>Situação</span><select name="status" defaultValue={demand.status} disabled={!canEdit}>{Object.entries(statusNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label></div>
      <label className="field"><span>Descrição</span><textarea name="description" rows={4} defaultValue={demand.description ?? ""} disabled={!canEdit} /></label>
      <div className="form-grid"><label className="field"><span>Empresa</span><select name="companyId" defaultValue={demand.primaryCompanyId ?? ""} disabled={!canEdit}><option value="">Sem empresa</option>{companies.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="field"><span>Categoria</span><select name="categoryId" defaultValue={demand.categoryId ?? ""} disabled={!canEdit}><option value="">Sem categoria</option>{categories.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div>
      <label className="field"><span>Workflow</span><select name="workflowId" value={selectedWorkflowId} disabled={!canEdit} onChange={(event) => setSelectedWorkflowId(event.target.value)}>{workflows.map((item) => <option key={item.id} value={item.id}>{item.name}{item.isDefault ? " · padrão" : ""}</option>)}</select><small>A troca aplica a primeira etapa do novo fluxo. A etapa e o responsável atual são controlados pela barra inferior.</small></label>
      <div className="form-grid"><label className="field"><span>Prioridade</span><select name="priority" defaultValue={demand.priority} disabled={!canEdit}>{Object.entries(priorityNames).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><Field label="Prazo final da demanda" name="deadlineAt" type="datetime-local" defaultValue={toInputDate(demand.deadlineAt)} disabled={!canEdit} /></div>
      <footer className="form-actions"><span className="revision-note">Revisão {demand.revision}</span><button className="primary action-primary" disabled={busy || !canEdit}>{busy ? "Salvando…" : "Salvar dados"}</button></footer>
    </form>
  </section>;
  return <>
    <button className="back-button" onClick={onBack}>← Voltar</button>
    <section className="demand-detail-head"><div><span className="demand-id">{demand.publicId}</span><h2>{demand.title}</h2><p>{demand.companyName ?? "Sem empresa"} · {demand.categoryName ?? "Sem categoria"}</p></div><div className="detail-head-actions"><span className={`demand-status ${demand.status.toLowerCase()}`}>{statusNames[demand.status]}</span>{canEdit && <button className="secondary compact" disabled={busy} onClick={() => void removeDemand("archive")}>Arquivar</button>}{canDelete && <button className="secondary compact danger-text" disabled={busy} onClick={() => void removeDemand("delete")}>Excluir</button>}</div></section>
    <nav className="detail-tabs" aria-label="Seções da demanda">{tabs.map((item) => <button className={tab === item.id ? "active" : ""} onClick={() => setTab(item.id)} key={item.id}>{item.label}</button>)}</nav>
    {tab !== "overview" && error && <Notice>{error}</Notice>}{tab !== "overview" && success && <Notice kind="success">{success}</Notice>}
    {tab === "overview" ? <div className="demand-overview-layout"><div className="demand-overview-main">{editForm}<FilesPanel demandId={demand.id} canManage={canEdit} compact onFilesChanged={refreshDemandFiles} /><section className="overview-block overview-shortcuts"><header><div><span className="overview-icon">⌘</span><span><strong>Funções do card</strong><small>Acesso às áreas avançadas</small></span></div></header><div><button onClick={() => setTab("briefing")}><b>▤</b><span><strong>Briefing</strong><small>{demand.categoryName ?? "Defina uma categoria"}</small></span></button><button onClick={() => setTab("checklist")}><b>✓</b><span><strong>Checklist</strong><small>Entregas obrigatórias da etapa</small></span></button><button onClick={() => setTab("time")}><b>◷</b><span><strong>Tempo</strong><small>Histórico e lançamentos manuais</small></span></button></div></section></div><aside className="demand-conversation"><ActivityPanel demandId={demand.id} canComment={canEdit} compact /></aside></div>
      : tab === "briefing" ? <BriefingPanel demand={demand} canEdit={canEdit} onSaved={onSaved} />
      : tab === "checklist" ? <ChecklistPanel demand={demand} canEdit={canEdit} onSaved={onSaved} />
      : tab === "workflow" ? timeline ? <WorkflowTimelineView timeline={timeline} canEdit={canEdit} busy={busy} onSchedule={saveStageSchedule} /> : timelineError ? <section className="panel work-content-panel"><Notice>{timelineError}</Notice></section> : <section className="panel feature-loading"><span className="loader" /></section>
      : tab === "activity" ? <ActivityPanel demandId={demand.id} canComment={canEdit} />
      : <TimePanel demandId={demand.id} canTrack={canEdit} canEditEstimate={canEditEstimate} onEstimateSaved={(expectedEffortMinutes, revision) => onSaved({ ...demand, expectedEffortMinutes, revision })} />}
    {timeline && <DemandStageDock demand={demand} timeline={timeline} people={people} canEdit={canEdit} busy={busy} onAction={runWorkflowAction} onReassign={reassignCurrentStage} />}
  </>;
}
function ComingSection({ icon, title, text, items }: { icon: string; title: string; text: string; items: string[] }) {
  return <section className="panel coming-section"><span>{icon}</span><div><h3>{title}</h3><p>{text}</p><ul>{items.map((item) => <li key={item}>✓ {item}</li>)}</ul></div></section>;
}

function PersonalAgenda({ demands, profile, canCreate, onOpen, onCreate }: { demands: Demand[]; profile: Profile | null; canCreate: boolean; onOpen: (demand: Demand) => void; onCreate: () => void }) {
  if (!profile) return <section className="panel agenda-loading"><span className="loader" /></section>;
  const mine = demands.filter((demand) => demand.assigneeId === profile.profileId && demand.status !== "COMPLETED");
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const tomorrow = new Date(today); tomorrow.setDate(tomorrow.getDate() + 1);
  const dateKey = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  const groups = new Map<string, { label: string; tone: string; date: number; items: Demand[] }>();
  function add(key: string, label: string, tone: string, date: number, demand: Demand) {
    const group = groups.get(key) ?? { label, tone, date, items: [] }; group.items.push(demand); groups.set(key, group);
  }
  mine.forEach((demand) => {
    if (!demand.deadlineAt) { add("undated", "Sem prazo", "neutral", Number.MAX_SAFE_INTEGER, demand); return; }
    const due = new Date(demand.deadlineAt); const dueDay = new Date(due); dueDay.setHours(0, 0, 0, 0);
    if (dueDay < today) add("overdue", "Atrasadas!", "danger", -1, demand);
    else if (dateKey(dueDay) === dateKey(today)) add("today", "Hoje", "today", today.getTime(), demand);
    else if (dateKey(dueDay) === dateKey(tomorrow)) add("tomorrow", `Amanhã ${dateLabel(demand.deadlineAt)}`, "tomorrow", tomorrow.getTime(), demand);
    else add(dateKey(dueDay), new Intl.DateTimeFormat("pt-BR", { weekday: "long", day: "2-digit", month: "2-digit", year: "numeric" }).format(dueDay), "future", dueDay.getTime(), demand);
  });
  const ordered = [...groups.values()].sort((a, b) => a.date - b.date);
  ordered.forEach((group) => group.items.sort((a, b) => String(a.deadlineAt).localeCompare(String(b.deadlineAt)) || a.title.localeCompare(b.title)));
  function startTimer(demandId: string) { window.dispatchEvent(new CustomEvent("fluxo:timer-start-request", { detail: { demandId } })); }
  return <div className="personal-agenda"><section className="agenda-hero"><div><span className="eyebrow">Minha agenda</span><h2>Olá, {profile.name.split(" ")[0]}.</h2><p>Veja o que precisa da sua atenção em ordem de entrega.</p></div><div><strong>{mine.length}</strong><span>{mine.length === 1 ? "demanda aberta" : "demandas abertas"}</span>{canCreate && <button onClick={onCreate}><ActionIcon src={additionalActionIcon} /> Nova demanda</button>}</div></section>
    {ordered.length ? <div className="agenda-groups">{ordered.map((group) => <section className={`agenda-group ${group.tone}`} key={`${group.label}:${group.date}`}><header><div><span /><h3>{group.label}</h3></div><b>{group.items.length}</b></header><div>{group.items.map((demand) => <article className="agenda-row" key={demand.id}>{canCreate && <button className="agenda-timer" type="button" onClick={() => startTimer(demand.id)} aria-label={`Iniciar timer de ${demand.title}`} title="Iniciar timer"><ActionIcon src={playActionIcon} /></button>}<button className="agenda-row-open" type="button" onClick={() => onOpen(demand)}><span className={`agenda-check ${demand.status === "IN_PROGRESS" ? "active" : ""}`} /><span className="agenda-copy"><strong>{demand.title}</strong><small>{demand.publicId} · {demand.companyName ?? "Sem empresa"} · {demand.stageName ?? "Sem etapa"}</small></span><span className={`priority priority-${demand.priority.toLowerCase()}`}>{priorityNames[demand.priority]}</span><time>{demand.deadlineAt ? new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(new Date(demand.deadlineAt)) : "—"}</time><span className="agenda-arrow">›</span></button></article>)}</div></section>)}</div> : <section className="panel agenda-empty"><span>✓</span><h3>Sua agenda está livre</h3><p>As demandas atribuídas a você aparecerão aqui, organizadas por data.</p>{canCreate && <button className="primary compact" onClick={onCreate}>+ Criar demanda</button>}</section>}
  </div>;
}

function Dashboard({ session, logout, onSession }: { session: Session; logout: () => void; onSession: (session: Session) => void }) {
  const adminPages: WorkspacePage[] = ["workflows", "categories", "users", "settings"];
  const adminOnlyPages: WorkspacePage[] = ["settings"];
  const canManage = session.role === "admin" || session.role === "coordinator"; const canCreate = session.role !== "viewer";
  const canOpenPage = (value: WorkspacePage) => (canManage || !adminPages.includes(value)) && (session.role === "admin" || !adminOnlyPages.includes(value));
  const initialPage = pageFromLocation();
  const [page, setPage] = useState<WorkspacePage>(canOpenPage(initialPage) ? initialPage : "overview");
  const [companies, setCompanies] = useState<Company[]>([]); const [categories, setCategories] = useState<Category[]>([]); const [workflows, setWorkflows] = useState<Workflow[]>([]); const [managedWorkflows, setManagedWorkflows] = useState<Workflow[]>([]); const [stages, setStages] = useState<WorkflowStage[]>([]); const [workflowStages, setWorkflowStages] = useState<WorkflowStage[]>([]); const [people, setPeople] = useState<Person[]>([]); const [users, setUsers] = useState<User[]>([]); const [demands, setDemands] = useState<Demand[]>([]); const [imports, setImports] = useState<DailyImport[]>([]); const [profile, setProfile] = useState<Profile | null>(null); const [error, setError] = useState(""); const [showImport, setShowImport] = useState(false); const [showCreate, setShowCreate] = useState(false); const [resumeImport, setResumeImport] = useState<DailyImport | null>(null); const [catalogModal, setCatalogModal] = useState<{ kind: "company" | "category"; item?: Company | Category | null } | null>(null); const [briefingCategory, setBriefingCategory] = useState<Category | null>(null); const [selectedDemand, setSelectedDemand] = useState<Demand | null>(null); const [drawerDemand, setDrawerDemand] = useState<Demand | null>(null); const [approvalRoles, setApprovalRoles] = useState<Record<string, string>>({}); const [accessRoles, setAccessRoles] = useState<Record<string, string>>({}); const [approvingUser, setApprovingUser] = useState(""); const [savingUser, setSavingUser] = useState(""); const [removingCompany, setRemovingCompany] = useState("");
  const [jobRoles, setJobRoles] = useState<JobRole[]>([]); const [roleAssignments, setRoleAssignments] = useState<JobRoleAssignment[]>([]);
  const [selectedDemandTab, setSelectedDemandTab] = useState<DemandDetailTab>("overview"); const [showQuickCapture, setShowQuickCapture] = useState(false);
  const [pageLoading, setPageLoading] = useState(true);
  const [pageLoadError, setPageLoadError] = useState("");
  const loadedPages = useRef(new Set<WorkspacePage>());
  const routeRequest = useRef(0);
  const publishedWorkflows = workflows.filter((workflow) => workflow.lifecycleState === "PUBLISHED");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => window.localStorage.getItem("fluxo.sidebar-collapsed") === "true");
  function go(next: WorkspacePage, replace = false) {
    if (!canOpenPage(next)) next = "overview";
    setPage(next); setSelectedDemand(null); setSelectedDemandTab("overview"); setDrawerDemand(null);
    const url = pageUrl(next);
    if (`${window.location.pathname}${window.location.search}` !== url || window.location.hash) {
      window.history[replace ? "replaceState" : "pushState"]({ page: next }, "", url);
    }
    window.scrollTo({ top: 0 });
  }
  function openDemand(demand: Demand, tab: DemandDetailTab = "overview") {
    setSelectedDemandTab(tab); setSelectedDemand(demand);
    if (!loadedPages.current.has("demands")) {
      void loadRouteData("demands", false, false).catch((caught) => setError(messageFrom(caught)));
    }
  }
  async function openReportDemand(demandId: string) {
    const local = demands.find((item) => item.id === demandId);
    if (local) { openDemand(local); return; }
    setError("");
    try { openDemand(await api<Demand>(`/demands/${demandId}`)); }
    catch (caught) { setError(messageFrom(caught)); }
  }
  function applyWorkspaceData(data: WorkspacePageData) {
    if (data.companies) setCompanies(data.companies);
    if (data.categories) setCategories(data.categories);
    if (data.workflows) setWorkflows(data.workflows);
    if (data.stages) setStages(data.stages);
    if (data.people) setPeople(data.people);
    if (data.demands) setDemands(data.demands);
    setProfile(data.profile);
  }
  async function loadRouteData(target: WorkspacePage, force = false, foreground = true) {
    if (!force && loadedPages.current.has(target)) { if (foreground) { setPageLoading(false); setPageLoadError(""); } return; }
    const request = foreground ? ++routeRequest.current : routeRequest.current;
    if (foreground) { setPageLoading(true); setPageLoadError(""); }
    try {
      const data = await api<WorkspacePageData>(`/workspace/pages/${target}`);
      applyWorkspaceData(data);
      loadedPages.current.add(target);
    } catch (caught) {
      if (foreground && request === routeRequest.current) setPageLoadError(messageFrom(caught));
      throw caught;
    } finally {
      if (foreground && request === routeRequest.current) setPageLoading(false);
    }
  }
  async function loadPageData(target: WorkspacePage) {
    if (!canManage) return;
    if (target === "workflows") {
      const [nextWorkflows, nextStages, nextRoles, nextAssignments] = await Promise.all([
        api<Workflow[]>("/catalogs/workflows?includeDraft=true"),
        api<WorkflowStage[]>("/catalogs/workflow-stages?includeInactive=true&includeDraft=true&allWorkflows=true"),
        api<JobRole[]>("/catalogs/job-roles"),
        api<JobRoleAssignment[]>("/catalogs/job-role-assignments"),
      ]);
      setManagedWorkflows(nextWorkflows); setWorkflowStages(nextStages); setJobRoles(nextRoles); setRoleAssignments(nextAssignments);
    } else if (target === "users" || target === "team") {
      setUsers(await api<User[]>("/users"));
    } else if (target === "intelligence") {
      setImports(await api<DailyImport[]>("/imports/dailys"));
    }
  }
  async function loadData() {
    setError("");
    loadedPages.current.clear();
    try { await Promise.all([loadRouteData(page, true), loadPageData(page)]); }
    catch (caught) { setError(messageFrom(caught)); }
  }
  async function openCreateDemand() {
    setError("");
    try { await loadRouteData("demands", false, false); setShowCreate(true); }
    catch (caught) { setError(messageFrom(caught)); }
  }
  useEffect(() => { setError(""); void loadRouteData(page).catch(() => undefined); }, [page]);
  useEffect(() => { void loadPageData(page).catch((caught) => setError(messageFrom(caught))); }, [page, session.role]);
  useEffect(() => { window.localStorage.setItem("fluxo.sidebar-collapsed", String(sidebarCollapsed)); }, [sidebarCollapsed]);
  useEffect(() => {
    const legacyRoute = window.location.hash && workspacePages.includes(window.location.hash.replace(/^#\/?/, "").split("/")[0] as WorkspacePage);
    if (legacyRoute || window.location.pathname === "/") go(page, true);
    const listener = () => {
      const value = pageFromLocation();
      const allowed = canOpenPage(value) ? value : "overview";
      setPage(allowed); setSelectedDemand(null); setSelectedDemandTab("overview"); setDrawerDemand(null);
      if (allowed !== value) window.history.replaceState({ page: allowed }, "", pageUrl(allowed));
    };
    window.addEventListener("popstate", listener);
    return () => window.removeEventListener("popstate", listener);
  }, [canManage, session.role]);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape" && showQuickCapture) { setShowQuickCapture(false); return; }
      if (!canCreate || event.key.toLocaleLowerCase() !== "q" || event.ctrlKey || event.metaKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, [contenteditable='true']") || showCreate || showImport || catalogModal || briefingCategory || drawerDemand) return;
      event.preventDefault(); setShowQuickCapture(true);
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [canCreate, showQuickCapture, showCreate, showImport, catalogModal, briefingCategory, drawerDemand]);
  async function approveUser(user: User) { setApprovingUser(user.id); setError(""); try { await api(`/users/${user.id}/approve`, { method: "POST", body: JSON.stringify({ role: approvalRoles[user.id] ?? "collaborator", expectedRevision: user.revision }) }); await loadData(); } catch (caught) { setError(messageFrom(caught)); } finally { setApprovingUser(""); } }
  async function updateUserAccess(user: User, state: "active" | "suspended") { setSavingUser(user.id); setError(""); try { await api(`/users/${user.id}`, { method: "PUT", body: JSON.stringify({ role: accessRoles[user.id] ?? user.role ?? "collaborator", state, expectedRevision: user.revision }) }); await loadData(); } catch (caught) { setError(messageFrom(caught)); } finally { setSavingUser(""); } }
  async function removeCompany(company: Company) {
    if (!window.confirm(`Excluir “${company.name}” dos cadastros ativos? Cards e relatórios históricos continuarão preservados.`)) return;
    setRemovingCompany(company.id); setError("");
    try { await api(`/catalogs/companies/${company.id}?expectedRevision=${company.revision}`, { method: "DELETE" }); await loadData(); }
    catch (caught) { setError(messageFrom(caught)); } finally { setRemovingCompany(""); }
  }
  async function savePreferences(preferences: ViewPreferences) {
    if (!profile) return;
    setProfile({ ...profile, preferences });
    try { const updated = await api<Profile>("/users/me/preferences", { method: "PUT", body: JSON.stringify(preferences) }); setProfile(updated); }
    catch (caught) { setError(messageFrom(caught)); setProfile(profile); }
  }
  async function quickCreate(title: string, deadlineAt: string | null) {
    if (!profile) throw new Error("Seu perfil ainda está carregando.");
    const created = await api<Demand>("/demands", { method: "POST", body: JSON.stringify({ title, description: null, companyId: null, categoryId: null, assigneeId: profile.profileId, stageId: null, workflowId: null, priority: "NORMAL", deadlineAt }) });
    setDemands((items) => [created, ...items]); setDrawerDemand(created);
  }
  async function moveDemand(demand: Demand, stageId: string) {
    setError("");
    try { const updated = await api<Demand>(`/demands/${demand.id}/stage`, { method: "PATCH", body: JSON.stringify({ stageId, expectedRevision: demand.revision }) }); setDemands((items) => items.map((item) => item.id === updated.id ? updated : item)); if (selectedDemand?.id === updated.id) setSelectedDemand(updated); }
    catch (caught) { setError(messageFrom(caught)); }
  }
  const pending = useMemo(() => users.filter((user) => user.state === "pending_approval"), [users]);
  const navigation: { label: string; links: { id: WorkspacePage; icon: string; label: string; badge?: number; beta?: boolean }[] }[] = [
    { label: "Trabalho", links: [{ id: "overview", icon: homeIcon, label: "Início" }, { id: "my-work", icon: myWorkIcon, label: "Meu trabalho" }, { id: "demands", icon: demandsIcon, label: "Demandas" }, { id: "calendar", icon: calendarIcon, label: "Calendário" }] },
    { label: "Organização", links: [{ id: "companies", icon: companiesIcon, label: "Empresas" }, { id: "team", icon: teamIcon, label: "Equipe" }, { id: "reports", icon: reportsIcon, label: "Relatórios" }] },
    { label: "Inteligência", links: [{ id: "intelligence", icon: dailyIcon, label: "Dailys", badge: imports.filter((item) => item.state === "reviewing").length, beta: true }] },
    ...(canManage ? [{ label: "Administração", links: [{ id: "workflows" as WorkspacePage, icon: workflowIcon, label: "Workflows" }, { id: "categories" as WorkspacePage, icon: categoriesIcon, label: "Categorias" }, { id: "users" as WorkspacePage, icon: accessIcon, label: "Acessos", badge: pending.length }, ...(session.role === "admin" ? [{ id: "settings" as WorkspacePage, icon: settingsIcon, label: "Configurações" }] : [])] }] : []),
  ];
  let content: React.ReactNode;
  if (selectedDemand) content = <DemandDetail demand={selectedDemand} companies={companies} categories={categories} workflows={publishedWorkflows} people={people} stages={stages} canEdit={canCreate} canEditEstimate={canManage} canDelete={canManage} initialTab={selectedDemandTab} onBack={() => { setSelectedDemand(null); go(page === "overview" || page === "calendar" || page === "my-work" || page === "reports" ? page : "demands"); }} onSaved={(updated) => { setSelectedDemand(updated); setDemands((items) => items.map((item) => item.id === updated.id ? updated : item)); }} onRemoved={async () => { setSelectedDemand(null); await loadData(); }} />;
  else if (pageLoading) content = <section className="panel feature-loading route-loading"><span className="loader" /><p>Carregando {pageTitles[page].toLocaleLowerCase("pt-BR")}…</p></section>;
  else if (pageLoadError) content = <section className="panel route-load-error"><h3>Não foi possível carregar esta página</h3><p>{pageLoadError}</p><button className="primary compact" type="button" onClick={() => void loadRouteData(page, true).catch(() => undefined)}>Tentar novamente</button></section>;
  else if (page === "overview") content = <PersonalAgenda demands={demands} profile={profile} canCreate={canCreate} onOpen={(demand) => openDemand(demand)} onCreate={() => void openCreateDemand()} />;
  else if (page === "demands" || page === "my-work") content = <WorkBoard demands={demands} stages={stages} people={people} companies={companies} profile={profile} mine={page === "my-work"} canEdit={canCreate} onOpen={page === "my-work" ? setDrawerDemand : openDemand} onPreferenceChange={(preferences) => void savePreferences(preferences)} onCalendar={() => go("calendar")} />;
  else if (page === "calendar") content = <CalendarRoute demands={demands} companies={companies} people={people} onOpen={(demand) => openDemand(demand)} />;
  else if (page === "companies") content = <section className="panel page-panel"><div className="panel-head"><div><span className="eyebrow dark">Cadastros ativos</span><h3>Empresas atendidas</h3></div>{canManage && <button className="small-button" onClick={() => setCatalogModal({ kind: "company" })}>+ Nova empresa</button>}</div>{companies.length ? <div className="entity-cards">{companies.map((company) => <article key={company.id}><i style={{ background: company.color }} /><div><strong>{company.name}</strong><span>{company.shortName} · {company.code}</span><p>{company.description || "Sem descrição cadastrada."}</p></div>{canManage && <div className="entity-actions"><button className="table-action" onClick={() => setCatalogModal({ kind: "company", item: company })}>Editar</button><button className="table-action danger-text" disabled={removingCompany === company.id} onClick={() => void removeCompany(company)}>{removingCompany === company.id ? "Excluindo…" : "Excluir"}</button></div>}</article>)}</div> : <div className="empty-state"><span>▦</span><h3>Nenhuma empresa cadastrada</h3></div>}</section>;
  else if (page === "team") content = <><ComingSection icon="○" title="Diretório da equipe" text="A estrutura visual está preparada para cargos, capacidade e distribuição de trabalho." items={["Perfil e foto individual", "Cargo e papel de acesso", "Capacidade por período"]} />{canManage && users.length > 0 && <section className="panel full"><div className="panel-head"><div><span className="eyebrow dark">Pessoas cadastradas</span><h3>Equipe atual</h3></div><span className="count">{users.length}</span></div><div className="table-wrap"><table><thead><tr><th>Nome</th><th>E-mail</th><th>Situação</th><th>Perfil</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td>{user.name}</td><td>{user.email}</td><td><span className={`state ${user.state}`}>{user.state === "active" ? "Ativo" : user.state === "suspended" ? "Suspenso" : "Pendente"}</span></td><td>{user.role ? roleNames[user.role] : "A definir"}</td></tr>)}</tbody></table></div></section>}</>;
  else if (page === "reports") content = <ReportsRoute canViewTeam={canManage} people={people} onOpen={(demandId) => void openReportDemand(demandId)} />;
  else if (page === "intelligence") content = <section className="panel page-panel"><div className="intelligence-hero"><div><span className="beta-chip">Beta</span><h3>Importação assistida de Dailys</h3><p>Envie um JSON analisado e escolha, item por item, qual card receberá a informação. Nenhuma alteração é aplicada sem sua revisão.</p></div>{canManage && <button className="primary action-primary" onClick={() => { setResumeImport(null); setShowImport(true); }}>Importar JSON</button>}</div>{imports.length ? <div className="table-wrap"><table><thead><tr><th>Relatório</th><th>Progresso</th><th>Situação</th><th>Ação</th></tr></thead><tbody>{imports.map((item) => <tr key={item.id}><td><strong>{item.sourceLabel}</strong><small className="table-subtitle">{item.filename}</small></td><td>{item.reviewedItems} de {item.totalItems}</td><td><span className={`import-state ${item.state}`}>{item.state === "applied" ? "Aplicada" : "Em revisão"}</span></td><td>{item.state === "reviewing" ? <button className="table-action" onClick={() => { setResumeImport(item); setShowImport(true); }}>Continuar revisão</button> : "Concluída"}</td></tr>)}</tbody></table></div> : <div className="empty-state"><span>◇</span><h3>Nenhuma importação realizada</h3><p>Este recurso complementa o trabalho manual quando houver um relatório estruturado.</p></div>}</section>;
  else if (page === "categories") content = <section className="panel page-panel"><div className="panel-head"><div><span className="eyebrow dark">Estrutura de entrada</span><h3>Categorias, briefings e workflows</h3></div><button className="small-button" onClick={() => setCatalogModal({ kind: "category" })}>+ Nova categoria</button></div><div className="category-table">{categories.map((category) => <article key={category.id}><i style={{ background: category.color }} /><span><strong>{category.name}</strong><small>{category.code} · {workflows.find((workflow) => workflow.id === category.defaultWorkflowId)?.name ?? "Sem workflow padrão"}</small></span><div><button onClick={() => setBriefingCategory(category)}>Briefing</button><button onClick={() => setCatalogModal({ kind: "category", item: category })}>Editar</button></div></article>)}</div><div className="scope-note"><strong>Entrada padronizada</strong><span>Cada categoria combina seu briefing e workflow padrão. Um card ainda pode usar outro workflow quando necessário.</span></div></section>;
  else if (page === "users") content = <section className="panel page-panel"><div className="panel-head"><div><span className="eyebrow dark">Controle de acesso</span><h3>Usuários</h3><p className="panel-help">Administradores podem alterar o perfil ou suspender o acesso. A suspensão encerra as sessões abertas.</p></div><span className="count">{users.length}</span></div>{users.length ? <div className="table-wrap"><table><thead><tr><th>Nome</th><th>E-mail</th><th>Situação</th><th>Perfil</th><th>Ação</th></tr></thead><tbody>{users.map((user) => <tr key={user.id}><td><span className="user-cell"><AvatarView name={user.name} url={user.avatarUrl} /><strong>{user.name}</strong></span></td><td>{user.email}</td><td><span className={`state ${user.state}`}>{user.state === "active" ? "Ativo" : user.state === "suspended" ? "Suspenso" : "Pendente"}</span></td><td>{session.role === "admin" ? <select className="role-select" value={user.state === "pending_approval" ? approvalRoles[user.id] ?? "collaborator" : accessRoles[user.id] ?? user.role ?? "collaborator"} onChange={(event) => user.state === "pending_approval" ? setApprovalRoles((values) => ({ ...values, [user.id]: event.target.value })) : setAccessRoles((values) => ({ ...values, [user.id]: event.target.value }))}><option value="collaborator">Colaborador</option><option value="coordinator">Coordenador</option><option value="viewer">Visualizador</option><option value="admin">Administrador</option></select> : user.role ? roleNames[user.role] : "Definir"}</td><td>{user.state === "pending_approval" && session.role === "admin" ? <button className="table-action" disabled={approvingUser === user.id} onClick={() => void approveUser(user)}>{approvingUser === user.id ? "Liberando…" : "Liberar acesso"}</button> : session.role === "admin" ? <div className="access-actions"><button className="table-action" disabled={savingUser === user.id} onClick={() => void updateUserAccess(user, user.state === "suspended" ? "suspended" : "active")}>{savingUser === user.id ? "Salvando…" : "Salvar perfil"}</button><button className={user.state === "suspended" ? "access-restore" : "access-remove"} disabled={savingUser === user.id} onClick={() => void updateUserAccess(user, user.state === "suspended" ? "active" : "suspended")}>{user.state === "suspended" ? "Reativar" : "Remover acesso"}</button></div> : "—"}</td></tr>)}</tbody></table></div> : <div className="empty-state"><p>Nenhum usuário cadastrado.</p></div>}</section>;
  else if (page === "profile") content = <ProfilePage profile={profile} session={session} onUpdated={(updated) => { setProfile(updated); onSession({ ...session, name: updated.name }); }} />;
  else if (page === "workflows") content = <WorkflowRoute workflows={managedWorkflows.length ? managedWorkflows : workflows} stages={workflowStages} demands={demands} categories={categories} people={people} roles={jobRoles} roleAssignments={roleAssignments} canPrepare={session.role === "admin"} onReload={loadData} />;
  else content = <GovernanceSettingsRoute onReload={loadData} />;
  return <div className={`app-shell${sidebarCollapsed ? " sidebar-collapsed" : ""}`} style={themeStyle(profile?.preferences)}>
    <aside className={`sidebar${sidebarCollapsed ? " collapsed" : ""}`}><div className="sidebar-head"><Brand /><button className="sidebar-toggle" type="button" onClick={() => setSidebarCollapsed((value) => !value)} aria-label={sidebarCollapsed ? "Expandir menu lateral" : "Recolher menu lateral"} aria-expanded={!sidebarCollapsed} title={sidebarCollapsed ? "Expandir menu" : "Recolher menu"}><span aria-hidden="true" /></button></div><nav aria-label="Navegação principal">{navigation.map((group) => <div className="nav-group" key={group.label}><small>{group.label}</small>{group.links.map((link) => <a key={link.id} href={pageUrl(link.id)} className={!selectedDemand && page === link.id ? "active" : ""} onPointerEnter={() => preloadPageModule(link.id)} onFocus={() => preloadPageModule(link.id)} onClick={(event) => { event.preventDefault(); go(link.id); }} aria-label={sidebarCollapsed ? link.label : undefined} title={sidebarCollapsed ? link.label : undefined}><NavIcon src={link.icon} /><span className="nav-label">{link.label}</span>{link.beta && <em>Beta</em>}{Boolean(link.badge) && <b>{link.badge}</b>}</a>)}</div>)}</nav><div className="side-profile"><button className="profile-trigger" onClick={() => go("profile")} aria-label={sidebarCollapsed ? "Abrir meu perfil" : undefined} title={sidebarCollapsed ? "Meu perfil" : undefined}><AvatarView name={profile?.name ?? session.name} url={profile?.avatarUrl} /><span><strong>{profile?.name ?? session.name}</strong><small>{session.role ? roleNames[session.role] : "Sem perfil"}</small></span></button><button className="logout-button" onClick={logout} aria-label="Sair" title="Sair">↗</button></div></aside>
    <main className={`workspace${selectedDemand ? " demand-open" : ""}`}>{!selectedDemand && <header><h1>{pageTitles[page]}</h1>{canCreate && <div className="workspace-header-actions"><button className="quick-capture-button" onClick={() => setShowQuickCapture(true)}><ActionIcon src={fastActionIcon} /> Captura rápida <kbd>Q</kbd></button><button className="new-demand-button" onClick={() => void openCreateDemand()}><ActionIcon src={additionalActionIcon} /> Nova demanda</button></div>}</header>}{error && <Notice>{error}</Notice>}<Suspense fallback={<section className="panel feature-loading route-loading"><span className="loader" /></section>}>{content}</Suspense></main>
    <GlobalTimer currentDemand={selectedDemand ?? drawerDemand} canTrack={canCreate} hasStageDock={Boolean(selectedDemand)} hasDrawerFooter={Boolean(drawerDemand)} onOpenDemand={(demandId) => { const target = demands.find((item) => item.id === demandId); if (target) { openDemand(target); setDrawerDemand(null); } }} />
    {drawerDemand && <TaskDrawer key={drawerDemand.id} demand={drawerDemand} companies={companies} categories={categories} people={people} stages={stages} canEdit={canCreate} canDelete={canManage} onClose={() => setDrawerDemand(null)} onOpenFull={(tab) => { openDemand(drawerDemand, tab); setDrawerDemand(null); }} onSaved={(updated) => { setDrawerDemand(updated); setDemands((items) => items.map((item) => item.id === updated.id ? updated : item)); }} onRemoved={async () => { setDrawerDemand(null); await loadData(); }} />}
    {showQuickCapture && <QuickCaptureModal onClose={() => setShowQuickCapture(false)} onCreate={quickCreate} />}
    {showCreate && <ManualDemandModal companies={companies} categories={categories} workflows={publishedWorkflows} people={people} stages={stages} onClose={() => setShowCreate(false)} onCreated={(created) => { setDemands((items) => [created, ...items]); setShowCreate(false); go("demands"); openDemand(created); }} />}
    {catalogModal && <CatalogModal kind={catalogModal.kind} item={catalogModal.item} workflows={publishedWorkflows} onClose={() => setCatalogModal(null)} onSaved={loadData} />}
    {briefingCategory && <BriefingTemplateModal category={briefingCategory} onClose={() => setBriefingCategory(null)} />}
    {showImport && <DailyImportModal demands={demands} initialImport={resumeImport} onClose={() => { setShowImport(false); setResumeImport(null); void loadData(); }} onApplied={() => { void loadData(); }} />}
  </div>;
}

export default function WorkspaceApp({ session, logout, onSession }: { session: Session; logout: () => void; onSession: (session: Session) => void }) {
  return <Dashboard session={session} logout={logout} onSession={onSession} />;
}
