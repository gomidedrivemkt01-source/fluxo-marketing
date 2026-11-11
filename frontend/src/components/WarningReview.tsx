import { useEffect, useRef, useState } from "react";
import { WARNING_REVIEW_EVENT, type WarningReviewRequest } from "../api";

export function WarningReview() {
  const [request, setRequest] = useState<WarningReviewRequest | null>(null);
  const [accepted, setAccepted] = useState(false);
  const pending = useRef<WarningReviewRequest | null>(null);
  const box = useRef<HTMLElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  function finish(value: boolean) {
    const current = pending.current;
    pending.current = null;
    setRequest(null);
    current?.resolve(value);
    previousFocus.current?.focus();
  }
  useEffect(() => {
    const listener = (event: Event) => {
      const next = (event as CustomEvent<WarningReviewRequest>).detail;
      next.handled = true;
      if (pending.current) {
        next.resolve(false);
        return;
      }
      previousFocus.current = document.activeElement as HTMLElement;
      pending.current = next;
      setAccepted(false);
      setRequest(next);
    };
    window.addEventListener(WARNING_REVIEW_EVENT, listener);
    return () => {
      window.removeEventListener(WARNING_REVIEW_EVENT, listener);
      pending.current?.resolve(false);
    };
  }, []);
  useEffect(() => {
    if (request)
      box.current?.querySelector<HTMLButtonElement>("button")?.focus();
  }, [request]);
  if (!request) return null;
  return (
    <div className="modal-backdrop warning-review-backdrop">
      <section
        ref={box}
        className="form-modal warning-review"
        role="dialog"
        aria-modal="true"
        aria-labelledby="warning-review-title"
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            finish(false);
          }
          if (event.key === "Tab") {
            const elements = Array.from(
              box.current?.querySelectorAll<HTMLElement>(
                "button:not(:disabled),input",
              ) ?? [],
            );
            const index = elements.indexOf(
              document.activeElement as HTMLElement,
            );
            if (event.shiftKey && index === 0) {
              event.preventDefault();
              elements.at(-1)?.focus();
            } else if (!event.shiftKey && index === elements.length - 1) {
              event.preventDefault();
              elements[0]?.focus();
            }
          }
        }}
      >
        <header className="modal-head">
          <h2 id="warning-review-title">Pendências desta alteração</h2>
          <button
            className="icon-button"
            aria-label="Fechar revisão"
            onClick={() => finish(false)}
          >
            ×
          </button>
        </header>
        <div className="warning-review-body">
          <p>
            Confira o que falta ajustar. Se optar por continuar, sua ciência
            ficará registrada no histórico desta demanda.
          </p>
          <ul>
            {request.warnings.map((item, index) => (
              <li key={item.code ?? index}>
                <strong>*</strong> {item.message}
              </li>
            ))}
          </ul>
          <label className="check">
            <input
              type="checkbox"
              checked={accepted}
              onChange={(event) => setAccepted(event.target.checked)}
            />
            <span>
              Estou ciente das pendências acima e quero seguir mesmo assim.
            </span>
          </label>
        </div>
        <footer className="warning-review-actions">
          <button className="secondary compact" onClick={() => finish(false)}>
            Corrigir campos
          </button>
          <button
            className="primary compact"
            disabled={!accepted}
            onClick={() => finish(true)}
          >
            Seguir mesmo assim
          </button>
        </footer>
      </section>
    </div>
  );
}
