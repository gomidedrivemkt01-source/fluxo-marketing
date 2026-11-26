export type PerformanceCard = { id: string; title: string; publicId: string; canOpen: boolean };
export type PersonalPerformance = {
  profileId: string; timezone: string; startDate: string; endDate: string; generatedAt: string;
  gapMinutes: number; dayStart: string; dayEnd: string;
  summary: { recordedMinutes: number; pendingMinutes: number; coverageMinutes: number; stageAdvances: number; deliveredCards: number; completedAfterDelivery: number; awaitingFinal: number; returns: number; timerStarts: number; timerResumes: number };
  days: { date: string; recordedMinutes: number; pendingMinutes: number; coverageMinutes: number; timerStarts: number; timerResumes: number; stageAdvances: number; deliveredCards: number; returns: number }[];
  segments: (PerformanceCard & { entryId: string; kind: "timer" | "manual" | "adjusted"; date: string; startedAt: string; endedAt: string; running: boolean; startMinute: number; endMinute: number; minutes: number })[];
  cadence: (PerformanceCard & { at: string; date: string; kind: "advance" | "return"; stageName: string })[];
  deliveries: (PerformanceCard & { advancedAt: string; lastAdvancedAt: string; stageAdvances: number; completedAt: string | null; outcome: "completed" | "awaiting" })[];
  returns: (PerformanceCard & { at: string; reason: string | null })[];
  approval: { counts: { approved: number; rework: number; pending: number }; decided: number; approvalRate: number | null; reworkRate: number | null; items: (PerformanceCard & { stageName: string; outcome: "approved" | "rework" | "pending" })[] };
  alerts: { id: string; tone: "warning" | "info" | "positive"; title: string; description: string; demandId: string | null }[];
  gaps: { date: string; startedAt: string; endedAt: string; minutes: number }[];
  comparisons: (PerformanceCard & { minutes: number; referenceMinutes: number; sampleCards: number; outcome: "above" | "below" | "typical" })[];
  quality: { unlocatedPendingMinutes: number; unlocatedMinutes: number; entriesWithoutTrace: number; adjustedEntries: number; baselineMinimum: number };
};
export function minuteLabel(value: number): string {
  const minutes = Math.round(value), hours = Math.floor(minutes / 60), rest = minutes % 60;
  return hours ? `${hours}h${rest ? ` ${rest}min` : ""}` : `${minutes}min`;
}
export function localDay(value: Date, zone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" }).formatToParts(value);
  return ["year","month","day"].map(kind => parts.find(part => part.type === kind)?.value ?? "").join("-");
}
function shifted(day: string, amount: number): string {
  const date = new Date(`${day}T12:00:00Z`); date.setUTCDate(date.getUTCDate()+amount); return date.toISOString().slice(0,10);
}
export function performanceRange(period: string, today: string, start: string, end: string) {
  if (period === "custom") return { start, end };
  if (period === "yesterday") { const day = shifted(today,-1); return { start: day, end: day }; }
  if (period === "week") return { start: shifted(today,-((new Date(`${today}T12:00:00Z`).getUTCDay()+6)%7)), end: today };
  if (period === "7") return { start: shifted(today,-6), end: today };
  return { start: today, end: today };
}
