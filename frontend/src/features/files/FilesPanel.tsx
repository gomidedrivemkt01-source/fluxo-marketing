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

function previewUrl(demandId: string, fileId: string): string {
  return `/api/v1/demands/${demandId}/files/${fileId}/preview`;
}

export function FilesPanel({ demandId, canManage, compact = false, onFilesChanged }: { demandId: string; canManage: boolean; compact?: boolean; onFilesChanged?: () => void | Promise<void> }) {
  const [files, setFiles] = useState<DemandFile[] | null>(null);
  const [selectedName, setSelectedName] = useState("");
  const [busy, setBusy] = useState("");
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [error, setError] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const imageFiles = files?.filter((item) => item.contentType.startsWith("image/")) ?? [];
  const currentImage = viewerIndex === null ? null : imageFiles[viewerIndex] ?? null;

  async function load() {
    setError("");
    try {
      const loaded = await api<DemandFile[]>(`/demands/${demandId}/files`);
      setFiles(loaded);
    } catch (caught) {
      setError(messageFrom(caught));
    }
  }

  useEffect(() => {
    setFiles(null);
    setViewerIndex(null);
    void load();
  }, [demandId]);

  useEffect(() => {
    if (viewerIndex === null) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setViewerIndex(null);
      if (event.key === "ArrowLeft") navigate(-1);
      if (event.key === "ArrowRight") navigate(1);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [viewerIndex, imageFiles.length]);

  function openViewer(item: DemandFile) {
    const index = imageFiles.findIndex((image) => image.id === item.id);
    if (index >= 0) setViewerIndex(index);
  }

  function navigate(direction: -1 | 1) {
    if (imageFiles.length < 2) return;
    setViewerIndex((current) => current === null ? null : (current + direction + imageFiles.length) % imageFiles.length);
  }

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
      await onFilesChanged?.();
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
      if (currentImage?.id === item.id) {
        const remaining = imageFiles.filter((image) => image.id !== item.id);
        setViewerIndex(remaining.length ? Math.min(viewerIndex ?? 0, remaining.length - 1) : null);
      }
      await onFilesChanged?.();
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

  const viewer = currentImage ? (
    <div className="file-viewer-backdrop" onClick={() => setViewerIndex(null)}>
      <section className="file-viewer" role="dialog" aria-modal="true" aria-label={`Visualização de ${currentImage.name}`} onClick={(event) => event.stopPropagation()}>
        <header>
          <div><strong>{currentImage.name}</strong><span>Imagem {(viewerIndex ?? 0) + 1} de {imageFiles.length}</span></div>
          <button type="button" onClick={() => setViewerIndex(null)} aria-label="Fechar visualização">×</button>
        </header>
        <div className="file-viewer-stage">
          {imageFiles.length > 1 && <button type="button" className="file-viewer-nav previous" onClick={() => navigate(-1)} aria-label="Imagem anterior">‹</button>}
          <img key={currentImage.id} src={previewUrl(demandId, currentImage.id)} alt={currentImage.name} />
          {imageFiles.length > 1 && <button type="button" className="file-viewer-nav next" onClick={() => navigate(1)} aria-label="Próxima imagem">›</button>}
        </div>
        <footer>
          <div><strong>{fileSize(currentImage.sizeBytes)}</strong><span>{currentImage.uploaderName} · {fileDate(currentImage.createdAt)}</span></div>
          <div>
            {currentImage.canDelete && <button type="button" className="file-viewer-delete" disabled={busy === currentImage.id} onClick={() => void remove(currentImage)}>Excluir arquivo</button>}
            <button type="button" className="file-viewer-download" disabled={busy === currentImage.id} onClick={() => void download(currentImage)}>{busy === currentImage.id ? "Preparando…" : "↓ Download"}</button>
          </div>
        </footer>
      </section>
    </div>
  ) : null;

  if (compact) {
    return (
      <><section className="inline-files">
        <header><div><strong>Arquivos e mídias</strong><span>{files.length ? `${files.length} anexado${files.length === 1 ? "" : "s"}` : "Nenhum anexo"}</span></div>{canManage && <form onSubmit={upload}><label className="inline-file-add"><input ref={inputRef} type="file" accept={acceptedTypes} disabled={busy === "upload"} onChange={chooseFile} required /><span>＋</span>{selectedName || "Anexar"}</label>{selectedName && <button disabled={busy === "upload"}>{busy === "upload" ? "Enviando…" : "Enviar"}</button>}</form>}</header>
        {error && <div className="activity-error">{error}</div>}
        {files.length > 0 && <div className="inline-file-grid">{files.slice(0, 8).map((item) => { const image = item.contentType.startsWith("image/"); return <button type="button" key={item.id} onClick={() => image ? openViewer(item) : void download(item)} title={image ? `Visualizar ${item.name}` : `Baixar ${item.name}`}><span>{image ? <img src={previewUrl(demandId, item.id)} alt="" loading="lazy" /> : fileIcon(item.contentType)}</span><small>{item.name}</small></button>; })}</div>}
      </section>{viewer}</>
    );
  }

  return (
    <><section className="panel files-panel">
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
              {item.contentType.startsWith("image/") ? <button type="button" className="file-icon file-open" onClick={() => openViewer(item)} title={`Visualizar ${item.name}`}><img src={previewUrl(demandId, item.id)} alt="" loading="lazy" /></button> : <span className="file-icon">{fileIcon(item.contentType)}</span>}
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
    </section>{viewer}</>
  );
}
