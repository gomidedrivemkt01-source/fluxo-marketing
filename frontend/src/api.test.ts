import { afterEach, describe, expect, it, vi } from "vitest";
import { api, AUTH_EXPIRED_EVENT, messageFrom } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("messageFrom", () => {
  it("uses the API message", () => {
    expect(messageFrom({ message: "Revise os dados." })).toBe("Revise os dados.");
  });

  it("uses a safe fallback", () => {
    expect(messageFrom(null)).toBe("Não foi possível concluir. Tente novamente.");
  });

  it("explains a temporary connection failure", () => {
    expect(messageFrom(new TypeError("Failed to fetch"))).toBe(
      "Não foi possível conectar ao servidor. Aguarde alguns segundos e tente novamente.",
    );
  });
});

describe("api", () => {
  it("notifies the app when an authenticated request finds an expired session", async () => {
    const browserWindow = new EventTarget();
    const expired = vi.fn();
    browserWindow.addEventListener(AUTH_EXPIRED_EVENT, expired);
    vi.stubGlobal("window", browserWindow);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(
      JSON.stringify({ code: "session_expired", message: "Sua sessão expirou." }),
      { status: 401, headers: { "Content-Type": "application/json" } },
    )));

    await expect(api("/demands")).rejects.toThrow("Sua sessão expirou.");

    expect(expired).toHaveBeenCalledOnce();
  });
});
