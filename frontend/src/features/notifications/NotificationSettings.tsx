import { useEffect, useState, type FormEvent } from "react";
import { api, messageFrom } from "../../api";
import { ValidatedForm } from "../../components/ValidatedForm";
import type { NotificationPolicy } from "./types";

export function NotificationSettings() {
  const [policy, setPolicy] = useState<NotificationPolicy | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  useEffect(() => { api<NotificationPolicy>("/notifications/policy").then(setPolicy).catch(caught => setError(messageFrom(caught))); }, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!policy) return;
    setBusy(true); setError(""); setSuccess("");
    try { setPolicy(await api<NotificationPolicy>("/notifications/policy", { method: "PUT", body: JSON.stringify({ ...policy, expectedRevision: policy.revision }) })); setSuccess("Política de alertas salva para toda a equipe."); window.dispatchEvent(new Event("fluxo:notification-policy-changed")); }
    catch (caught) { setError(messageFrom(caught)); } finally { setBusy(false); }
  }
  return <article className="governance-card notification-settings"><div className="governance-card-head"><div><h4>Alertas operacionais</h4><p>Defina quando cada pessoa deve ser avisada sobre os cards sob sua responsabilidade ou com sua participação.</p></div></div>{error && <div className="notice error" role="alert">{error}</div>}{success && <div className="notice success" role="status">{success}</div>}{policy ? <ValidatedForm className="notification-policy-form" onSubmit={save}>
    <label className="notification-check"><input type="checkbox" disabled={busy} checked={policy.enabled} onChange={event => setPolicy({ ...policy, enabled: event.target.checked })} />Ativar avisos operacionais na plataforma</label>
    <fieldset disabled={!policy.enabled || busy}><legend>Regras de prazo e acompanhamento</legend><label className="field"><span>Alertar quando faltarem menos de quantos dias?</span><input name="warningDays" type="number" min="1" max="90" required value={policy.warningDays} onChange={event => setPolicy({ ...policy, warningDays: Number(event.target.value) })} /><small>O padrão é 7 dias corridos, considerando o prazo final do card.</small></label>
    <label className="notification-check"><input type="checkbox" checked={policy.dueSoon} onChange={event => setPolicy({ ...policy, dueSoon: event.target.checked })} />Avisar quando o prazo estiver próximo</label><label className="notification-check"><input type="checkbox" checked={policy.overdue} onChange={event => setPolicy({ ...policy, overdue: event.target.checked })} />Manter aviso enquanto o prazo estiver vencido</label><label className="notification-check"><input type="checkbox" checked={policy.approvals} onChange={event => setPolicy({ ...policy, approvals: event.target.checked })} />Avisar sobre aprovações pendentes</label><label className="notification-check"><input type="checkbox" checked={policy.includeParticipating} onChange={event => setPolicy({ ...policy, includeParticipating: event.target.checked })} />Acompanhar também cards em que a pessoa já participou de uma etapa</label></fieldset>
    <p className="notification-explanation">Os avisos aparecem no sino de cada usuário e permanecem até a situação ser resolvida. Cards concluídos, arquivados ou excluídos não geram alertas. Não há envio de e-mails nesta configuração.</p><button className="primary action-primary compact" disabled={busy}>{busy ? "Salvando…" : "Salvar política de alertas"}</button>
  </ValidatedForm> : !error && <p className="helper">Carregando a política de alertas…</p>}</article>;
}
