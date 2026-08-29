export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    credentials: "include",
    headers: { Accept: "application/json", ...(init?.headers ?? {}) },
  });

  if (response.status === 401) {
    // No live session - the server routes (not this SPA) own login, so hand
    // off with a full navigation rather than trying to render a logged-out
    // state here.
    window.location.href = "/login";
    return new Promise<T>(() => {});
  }

  if (!response.ok) {
    const body: { detail?: string } = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail ?? response.statusText);
  }

  return (await response.json()) as T;
}

export interface DashboardMetrics {
  bodyBattery: number | null;
  trainingReadiness: number | null;
  sleepScore: number | null;
  restingHeartRate: number | null;
  hrv: number | null;
}

export interface DashboardTrends {
  bodyBattery: (number | null)[];
  trainingReadiness: (number | null)[];
  sleepScore: (number | null)[];
  restingHeartRate: (number | null)[];
  hrv: (number | null)[];
}

export interface ActivitySummary {
  activityId: number | null;
  name: string | null;
  type: string | null;
  startTimeLocal: string | null;
  distanceMeters: number | null;
  durationSeconds: number | null;
  calories: number | null;
  averageHR: number | null;
}

export interface WeekTotals {
  durationSeconds: number;
  runningDistanceMeters: number;
  workoutCount: number;
}

export interface TrainingLoad {
  thisWeek: WeekTotals;
  lastWeek: WeekTotals;
}

export interface RacePredictions {
  /** All four in seconds. */
  time5K: number | null;
  time10K: number | null;
  timeHalfMarathon: number | null;
  timeMarathon: number | null;
}

export interface TrainingStatus {
  label: string | null;
  vo2Max: number | null;
}

export interface DashboardResponse {
  today: DashboardMetrics;
  trends: DashboardTrends;
  recentActivities: ActivitySummary[];
  trainingLoad: TrainingLoad | null;
  racePredictions: RacePredictions | null;
  trainingStatus: TrainingStatus | null;
}

export interface SessionItem {
  date: string;
  name?: string;
}

export interface WeeklyCheckInResponse {
  weekStart: string;
  weekEnd: string;
  sessionsScheduled: number;
  sessionsCompleted: SessionItem[];
  sessionsMissed: SessionItem[];
  sessionsUpcoming: SessionItem[];
  recoveryTrend: {
    trainingReadiness: (number | null)[];
    hrv: (number | null)[];
  };
  readinessSuppressed: boolean;
  hrvSuppressed: boolean;
}

export interface PlanProgressResponse {
  raceDate: string;
  daysUntilRace: number;
  currentWeek: number | null;
  weeksRemaining: number | null;
  totalWeeks: number | null;
  matchedSessionName: string | null;
}

export function getDashboard(): Promise<DashboardResponse> {
  return request("/api/dashboard");
}

export function getWeeklyCheckIn(): Promise<WeeklyCheckInResponse> {
  return request("/api/weekly-check-in");
}

export function getPlanProgress(raceDate: string): Promise<PlanProgressResponse> {
  return request(`/api/plan-progress?race_date=${encodeURIComponent(raceDate)}`);
}

export function disconnectGarmin(): Promise<{ status: string }> {
  return request("/api/disconnect", { method: "POST" });
}
