import { describe, expect, it } from "vitest";
import { focusCounts, matchesFocus, type FocusDemand } from "./focus";

const now = new Date("2026-09-29T15:00:00Z");
const zone = "America/Sao_Paulo";
const me = "profile-me";

function demand(values: Partial<FocusDemand> = {}): FocusDemand {
  return {
    assigneeId: me,
    createdById: me,
    deadlineAt: null,
    status: "WAITING_EXECUTION",
    ...values,
  };
}

describe("matchesFocus", () => {
  it("separates inbox, today, upcoming and overdue by the user timezone", () => {
    expect(matchesFocus(demand(), "inbox", me, zone, now)).toBe(true);
    expect(matchesFocus(demand({ deadlineAt: "2026-09-29T18:00:00Z" }), "today", me, zone, now)).toBe(true);
    expect(matchesFocus(demand({ deadlineAt: "2026-09-30T12:00:00Z" }), "upcoming", me, zone, now)).toBe(true);
    expect(matchesFocus(demand({ deadlineAt: "2026-09-28T12:00:00Z" }), "overdue", me, zone, now)).toBe(true);
  });

  it("keeps waiting work out of the inbox", () => {
    const waiting = demand({ status: "WAITING_APPROVAL" });
    expect(matchesFocus(waiting, "waiting", me, zone, now)).toBe(true);
    expect(matchesFocus(waiting, "inbox", me, zone, now)).toBe(false);
  });

  it("removes an inbox item when work starts even without a deadline", () => {
    expect(matchesFocus(demand({ status: "IN_PROGRESS" }), "inbox", me, zone, now)).toBe(false);
  });

  it("finds work created by me and assigned to another person", () => {
    expect(matchesFocus(demand({ assigneeId: "profile-other" }), "delegated", me, zone, now)).toBe(true);
    expect(matchesFocus(demand({ assigneeId: null }), "delegated", me, zone, now)).toBe(false);
  });

  it("excludes completed demands from action views", () => {
    const completed = demand({ status: "COMPLETED", deadlineAt: "2026-09-29T18:00:00Z" });
    expect(matchesFocus(completed, "today", me, zone, now)).toBe(false);
    expect(matchesFocus(completed, "all", me, zone, now)).toBe(true);
  });
});

describe("focusCounts", () => {
  it("returns a count for every focus view", () => {
    const counts = focusCounts([
      demand(),
      demand({ deadlineAt: "2026-09-29T18:00:00Z" }),
      demand({ assigneeId: "profile-other" }),
    ], me, zone, now);

    expect(counts).toMatchObject({ all: 2, inbox: 1, today: 1, delegated: 1 });
  });
});
