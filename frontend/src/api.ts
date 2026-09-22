export type Session = {
  state: "pending_approval" | "active" | "suspended";
  name: string;
  email: string;
  role: "admin" | "coordinator" | "collaborator" | "viewer" | null;
};

export type ApiError = { code: string; message: string; requestId?: string };

function cookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((part) => part.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=");
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = cookie("fm_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) {
    const fallback: ApiError = { code: "request_failed", message: "Não foi possível concluir." };
    throw Object.assign(new Error(fallback.message), (await response.json().catch(() => fallback)) as ApiError);
  }
  return (await response.json()) as T;
}

export function messageFrom(error: unknown): string {
  if (error && typeof error === "object" && "message" in error) return String(error.message);
  return "Não foi possível concluir. Tente novamente.";
}
