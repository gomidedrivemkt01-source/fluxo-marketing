export type AnalyticsReport = {
  periodStartedAt: string; periodEndedAt: string; periodDays: number; generatedAt: string;
  scope: "team" | "person"; scopeProfileId: string | null; scopeProfileName: string | null; canViewTeam: boolean; warningDays: number;
  summary: { confirmedDeliveries: number; awaitingFinal: number; completedCards: number; advancedCards: number; stageAdvances: number; activeCards: number; overdueCards: number; dueSoon: number; trackedMinutes: number; medianCycleHours: number | null; p90CycleHours: number | null; onTimeRate: number | null; measuredDeadlines: number };
  people: { profileId: string; name: string; confirmedDeliveries: number; awaitingFinal: number; advancedCards: number; stageAdvances: number; activeCards: number; overdueCards: number; trackedMinutes: number }[];
  trend: { date: string; cardsCompleted: number; confirmedContributions: number; stageAdvances: number; trackedMinutes: number }[];
  granularity: "day" | "week" | "month";
  stages: { id: string; name: string; workflowName: string; completedVisits: number; medianHours: number | null; p90Hours: number | null; returns: number; slaRate: number | null; measuredSla: number }[];
  timeAllocation: { id: string; label: string; color: string | null; minutes: number }[];
  deadlineRisk: { id: string; count: number }[];
  attention: { id: string; publicId: string; title: string; companyName: string | null; deadlineAt: string | null; reason: string }[];
  quality: { inferredVisitsExcluded: number; completedWithoutFinalEvidence: number; undatedActive: number; unassignedActive: number; verifiedCompletedCards: number; openTimersExcluded: number };
};

export function duration(minutes: number): string {
  const hours = Math.floor(minutes / 60), rest = minutes % 60;
  return hours ? `${hours}h${rest ? ` ${rest}min` : ""}` : `${minutes}min`;
}

export function hoursLabel(hours: number | null): string {
  return hours === null ? "Sem dados" : `${hours.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}h`;
}
