import { describe, expect, it } from "vitest";
import { localDay, performanceRange } from "./performance";

describe("independent immediate-performance ranges", () => {
  it("uses the person's date rather than the UTC date", () => {
    expect(localDay(new Date("2026-11-27T01:00:00Z"),"America/Sao_Paulo")).toBe("2026-11-26");
  });
  it("supports today, yesterday and the current week across a year boundary", () => {
    expect(performanceRange("today","2027-01-01","2026-01-01","2026-01-31")).toEqual({start:"2027-01-01",end:"2027-01-01"});
    expect(performanceRange("yesterday","2027-01-01","","")).toEqual({start:"2026-12-31",end:"2026-12-31"});
    expect(performanceRange("week","2027-01-01","","")).toEqual({start:"2026-12-28",end:"2027-01-01"});
  });
  it("preserves the custom range and uses seven calendar days", () => {
    expect(performanceRange("custom","2026-11-26","2026-11-01","2026-11-12")).toEqual({start:"2026-11-01",end:"2026-11-12"});
    expect(performanceRange("7","2026-11-26","","")).toEqual({start:"2026-11-20",end:"2026-11-26"});
  });
});
