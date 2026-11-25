import { describe, expect, it, vi } from "vitest";
import { createClientId } from "./clientId";

describe("client preference identifiers", () => {
  it("uses native UUIDs when the browser exposes the secure-context method", () => {
    const native = vi.fn(() => "83c76302-64cc-4abe-bf65-23b9ca0e1d1c" as const);
    const random = { randomUUID: native, getRandomValues: vi.fn() };
    expect(createClientId(random)).toBe("83c76302-64cc-4abe-bf65-23b9ca0e1d1c");
    expect(native).toHaveBeenCalledOnce();
    expect(random.getRandomValues).not.toHaveBeenCalled();
  });

  it("creates a valid UUID with the available random source on LAN HTTP", () => {
    let calls = 0;
    const random = { getRandomValues<T extends ArrayBufferView | null>(array: T): T {
      calls += 1;
      (array as Uint8Array).fill(255);
      return array;
    } };
    const identifier = createClientId(random);
    expect(identifier).toBe("ffffffff-ffff-4fff-bfff-ffffffffffff");
    expect(identifier).toMatch(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
    expect(identifier).toMatch(/^[a-zA-Z0-9-]{1,64}$/);
    expect(calls).toBe(1);
  });

  it("provides an actionable error if the browser lacks random generation", () => {
    expect(() => createClientId({} as Crypto)).toThrow("Atualize o navegador");
  });
});
