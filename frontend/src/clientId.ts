type RandomSource = Pick<Crypto, "getRandomValues"> & Partial<Pick<Crypto, "randomUUID">>;

/** Browser-generated IDs for columns, saved views and interface profiles. */
export function createClientId(random: RandomSource = globalThis.crypto): string {
  if (typeof random?.randomUUID === "function") return random.randomUUID();
  // randomUUID requires a secure context; getRandomValues also works on LAN HTTP.
  if (typeof random?.getRandomValues !== "function") {
    throw new Error("Não foi possível gerar o identificador. Atualize o navegador e tente novamente.");
  }
  const bytes = random.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6]! & 0x0f) | 0x40;
  bytes[8] = (bytes[8]! & 0x3f) | 0x80;
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}
