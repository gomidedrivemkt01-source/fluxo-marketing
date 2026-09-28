import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";

import { api, messageFrom } from "../../api";

type DemandFile = {
  id: string;
  name: string;
  contentType: string;
  sizeBytes: number;
  sha256: string;
  uploaderId: string;
  uploaderName: string;
  revision: number;
  canDelete: boolean;
  createdAt: string;
};

type SignedFile = { url: string; expiresAt: string };

const acceptedTypes = [
  ".pdf",
  ".png",
  ".jpg",
  ".jpeg",
  ".webp",
  ".gif",
  ".txt",
  ".md",
  ".csv",
  ".docx",
  ".xlsx",
  ".pptx",
  ".mp3",
  ".wav",
  ".m4a",
  ".mp4",
  ".webm",
  ".mov",
].join(",");

function fileDate(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function fileSize(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function fileIcon(contentType: string): string {
  if (contentType.startsWith("image/")) return "▧";
  if (contentType.startsWith("video/")) return "▶";
  if (contentType.startsWith("audio/")) return "♪";
  if (contentType === "application/pdf") return "PDF";
  return "DOC";
}

export function FilesPanel({ demandId, canManage }: { demandId: string; canManage: boolean }) {
  const [files, setFiles] = useState<DemandFile[] | null>(null);
  const [selectedName, setSelectedName] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  async function load() {
    setError("");
    try {
      setFiles(await api<DemandFile[]>(`/demands/${demandId}/files`));
    } catch (caught) {
      setError(messageFrom(caught));
    }
  }

  useEffect(() => {
    setFiles(null);
    void load();
  }, [demandId]);

  function chooseFile(event: ChangeEvent<HTMLInputElement>) {
    setSelectedName(event.target.files?.[0]?.name ?? "");
  }

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = inputRef.current?.files?.[0];
    if (!file) return;
    const form = event.currentTarget;
    const body = new FormData();
    body.append("file", file);
    setBusy("upload");
    setError("");
    try {
      const created = await api<DemandFile>(`/demands/${demandId}/files`, {
        method: "POST",
        body,
      });
      setFiles((current) => [created, ...(current ?? [])]);
      form.reset();
      setSelectedName("");
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy("");
    }
  }

  async function download(item: DemandFile) {
    setBusy(item.id);
    setError("");
    try {
      const signed = await api<SignedFile>(`/demands/${demandId}/files/${item.id}/download`, {
        method: "POST",
      });
      const anchor = document.createElement("a");
      anchor.href = signed.url;
      anchor.download = item.name;
      anchor.rel = "noopener";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
    } catch (caught) {
      setError(messageFrom(caught));
    } finally {
      setBusy("");
    }
  }

  async function remove(item: DemandFile) {
    if (!window.confirm(`Remover “${item.name}” desta demanda?`)) return;
    setBusy(item.id);
    setError("");
    try {
      await api(`/demands/${demandId}/files/${item.id}`, {
        method: "DELETE",
        body: JSON.stringify({ expectedRevision: item.revision }),
      });
      setFiles((current) => current?.filter((file) => file.id !== item.id) ?? []);
    } catch (caught) {
      setError(messageFrom(caught));
      await load();
    } finally {
      setBusy("");
    }
  }

  if (!files) {
    return (
      <section className="panel files-panel files-loading">
        {error ? (
          <div className="feature-preview">
            <span>!</span>
            <h3>Não foi possível carregar os arquivos</h3>
            <p>{error}</p>
            <button className="secondary compact" onClick={() => void load()}>
              Tentar novamente
            </button>
          </div>
        ) : (
          <span className="loader" aria-label="Carregando arquivos" />
        )}
      </section>
    );
  }

  return (
    <section className="panel files-panel">
      <header className="files-head">
        <div>
          <span className="eyebrow dark">Documentos e mídias</span>
          <h3>Arquivos da demanda</h3>
          <p>Os anexos ficam em um bucket privado e cada download usa um link temporário.</p>
        </div>
        <span>{files.length} {files.length === 1 ? "arquivo" : "arquivos"}</span>
      </header>

      {canManage && (
        <form className="file-uploader" onSubmit={upload}>
          <label className="file-picker">
            <input
              ref={inputRef}
              type="file"
              name="file"
              accept={acceptedTypes}
              disabled={busy === "upload"}
              onChange={chooseFile}
              required
            />
            <span>＋</span>
            <strong>{selectedName || "Escolher arquivo"}</strong>
            <small>PDF, imagens, Office, texto, áudio ou vídeo · até 25 MB</small>
          </label>
          <button className="primary action-primary" disabled={!selectedName || busy === "upload"}>
            {busy === "upload" ? "Enviando…" : "Enviar arquivo"}
          </button>
        </form>
      )}

      {error && <div className="activity-error">{error}</div>}

      {!files.length ? (
        <div className="files-empty">
          <span>◫</span>
          <strong>Nenhum arquivo anexado</strong>
          <p>Briefings, artes, planilhas e entregas podem ser reunidos aqui.</p>
        </div>
      ) : (
        <div className="file-list">
          {files.map((item) => (
            <article key={item.id}>
              <span className="file-icon">{fileIcon(item.contentType)}</span>
              <div className="file-copy">
                <strong title={item.name}>{item.name}</strong>
                <span>{fileSize(item.sizeBytes)} · {item.uploaderName} · {fileDate(item.createdAt)}</span>
                <small title={item.sha256}>SHA-256 {item.sha256.slice(0, 16)}…</small>
              </div>
              <div className="file-actions">
                <button
                  className="secondary compact"
                  disabled={busy === item.id}
                  onClick={() => void download(item)}
                >
                  {busy === item.id ? "Preparando…" : "Baixar"}
                </button>
                {item.canDelete && (
                  <button
                    className="file-remove"
                    disabled={busy === item.id}
                    onClick={() => void remove(item)}
                  >
                    Remover
                  </button>
                )}
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
