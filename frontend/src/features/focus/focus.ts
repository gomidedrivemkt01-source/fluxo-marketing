export type FocusView = "all" | "inbox" | "today" | "upcoming" | "overdue" | "waiting" | "delegated";

export type FocusDemand = {
  assigneeId: string | null;
  createdById: string;
  deadlineAt: string | null;
  status: string;
};

const waitingStatuses = new Set(["WAITING_INFORMATION", "WAITING_APPROVAL", "BLOCKED"]);

function dateKey(value: Date, timeZone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(value);
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}`;
}

export function matchesFocus(
  demand: FocusDemand,
  view: FocusView,
  profileId: string,
  timeZone: string,
  now = new Date(),
): boolean {
  if (view === "delegated") {
    return demand.status !== "COMPLETED"
      && demand.createdById === profileId
      && demand.assigneeId !== null
      && demand.assigneeId !== profileId;
  }
  if (demand.assigneeId !== profileId) return false;
  if (view === "all") return true;
  if (demand.status === "COMPLETED") return false;
  if (view === "waiting") return waitingStatuses.has(demand.status);

  const waiting = waitingStatuses.has(demand.status);
  if (view === "inbox") return demand.deadlineAt === null && demand.status === "WAITING_EXECUTION";
  if (!demand.deadlineAt) return false;

  const today = dateKey(now, timeZone);
  const deadline = dateKey(new Date(demand.deadlineAt), timeZone);
  if (view === "today") return deadline === today;
  if (view === "upcoming") return deadline > today;
  return deadline < today;
}

export function focusCounts(
  demands: FocusDemand[],
  profileId: string,
  timeZone: string,
  now = new Date(),
): Record<FocusView, number> {
  const views: FocusView[] = ["all", "inbox", "today", "upcoming", "overdue", "waiting", "delegated"];
  return Object.fromEntries(
    views.map((view) => [
      view,
      demands.filter((demand) => matchesFocus(demand, view, profileId, timeZone, now)).length,
    ]),
  ) as Record<FocusView, number>;
}
