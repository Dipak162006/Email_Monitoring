export interface DashboardStats {
  sent_count: number;
  bounced_count: number;
  response_count: number;
  bounce_rate: number;
  sent_change_percent: number | null;
  bounced_change_percent: number | null;
  response_change_percent: number | null;
  period_start: string | null;
  period_end: string | null;
}

export interface DashboardActivityPoint {
  date: string;
  label: string;
  sent: number;
  responses: number;
  bounced: number;
}

export interface DashboardActivityResponse {
  points: DashboardActivityPoint[];
  total_sent: number;
  total_responses: number;
  total_bounced: number;
}

export interface AccountHealthItem {
  id: number;
  name: string;
  email_address: string;
  provider: "GOOGLE" | "YAHOO" | "ZOHO" | "CUSTOM" | string;
  is_active: boolean;
  last_synced_at: string | null;
  status_label: "Operational" | "Syncing" | "Idle" | string;
}

export interface AccountHealthResponse {
  total_accounts: number;
  active_accounts: number;
  syncing_accounts: number;
  last_synced_at: string | null;
  accounts: AccountHealthItem[];
}

export type DateRangePreset = "today" | "7d" | "30d" | "90d" | "6m" | "1y" | "all";

export interface DateRangeConfig {
  id: DateRangePreset;
  label: string;
  comparisonLabel: string;
  computeRange: (now: Date) => { dateFrom?: string; dateTo: string; allTime?: boolean };
}

export const DATE_RANGE_PRESETS: Record<DateRangePreset, DateRangeConfig> = {
  today: {
    id: "today",
    label: "Today",
    comparisonLabel: "yesterday",
    computeRange: (now: Date) => {
      const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 0, 0, 0);
      return { dateFrom: todayStart.toISOString(), dateTo: now.toISOString() };
    },
  },
  "7d": {
    id: "7d",
    label: "Last 7 days",
    comparisonLabel: "previous 7d",
    computeRange: (now: Date) => {
      const from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      return { dateFrom: from.toISOString(), dateTo: now.toISOString() };
    },
  },
  "30d": {
    id: "30d",
    label: "Last 30 days",
    comparisonLabel: "previous 30d",
    computeRange: (now: Date) => {
      const from = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      return { dateFrom: from.toISOString(), dateTo: now.toISOString() };
    },
  },
  "90d": {
    id: "90d",
    label: "Last 90 days",
    comparisonLabel: "previous 90d",
    computeRange: (now: Date) => {
      const from = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
      return { dateFrom: from.toISOString(), dateTo: now.toISOString() };
    },
  },
  "6m": {
    id: "6m",
    label: "Last 6 months",
    comparisonLabel: "previous 6m",
    computeRange: (now: Date) => {
      const from = new Date(now.getFullYear(), now.getMonth() - 6, now.getDate(), now.getHours(), now.getMinutes(), now.getSeconds());
      return { dateFrom: from.toISOString(), dateTo: now.toISOString() };
    },
  },
  "1y": {
    id: "1y",
    label: "Last 1 year",
    comparisonLabel: "previous 1y",
    computeRange: (now: Date) => {
      const from = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate(), now.getHours(), now.getMinutes(), now.getSeconds());
      return { dateFrom: from.toISOString(), dateTo: now.toISOString() };
    },
  },
  all: {
    id: "all",
    label: "All Time",
    comparisonLabel: "prior data",
    computeRange: (now: Date) => {
      return { dateFrom: undefined, dateTo: now.toISOString(), allTime: true };
    },
  },
};

export interface DashboardFilterParams {
  companyId?: number;
  emailAccountId?: number;
  dateFrom?: string;
  dateTo?: string;
  allTime?: boolean;
}

