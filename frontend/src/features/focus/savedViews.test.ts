import { describe, expect, it } from "vitest";

import { buildSavedView } from "./savedViews";

describe("buildSavedView", () => {
  it("captures a normalized snapshot of the active filters", () => {
    expect(buildSavedView("view-1", "  Urgentes   hoje ", {
      query: "  campanha  ",
      companyId: "company-1",
      status: "IN_PROGRESS",
      priority: "URGENT",
      focusView: "today",
    })).toEqual({
      id: "view-1",
      name: "Urgentes hoje",
      query: "campanha",
      companyId: "company-1",
      status: "IN_PROGRESS",
      priority: "URGENT",
      focusView: "today",
    });
  });

  it("rejects names that cannot identify the view", () => {
    expect(() => buildSavedView("view-2", " ", {
      query: "",
      companyId: "ALL",
      status: "ALL",
      priority: "ALL",
      focusView: "all",
    })).toThrow("pelo menos 2 caracteres");
  });
});
