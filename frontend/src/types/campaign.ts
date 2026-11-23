export interface SendingWindowConfig {
  enabled: boolean;
  timezone: string;
  days: number[];
  start_time: string;
  end_time: string;
}

export type CampaignStatus =
  | "DRAFT"
  | "SCHEDULED"
  | "QUEUED"
  | "RUNNING"
  | "PAUSED"
  | "COMPLETED"
  | "CANCELLED"
  | "FAILED"
  | "ARCHIVED";

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
  steps?: CampaignStepItem[];
  followup_steps?: CampaignStepItem[];
  sending_window?: SendingWindowConfig | null;
}

export interface CampaignStepItem {
  id: number;
  campaign_id: number;
  step_number: number;
  delay_hours: number;
  subject: string;
  body_text?: string | null;
  body_html?: string | null;
  target_tags?: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CampaignStepWritePayload {
  step_number: number;
  delay_hours: number;
  subject?: string;
  body_text?: string | null;
  body_html?: string | null;
  target_tags?: string[];
  is_active?: boolean;
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
  replied_count?: number;
  followup_scheduled_count?: number;
  followup_sent_count?: number;
  initial_sent_count?: number;
  total_sent_count?: number;
  unique_replied_count?: number;
}

export interface CampaignCreatePayload {
  name: string;
  email_account_id: number;
  subject?: string;
  body_text?: string | null;
  body_html?: string | null;
  send_interval_seconds?: number;
  followup_steps?: CampaignStepWritePayload[];
  sending_window?: SendingWindowConfig | null;
}

export interface CampaignUpdatePayload {
  name?: string;
  email_account_id?: number;
  subject?: string;
  body_text?: string | null;
  body_html?: string | null;
  scheduled_at?: string | null;
  send_interval_seconds?: number;
  followup_steps?: CampaignStepWritePayload[];
  sending_window?: SendingWindowConfig | null;
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
  | "SUPPRESSED"
  | "ACTIVE"
  | "COMPLETED"
  | "STOPPED";

export type CampaignRecipientStopReason =
  | "REPLIED"
  | "UNSUBSCRIBED"
  | "BOUNCED"
  | "MANUAL"
  | "CAMPAIGN_CANCELLED";

export interface CampaignRecipient {
  id: number;
  campaign_id: number;
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  custom_variables?: Record<string, any> | null;
  tags?: string[];
  status: CampaignRecipientStatus;
  current_step_number?: number;
  next_step_due_at?: string | null;
  stopped_reason?: string | null;
  replied_at?: string | null;
  created_at: string;
  updated_at?: string;
}

export interface CampaignRecipientReschedulePayload {
  next_step_due_at: string;
}

export interface CampaignRecipientStopPayload {
  reason?: string;
}

export interface CampaignRecipientCreatePayload {
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  custom_variables?: Record<string, any> | null;
  tags?: string[];
}

export interface CampaignRecipientTagsUpdatePayload {
  tags: string[];
}

export interface CampaignRecipientTagAddPayload {
  tag: string;
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

export type SuppressionReason =
  | "BOUNCE"
  | "UNSUBSCRIBE"
  | "MANUAL"
  | "COMPLAINT";

export interface SuppressionEntry {
  id: number;
  company_id: number;
  email: string;
  reason: SuppressionReason;
  created_at: string;
}

export interface SuppressionCreatePayload {
  email: string;
  reason?: SuppressionReason;
}

export interface SuppressionBulkCreatePayload {
  emails: string[];
  reason?: SuppressionReason;
}

export interface SuppressionBulkCreateResponse {
  total_submitted: number;
  inserted_count: number;
  skipped_count: number;
  entries: SuppressionEntry[];
  skipped_emails: string[];
}

export interface SuppressionListParams {
  reason?: string;
  search?: string;
  limit?: number;
  offset?: number;
}


export interface CampaignStepAnalytics {
  step_id?: number;
  step_number: number;
  subject: string;
  delay_hours: number;
  target_tags: string[];
  targeted_count: number;
  sent_count: number;
  unique_recipients_sent?: number;
  sending_count: number;
  bounced_count: number;
  failed_count: number;
  skipped_count: number;
  replied_count: number;
  pending_count: number;
  delivered_count?: number;
  delivery_rate: number;
  reply_rate: number;
  bounce_rate: number;
  is_active?: boolean;
  raw_open_count?: number;
  unique_open_recipients?: number;
  raw_click_count?: number;
  unique_click_recipients?: number;
  open_rate?: number;
  click_rate?: number;
  click_to_open_rate?: number;
}

export interface CampaignDeliveryTrendPoint {
  date: string;
  sent_count: number;
  bounced_count: number;
  replied_count: number;
}

export interface CampaignDeliveryMetrics {
  total_recipients: number;
  total_sent: number;
  unique_recipients_sent: number;
  estimated_delivered_count: number;
  bounced_count: number;
  failed_count: number;
  suppressed_count: number;
  delivered_count: number;
}

export interface CampaignEngagementMetrics {
  raw_open_count: number;
  unique_open_recipients: number;
  unique_recipients_sent: number;
  open_rate: number;
  raw_click_count: number;
  unique_click_recipients: number;
  click_rate: number;
  click_to_open_rate: number;
  unique_clicked_destinations?: number | null;
}

export interface CampaignClassificationMetrics {
  bot_events_count: number;
  non_bot_events_count: number;
  unknown_events_count: number;
  bot_open_count?: number;
  non_bot_open_count?: number;
  unknown_open_count?: number;
  bot_click_count?: number;
  non_bot_click_count?: number;
  unknown_click_count?: number;
}

export interface CampaignAnalyticsResponse {
  campaign_id: number;
  campaign_name: string;
  campaign_status: CampaignStatus;
  total_recipients: number;
  total_steps: number;
  initial_sent_count?: number;
  followup_sent_count?: number;
  total_sent_count?: number;
  unique_replied_count?: number;
  steps: CampaignStepAnalytics[];
  omitted_metrics_notice?: string;
  delivery_trend?: CampaignDeliveryTrendPoint[];

  // Extended delivery metrics
  estimated_delivered_count?: number;
  delivered_count?: number;
  bounced_count?: number;
  failed_count?: number;
  suppressed_count?: number;

  // Extended engagement metrics
  unique_recipients_sent?: number;
  raw_open_count?: number;
  unique_open_recipients?: number;
  open_rate?: number;
  raw_click_count?: number;
  unique_click_recipients?: number;
  click_rate?: number;
  click_to_open_rate?: number;
  unique_clicked_destinations?: number | null;

  // Extended classification metrics
  bot_events_count?: number;
  non_bot_events_count?: number;
  unknown_events_count?: number;

  // Structured metric groups
  delivery?: CampaignDeliveryMetrics;
  engagement?: CampaignEngagementMetrics;
  classification?: CampaignClassificationMetrics;
}

export interface CampaignRecipientEngagementItem {
  recipient_id: number;
  masked_email?: string | null;
  first_event_at: string;
  last_event_at: string;
  total_events_count: number;
  bot_events_count: number;
  non_bot_events_count: number;
  unknown_events_count: number;
}

export interface CampaignRecipientEngagementResponse {
  campaign_id: number;
  event_type: "OPEN" | "CLICK" | string;
  total: number;
  limit: number;
  offset: number;
  items: CampaignRecipientEngagementItem[];
}

export interface CampaignRecipientEngagementParams {
  event_type?: "OPEN" | "CLICK" | string;
  limit?: number;
  offset?: number;
  step_number?: number | null;
}


export interface CampaignDrilldownSummary {
  recipients_count: number;
  sent_count: number;
  replies_count: number;
  bounced_count: number;
  failed_count: number;
}

export interface CampaignEmailsDrilldownItem {
  id: number | string;
  recipient_id?: number | null;
  delivery_id?: number | null;
  email_id?: number | null;
  thread_id?: number | null;
  email?: string | null;
  recipient_name?: string | null;
  sender?: string | null;
  recipient?: string | null;
  status?: string | null;
  stopped_reason?: string | null;
  step_number?: number | null;
  subject?: string | null;
  sent_at?: string | null;
  received_at?: string | null;
  bounced_at?: string | null;
  bounce_type?: string | null;
  error_message?: string | null;
  attempt_count?: number | null;
  last_attempt_at?: string | null;
  replied_at?: string | null;
  is_suppressed?: boolean | null;
  suppression_reason?: string | null;
  can_retry?: boolean | null;
  created_at?: string | null;
  next_step_due_at?: string | null;
}

export interface CampaignEmailsDrilldownResponse {
  campaign_id: number;
  campaign_name: string;
  selected_status: "recipients" | "sent" | "replies" | "bounced" | "failed" | string;
  summary: CampaignDrilldownSummary;
  total: number;
  limit: number;
  offset: number;
  items: CampaignEmailsDrilldownItem[];
}
