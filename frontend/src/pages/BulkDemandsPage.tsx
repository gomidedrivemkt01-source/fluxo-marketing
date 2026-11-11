import { useEffect, useState } from "react";
import { api, messageFrom } from "../api";

type Row = {
  index: number;
  externalId: string;
  title: string;
  company: string;
  category: string;
  workflow: string;
  stage: string;
  assignee: string;
  deadlineAt: string | null;
  state: "ready" | "invalid" | "duplicate";
  errors: { field: string; message: string }[];
};
type Preview = {
  rows: Row[];
  ready: number;
  duplicates: number;
  invalid: number;
  previewHash: string;
};
type Result = {
  created: number;
  skipped: number;
  alreadyApplied: boolean;
  demands: { id: string; publicId: string; title: string }[];
};
type Batch = {
  id: string;
  batchId: string;
  createdAt: string;
  created: number;
  skipped: number;
};

export default function BulkDemandsPage({
  canCreate,
  onCreated,
  onShowDemands,
}: {
  canCreate: boolean;
  onCreated: () => void;
  onShowDemands: () => void;
}) {
  const [document, setDocument] = useState<unknown>(null);
  const [filename, setFilename] = useState("");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [result, setResult] = useState<Result | null>(null);
  const [history, setHistory] = useState<Batch[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  async function loadHistory() {
    try {
      setHistory(await api<Batch[]>("/bulk-demands/history"));
    } catch (caught) {
      setError(messageFrom(caught));
    }
  }
  useEffect(() => {
    void loadHistory();
  }, []);
  async function selectFile(file?: File) {
    setPreview(null);
    setResult(null);
    setDocument(null);
    setConfirmed(false);
    setError("");
    setFilename(file?.name ?? "");
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setError("O arquivo deve ter no máximo 5 MB.");
      return;
    }
    try {
      setDocument(JSON.parse((await file.text()).replace(/^\uFEFF/, "")));
    } catch {
      setError(
        "Não foi possível ler o JSON. Envie somente o arquivo JSON válido, sem blocos de Markdown ou textos antes/depois.",
      );
    }
  }
  async function validate() {
    if (!document) return;
    setBusy(true);
    setError("");
    setConfirmed(false);
    setResult(null);
    try {
      setPreview(
        await api<Preview>("/bulk-demands/preview", {
          method: "POST",
          body: JSON.stringify({ document }),
        }),
      );
    } catch (caught) {
      setPreview(null);
      const detail = caught as {
        fieldErrors?: { field: string; message?: string }[];
      };
      setError(
        [
          messageFrom(caught),
          ...(detail.fieldErrors ?? [])
            .slice(0, 12)
            .map(
              (item) =>
                `${item.field}: ${item.message ?? "Confira este campo."}`,
            ),
        ].join("\n"),
      );
    } finally {
      setBusy(false);
    }
  }
  async function apply() {
    if (!document || !preview || !confirmed) return;
    setBusy(true);
    setError("");
    try {
      const value = await api<Result>("/bulk-demands/apply", {
        method: "POST",
        body: JSON.stringify({ document, previewHash: preview.previewHash }),
      });
      setResult(value);
      setConfirmed(false);
      onCreated();
      await loadHistory();
    } catch (caught) {
      setError(messageFrom(caught));
      setConfirmed(false);
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="bulk-page">
      <header className="bulk-heading">
        <div>
          <h2>Demandas em massa</h2>
          <p>
            Transforme uma linha editorial em cards completos, com revisão antes
            de criar.
          </p>
        </div>
        <div className="bulk-model-actions">
          <a
            className="secondary compact"
            href="/api/v1/bulk-demands/model"
            download
          >
            Baixar modelo para o chat
          </a>
          <a
            className="table-action"
            href="/api/v1/bulk-demands/schema"
            download
          >
            JSON Schema
          </a>
        </div>
      </header>
      <div className="bulk-guide">
        <ol>
          <li>
            Baixe o modelo atualizado, com as empresas, categorias, workflows e
            pessoas disponíveis.
          </li>
          <li>
            Envie o arquivo ao chat de conteúdo e peça um card por post,
            seguindo as instruções incluídas no modelo.
          </li>
          <li>
            Envie o JSON gerado, confira as configurações e confirme o lote.
            Cada card mantém seu próprio briefing, checklist e prazo.
          </li>
        </ol>
        <p>
          Até 200 cards e 5 MB por arquivo. Chaves <code>externalId</code>{" "}
          repetidas são ignoradas, sem sobrescrever os cards existentes. Datas
          desconhecidas podem ficar em branco.
        </p>
      </div>
      {error && (
        <div className="notice error bulk-error" role="alert">
          {error}
        </div>
      )}
      {canCreate ? (
        <div className="bulk-upload">
          <label className="field">
            <span>Arquivo JSON da linha editorial</span>
            <input
              type="file"
              accept="application/json,.json"
              disabled={busy}
              onChange={(event) => void selectFile(event.target.files?.[0])}
            />
          </label>
          <button
            className="primary compact"
            disabled={!document || busy}
            onClick={() => void validate()}
          >
            {busy ? "Processando…" : "Validar e revisar"}
          </button>
        </div>
      ) : (
        <p className="scope-note">
          Seu perfil permite consultar e baixar o modelo. A criação exige
          permissão para trabalhar nas demandas.
        </p>
      )}
      {preview && (
        <section className="bulk-review">
          <header>
            <div>
              <h3>Revisão de {filename}</h3>
              <p>
                <strong>{preview.ready}</strong> novas ·{" "}
                <strong>{preview.duplicates}</strong> já existentes ·{" "}
                <strong>{preview.invalid}</strong> com ajustes
              </p>
            </div>
            <span>
              Confira categoria, fluxo, responsável e prazo de cada material.
            </span>
          </header>
          <div className="bulk-rows">
            {preview.rows.map((row) => (
              <article className={`bulk-row ${row.state}`} key={row.externalId}>
                <div className="bulk-row-title">
                  <span className="bulk-row-number">{row.index}</span>
                  <div>
                    <strong>{row.title}</strong>
                    <small>{row.externalId}</small>
                  </div>
                  <b>
                    {row.state === "ready"
                      ? "Nova"
                      : row.state === "duplicate"
                        ? "Já criada"
                        : "Ajustar *"}
                  </b>
                </div>
                <dl>
                  <div>
                    <dt>Empresa / Categoria</dt>
                    <dd>
                      {row.company} · {row.category}
                    </dd>
                  </div>
                  <div>
                    <dt>Workflow / Etapa</dt>
                    <dd>
                      {row.workflow} · {row.stage}
                    </dd>
                  </div>
                  <div>
                    <dt>Responsável</dt>
                    <dd>{row.assignee}</dd>
                  </div>
                  <div>
                    <dt>Entrega</dt>
                    <dd>
                      {row.deadlineAt
                        ? new Intl.DateTimeFormat("pt-BR", {
                            dateStyle: "short",
                            timeStyle: "short",
                          }).format(new Date(row.deadlineAt))
                        : "Sem prazo"}
                    </dd>
                  </div>
                </dl>
                {row.state === "duplicate" ? (
                  <p className="bulk-duplicate-note">
                    Este externalId já foi criado e será preservado, inclusive
                    se o card estiver arquivado ou na lixeira.
                  </p>
                ) : (
                  row.errors.length > 0 && (
                    <ul className="bulk-row-errors">
                      {row.errors.map((item, index) => (
                        <li key={index}>
                          * <strong>{item.field}:</strong> {item.message}
                        </li>
                      ))}
                    </ul>
                  )
                )}
              </article>
            ))}
          </div>
          {!result && (
            <footer className="bulk-confirm">
              <label className="check">
                <input
                  type="checkbox"
                  checked={confirmed}
                  disabled={busy || !!preview.invalid || !preview.ready}
                  onChange={(event) => setConfirmed(event.target.checked)}
                />
                <span>
                  Conferi a prévia e quero criar as {preview.ready} novas
                  demandas.
                </span>
              </label>
              <button
                className="primary compact"
                disabled={
                  !confirmed || busy || !!preview.invalid || !preview.ready
                }
                onClick={() => void apply()}
              >
                Criar {preview.ready} demandas
              </button>
            </footer>
          )}
        </section>
      )}
      {result && (
        <div className="bulk-result notice success" role="status">
          <strong>
            {result.alreadyApplied
              ? "Este lote já havia sido aplicado."
              : `${result.created} demandas criadas.`}
          </strong>
          <span>{result.skipped} chaves já existentes preservadas.</span>
          <button className="secondary compact" onClick={onShowDemands}>
            Ver demandas
          </button>
        </div>
      )}
      <section className="bulk-history panel">
        <div className="panel-head">
          <h3>Histórico de lotes</h3>
          <span>Últimos 50 lotes disponíveis para seu perfil</span>
        </div>
        {history.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Lote</th>
                  <th>Criadas</th>
                  <th>Já existentes</th>
                  <th>Data</th>
                </tr>
              </thead>
              <tbody>
                {history.map((item) => (
                  <tr key={item.id}>
                    <td>{item.batchId}</td>
                    <td>{item.created}</td>
                    <td>{item.skipped}</td>
                    <td>
                      {new Intl.DateTimeFormat("pt-BR", {
                        dateStyle: "short",
                        timeStyle: "short",
                      }).format(new Date(item.createdAt))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="bulk-no-history">
            Nenhum lote registrado para seu perfil.
          </p>
        )}
      </section>
    </section>
  );
}
