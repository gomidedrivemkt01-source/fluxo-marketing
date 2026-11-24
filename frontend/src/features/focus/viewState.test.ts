import { describe, expect, it } from "vitest";
import { readViewState, viewStateKey } from "./viewState";

const defaults = { query: "", company: "ALL", assignees: [] as string[], month: 0 };

describe("workspace filters", () => {
  it("isolates users and areas in the current browser tab", () => {
    expect(viewStateKey("person-a", "demands")).not.toBe(viewStateKey("person-b", "demands"));
    expect(viewStateKey("person-a", "demands")).not.toBe(viewStateKey("person-a", "my-work"));
    const storage = { getItem: () => JSON.stringify({ query: "Campanha", company: "brand-1", assignees: ["UNASSIGNED", "person-2"], month: 1793491200000 }) };
    expect(readViewState(storage, "key", defaults)).toEqual({ query: "Campanha", company: "brand-1", assignees: ["UNASSIGNED", "person-2"], month: 1793491200000 });
  });
  it("ignores unavailable, corrupt or incorrectly typed storage", () => {
    expect(readViewState({ getItem: () => "broken" }, "key", defaults)).toEqual(defaults);
    expect(readViewState({ getItem: () => { throw new Error("blocked"); } }, "key", defaults)).toEqual(defaults);
    expect(readViewState({ getItem: () => JSON.stringify({ query: {}, company: null, assignees: [1], month: "invalid", extra: "ignored" }) }, "key", defaults)).toEqual(defaults);
  });
});
