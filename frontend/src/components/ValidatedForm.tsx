import { useEffect, useId, useRef, useState, type ComponentProps } from "react";
import { FORM_PROBLEM_EVENT, type FieldProblem } from "../api";

const labels: Record<string, string> = {
  title: "Título",
  description: "Descrição",
  status: "Situação",
  priority: "Prioridade",
  deadlineAt: "Prazo",
  companyId: "Empresa",
  categoryId: "Categoria",
  workflowId: "Workflow",
  stageId: "Etapa",
  assigneeId: "Responsável",
  checklist: "Checklist",
  comment: "Justificativa do retorno",
  forecastAt: "Previsão",
};
type Control = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;

export function ValidatedForm({
  onSubmit,
  children,
  ...props
}: ComponentProps<"form">) {
  const ref = useRef<HTMLFormElement>(null);
  const pending = useRef(false);
  const [problems, setProblems] = useState<FieldProblem[]>([]);
  const prefix = useId();
  function control(field: string): Control | undefined {
    return Array.from(ref.current?.elements ?? []).find(
      (item) => "name" in item && item.name === field,
    ) as Control | undefined;
  }
  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (
        event as CustomEvent<{ fields: FieldProblem[]; form?: Element | null }>
      ).detail;
      if (pending.current && (!detail.form || detail.form === ref.current))
        setProblems(detail.fields);
    };
    window.addEventListener(FORM_PROBLEM_EVENT, listener);
    return () => window.removeEventListener(FORM_PROBLEM_EVENT, listener);
  }, []);
  useEffect(() => {
    const controls: Control[] = [];
    problems.forEach((problem, index) => {
      const item = control(problem.field);
      if (item) {
        item.setAttribute("aria-invalid", "true");
        item.setAttribute("aria-describedby", `${prefix}-${index}`);
        controls.push(item);
      }
    });
    if (controls[0]) {
      controls[0].focus();
      controls[0].scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    return () =>
      controls.forEach((item) => {
        item.removeAttribute("aria-invalid");
        item.removeAttribute("aria-describedby");
      });
  }, [problems]);
  async function submit(
    event: Parameters<NonNullable<ComponentProps<"form">["onSubmit"]>>[0],
  ) {
    event.preventDefault();
    const invalid = Array.from(event.currentTarget.elements)
      .filter(
        (item): item is Control =>
          item instanceof HTMLInputElement ||
          item instanceof HTMLTextAreaElement ||
          item instanceof HTMLSelectElement,
      )
      .filter((item) => !item.disabled && !item.checkValidity());
    if (invalid.length) {
      setProblems(
        invalid.map((item) => ({
          field: item.name,
          message: item.validationMessage || "Confira este campo.",
        })),
      );
      return;
    }
    setProblems([]);
    pending.current = true;
    try {
      await onSubmit?.(event);
    } finally {
      pending.current = false;
    }
  }
  return (
    <form {...props} noValidate ref={ref} onSubmit={submit}>
      {problems.length > 0 && (
        <div className="form-problems" role="alert">
          <strong>Confira os campos marcados com *</strong>
          <ul>
            {problems.map((problem, index) => (
              <li id={`${prefix}-${index}`} key={`${problem.field}-${index}`}>
                <button
                  type="button"
                  onClick={() => {
                    control(problem.field)?.focus();
                    control(problem.field)?.scrollIntoView({
                      block: "center",
                      behavior: "smooth",
                    });
                  }}
                >
                  {labels[problem.field] ??
                    control(problem.field)?.labels?.[0]?.textContent?.replace(
                      "Obrigatório",
                      "",
                    ) ??
                    problem.field}{" "}
                  *
                </button>
                <span>
                  {problem.message || "Confira o valor e o formato informado."}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {children}
    </form>
  );
}
