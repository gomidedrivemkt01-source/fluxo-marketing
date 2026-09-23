import { describe, expect, it } from "vitest";
import { messageFrom } from "./api";

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
