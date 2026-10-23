export type Session = {
  state: "pending_approval" | "active" | "suspended";
  name: string;
  email: string;
  role: "admin" | "coordinator" | "collaborator" | "viewer" | null;
};

export type ApiError = { code: string; message: string; requestId?: string };
export const AUTH_EXPIRED_EVENT = "fluxo:auth-expired";
const GET_TIMEOUT_MS = 25_000;
const WRITE_TIMEOUT_MS = 90_000;
const GET_RETRIES = 1;

function cookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((part) => part.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=");
}

function transientRequestError(error: unknown): boolean {
  return Boolean(error && typeof error === "object" && "code" in error && error.code === "request_timeout")
    || error instanceof TypeError
    || (error instanceof DOMException && error.name === "AbortError")
    || (error instanceof Error && error.name === "AbortError");
}

async function fetchWithTimeout(path: string, init: RequestInit, timeoutMs: number): Promise<Response> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  init.signal?.addEventListener("abort", abort, { once: true });
  const timeout = globalThis.setTimeout(abort, timeoutMs);
  try {
    return await fetch(`/api/v1${path}`, { ...init, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted && !init.signal?.aborted) {
      throw Object.assign(new Error("O servidor demorou para responder. Tente novamente."), { code: "request_timeout" });
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeout);
    init.signal?.removeEventListener("abort", abort);
  }
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
  const request = { ...init, headers, credentials: "include" as const };
  const attempts = method === "GET" ? GET_RETRIES + 1 : 1;
  let response: Response | undefined;
  let lastError: unknown;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      response = await fetchWithTimeout(path, request, method === "GET" ? GET_TIMEOUT_MS : WRITE_TIMEOUT_MS);
      break;
    } catch (error) {
      lastError = error;
      if (init.signal?.aborted || attempt === attempts - 1 || !transientRequestError(error)) throw error;
      await new Promise((resolve) => globalThis.setTimeout(resolve, 600));
    }
  }
  if (!response) throw lastError;
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
