import { describe, expect, it } from "vitest";
import { byDelivery, dayKey, deliveryRange, isAwaitingApproval, isOverdue, overviewSummary, type OverviewDemand } from "./overview";

const now = new Date("2026-11-25T15:00:00Z");
const zone = "America/Sao_Paulo";
const card = (id: string, changes: Partial<OverviewDemand> = {}): OverviewDemand => ({ id, title: id, assigneeId: "person", status: "IN_PROGRESS", stageName: "Produção", deadlineAt: null, priority: "NORMAL", ...changes });

describe("operational overview", () => {
  it("uses the profile timezone, including weeks spanning a year boundary", () => {
    expect(dayKey(new Date("2026-11-25T01:00:00Z"), zone)).toBe("2026-11-24");
    expect(deliveryRange("week", zone, now)).toEqual({ start: "2026-11-23", end: "2026-11-29" });
    expect(deliveryRange("week", zone, new Date("2027-01-01T12:00:00Z"))).toEqual({ start: "2026-12-28", end: "2027-01-03" });
    expect(deliveryRange("14", zone, now)).toEqual({ start: "2026-11-25", end: "2026-12-08" });
  });
  it("counts actual missed times today and excludes completed cards", () => {
    expect(isOverdue(card("late", { deadlineAt: "2026-11-25T14:59:00Z" }), now)).toBe(true);
    expect(isOverdue(card("later", { deadlineAt: "2026-11-25T16:00:00Z" }), now)).toBe(false);
    expect(isOverdue(card("done", { status: "COMPLETED", deadlineAt: "2026-11-24T12:00:00Z" }), now)).toBe(false);
  });
  it("finds approvals through status or workflow stage without double counting", () => {
    expect(isAwaitingApproval(card("a", { status: "WAITING_APPROVAL" }))).toBe(true);
    expect(isAwaitingApproval(card("b", { stageName: "Aprovação editorial" }))).toBe(true);
    const summary = overviewSummary([card("a", { status: "WAITING_APPROVAL", stageName: "Aprovação" }), card("b", { status: "COMPLETED", stageName: "Aprovação" })], "week", zone, now);
    expect(summary.approvals.map(item => item.id)).toEqual(["a"]);
  });
  it("keeps scheduled items and weekly deliveries distinct from upcoming deadlines", () => {
    const summary = overviewSummary([
      card("past", { deadlineAt: "2026-11-23T16:00:00Z" }),
      card("next", { deadlineAt: "2026-11-26T16:00:00Z" }),
      card("scheduled", { status: "SCHEDULED", deadlineAt: "2026-12-02T16:00:00Z" }),
      card("undated"), card("completed", { status: "COMPLETED" }),
    ], "week", zone, now);
    expect(summary.active).toHaveLength(4);
    expect(summary.deliveries.map(item => item.id)).toEqual(["past", "next"]);
    expect(summary.upcoming.map(item => item.id)).toEqual(["next"]);
    expect(summary.scheduled.map(item => item.id)).toEqual(["scheduled"]);
  });
  it("sorts unassigned deadlines last with deterministic ties", () => {
    const sorted = [card("Z"), card("B", { deadlineAt: "2026-11-26T16:00:00Z" }), card("A", { deadlineAt: "2026-11-26T16:00:00Z" })].sort(byDelivery);
    expect(sorted.map(item => item.id)).toEqual(["A", "B", "Z"]);
  });
});
