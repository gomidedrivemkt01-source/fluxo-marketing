export type Session = {
  state: "pending_approval" | "active" | "suspended";
  name: string;
  email: string;
  role: "admin" | "coordinator" | "collaborator" | "viewer" | null;
};

export type ApiError = { code: string; message: string; requestId?: string };
export const AUTH_EXPIRED_EVENT = "fluxo:auth-expired";

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
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = cookie("fm_csrf");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: "include" });
  if (!response.ok) {
    const fallback: ApiError = { code: "request_failed", message: "Não foi possível concluir." };
    const detail = (await response.json().catch(() => fallback)) as ApiError;
    if (response.status === 401 && path !== "/auth/session" && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    }
    throw Object.assign(new Error(detail.message), detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function messageFrom(error: unknown): string {
  if (error && typeof error === "object" && "message" in error) {
    const message = String(error.message);
    if (/failed to fetch|networkerror|load failed/i.test(message)) {
      return "Não foi possível conectar ao servidor. Aguarde alguns segundos e tente novamente.";
    }
    return message;
  }
  return "Não foi possível concluir. Tente novamente.";
}
