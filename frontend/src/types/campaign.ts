export type CampaignStatus =
  | "DRAFT"
  | "SCHEDULED"
  | "QUEUED"
  | "RUNNING"
  | "PAUSED"
  | "COMPLETED"
  | "CANCELLED"
  | "FAILED";

export interface Campaign {
  id: number;
  company_id: number;
  email_account_id: number;
  name: string;
  subject: string;
  body_text?: string | null;
  body_html?: string | null;
  status: CampaignStatus;
  scheduled_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  created_by_user_id?: number | null;
  created_at: string;
  updated_at: string;
  send_interval_seconds?: number;
  next_send_at?: string | null;
  // Resolved or enriched fields (optional from detail or client join)
  email_account_name?: string | null;
  email_account_address?: string | null;
  recipient_count?: number;
  attachments?: CampaignAttachment[];
}

export interface CampaignAttachment {
  id: number;
  campaign_id: number;
  company_id: number;
  email_account_id: number;
  file_name: string;
  content_type: string;
  file_size: number;
  created_at: string;
}

export interface CampaignDetail extends Campaign {
  recipient_count: number;
  pending_count?: number;
  sent_count?: number;
  failed_count?: number;
  bounced_count?: number;
  suppressed_count?: number;
}

export interface CampaignCreatePayload {
  name: string;
  email_account_id: number;
  subject?: string;
  body_text?: string | null;
  body_html?: string | null;
  send_interval_seconds?: number;
}

export interface CampaignUpdatePayload {
  name?: string;
  email_account_id?: number;
  subject?: string;
  body_text?: string | null;
  body_html?: string | null;
  scheduled_at?: string | null;
  send_interval_seconds?: number;
}

export interface CampaignSchedulePayload {
  scheduled_at?: string | null;
}

export interface CampaignListParams {
  status?: CampaignStatus | string;
  limit?: number;
  offset?: number;
}

export type CampaignRecipientStatus =
  | "PENDING"
  | "SENT"
  | "FAILED"
  | "BOUNCED"
  | "SUPPRESSED";

export interface CampaignRecipient {
  id: number;
  campaign_id: number;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  custom_variables?: Record<string, any> | null;
  status: CampaignRecipientStatus;
  created_at: string;
}

export interface CampaignRecipientCreatePayload {
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  custom_variables?: Record<string, any> | null;
}

export interface CampaignRecipientUpdatePayload {
  email?: string;
  first_name?: string | null;
  last_name?: string | null;
  custom_variables?: Record<string, any> | null;
}

export interface CampaignRecipientBulkCreateRequest {
  recipients: CampaignRecipientCreatePayload[];
}

export interface CampaignRecipientBulkCreateResponse {
  total_submitted: number;
  inserted_count: number;
  skipped_count: number;
  recipients: CampaignRecipient[];
  skipped_emails: string[];
}

export interface CampaignRecipientImportResponse {
  total_rows: number;
  inserted_count: number;
  skipped_duplicates_count: number;
  invalid_rows_count: number;
  skipped_emails: string[];
  invalid_rows: Array<{
    row: number;
    email: string;
    reason: string;
  }>;
}

export interface CampaignRecipientListParams {
  status?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

export interface PreflightIssue {
  code: string;
  message: string;
  severity: "BLOCKING" | "WARNING" | string;
  blocking: boolean;
}

export interface CampaignPreflightResponse {
  eligible: boolean;
  campaign_id: number;
  recipient_count: number;
  eligible_recipient_count: number;
  suppressed_recipient_count: number;
  issues: PreflightIssue[];
}

export interface CampaignDispatchResponse {
  campaign_id: number;
  company_id: number;
  status: CampaignStatus;
  task_id?: string | null;
  dispatched_at: string;
  eligible_recipient_count: number;
  total_recipient_count: number;
}

