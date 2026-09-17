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

export type DateRangePreset = "today" | "7d" | "30d";

export interface DashboardFilterParams {
  companyId?: number;
  emailAccountId?: number;
  dateFrom?: string;
  dateTo?: string;
}
