export type OverviewDemand = {
  id: string;
  title: string;
  assigneeId: string | null;
  status: string;
  stageName: string | null;
  deadlineAt: string | null;
  priority: string;
};

export type DeliveryPeriod = "week" | "14" | "30";

const dayFormatters = new Map<string, Intl.DateTimeFormat>();

export function dayKey(date: Date, timeZone: string): string {
  let formatter = dayFormatters.get(timeZone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" });
    dayFormatters.set(timeZone, formatter);
  }
  return formatter.format(date);
}

export function isAwaitingApproval(demand: OverviewDemand): boolean {
  return demand.status === "WAITING_APPROVAL" || /aprova/i.test(demand.stageName ?? "");
}

export function isOverdue(demand: OverviewDemand, now: Date): boolean {
  return demand.status !== "COMPLETED" && Boolean(demand.deadlineAt && new Date(demand.deadlineAt).getTime() < now.getTime());
}

export function deliveryRange(period: DeliveryPeriod, timeZone: string, now: Date): { start: string; end: string } {
  const start = dayKey(now, timeZone);
  const anchor = new Date(`${start}T12:00:00Z`);
  if (period === "week") {
    const monday = (anchor.getUTCDay() + 6) % 7;
    anchor.setUTCDate(anchor.getUTCDate() - monday);
    const weekStart = anchor.toISOString().slice(0, 10);
    anchor.setUTCDate(anchor.getUTCDate() + 6);
    return { start: weekStart, end: anchor.toISOString().slice(0, 10) };
  }
  anchor.setUTCDate(anchor.getUTCDate() + Number(period) - 1);
  return { start, end: anchor.toISOString().slice(0, 10) };
}

export function inDeliveryRange(demand: OverviewDemand, period: DeliveryPeriod, timeZone: string, now: Date): boolean {
  if (!demand.deadlineAt) return false;
  const { start, end } = deliveryRange(period, timeZone, now);
  const deadline = dayKey(new Date(demand.deadlineAt), timeZone);
  return deadline >= start && deadline <= end;
}

export function byDelivery(a: OverviewDemand, b: OverviewDemand): number {
  const dateA = a.deadlineAt ? new Date(a.deadlineAt).getTime() : Infinity;
  const dateB = b.deadlineAt ? new Date(b.deadlineAt).getTime() : Infinity;
  return (dateA === dateB ? 0 : dateA - dateB) || a.title.localeCompare(b.title, "pt-BR");
}

export function overviewSummary<T extends OverviewDemand>(demands: T[], period: DeliveryPeriod, timeZone: string, now: Date) {
  const active = demands.filter((item) => item.status !== "COMPLETED");
  return {
    active,
    overdue: active.filter((item) => isOverdue(item, now)),
    approvals: active.filter(isAwaitingApproval).sort(byDelivery),
    deliveries: active.filter((item) => inDeliveryRange(item, period, timeZone, now)),
    scheduled: active.filter((item) => item.status === "SCHEDULED"),
    upcoming: active.filter((item) => item.deadlineAt && new Date(item.deadlineAt) >= now && inDeliveryRange(item, period, timeZone, now)).sort(byDelivery),
  };
}
