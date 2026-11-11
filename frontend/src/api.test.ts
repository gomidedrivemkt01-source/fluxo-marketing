import { afterEach, describe, expect, it, vi } from "vitest";
import { api, AUTH_EXPIRED_EVENT, messageFrom, WARNING_REVIEW_EVENT, type WarningReviewRequest } from "./api";

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
  it("only retries a warning after explicit acknowledgement and preserves the mutation", async () => {
    vi.stubGlobal("document", {cookie:""});
    const browserWindow = new EventTarget();
    browserWindow.addEventListener(WARNING_REVIEW_EVENT, event=>{const request=(event as CustomEvent<WarningReviewRequest>).detail;request.handled=true;request.resolve(true);});
    vi.stubGlobal("window",browserWindow);
    const request=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({code:"acknowledgement_required",message:"Confira",canProceed:true,warnings:[{code:"deadline_past",field:"deadlineAt",message:"Prazo vencido"}]}),{status:409})).mockResolvedValueOnce(new Response(JSON.stringify({ok:true}),{status:200}));
    vi.stubGlobal("fetch",request);
    await expect(api("/demands/card",{method:"PUT",body:JSON.stringify({expectedRevision:7,title:"Texto"})})).resolves.toEqual({ok:true});
    expect(request).toHaveBeenCalledTimes(2);
    expect(JSON.parse(request.mock.calls[1]![1].body)).toEqual({expectedRevision:7,title:"Texto",acknowledgedWarnings:["deadline_past"]});
  });

  it("does not repeat a write when warning review is cancelled",async()=>{
    vi.stubGlobal("document",{cookie:""});
    const browserWindow=new EventTarget();
    browserWindow.addEventListener(WARNING_REVIEW_EVENT,event=>{const request=(event as CustomEvent<WarningReviewRequest>).detail;request.handled=true;request.resolve(false);});
    vi.stubGlobal("window",browserWindow);
    const request=vi.fn().mockResolvedValue(new Response(JSON.stringify({code:"acknowledgement_required",message:"Confira",canProceed:true,warnings:[{code:"deadline_past",field:"deadlineAt",message:"Prazo vencido"}]}),{status:409}));
    vi.stubGlobal("fetch",request);
    await expect(api("/demands/card",{method:"PUT",body:"{}"})).rejects.toThrow("Confira");
    expect(request).toHaveBeenCalledOnce();
  });
  it("retries a GET once after a temporary network failure", async () => {
    const request = vi.fn()
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    vi.stubGlobal("fetch", request);

    await expect(api<{ ok: boolean }>("/workspace/pages/demands")).resolves.toEqual({ ok: true });
    expect(request).toHaveBeenCalledTimes(2);
  });

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
