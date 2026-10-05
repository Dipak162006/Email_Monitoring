export type EmailDirection = "OUTGOING" | "INCOMING";

export type EmailStatus =
  | "DRAFT"
  | "QUEUED"
  | "SENDING"
  | "SENT"
  | "FAILED"
  | "BOUNCED"
  | "RECEIVED";

export interface EmailItem {
  id: number;
  company_id: number;
  email_account_id: number;
  thread_id: number | null;
  message_id: string | null;
  direction: EmailDirection;
  status: EmailStatus;
  sender: string;
  recipients: string[];
  cc?: string[] | null;
  bcc?: string[] | null;
  reply_to?: string | null;
  in_reply_to?: string | null;
  references_header?: string | null;
  subject: string;
  body_text?: string | null;
  body_html?: string | null;
  is_read: boolean;
  is_starred: boolean;
  is_deleted: boolean;
  sent_at?: string | null;
  received_at?: string | null;
  created_at: string;
  updated_at: string;
  /** Number of stored downloadable attachments for this email (0 when none). */
  attachment_count?: number;
}

export interface EmailListResponse {
  emails: EmailItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface EmailListParams {
  folder?: string;
  status?: string;
  direction?: string;
  emailAccountId?: number;
  companyId?: number;
  isRead?: boolean;
  isStarred?: boolean;
  search?: string;
  dateFrom?: string;
  dateTo?: string;
  sort?: "newest" | "oldest";
  limit?: number;
  offset?: number;
}

export interface AttachmentItem {
  id: number;
  company_id: number;
  email_account_id: number;
  email_id: number;
  file_name: string;
  content_type: string;
  file_size: number;
  created_at: string;
  updated_at: string;
}

export interface AttachmentListResponse {
  attachments: AttachmentItem[];
  total: number;
}

export interface EmailThreadDetail {
  id: number;
  company_id: number;
  email_account_id: number;
  subject: string;
  snippet?: string | null;
  message_count: number;
  has_reply: boolean;
  last_message_at: string;
  is_read: boolean;
  created_at: string;
  updated_at: string;
  emails: EmailItem[];
}

export type EmailProvider = "CUSTOM" | "GOOGLE" | "YAHOO" | "ZOHO";
export type SecurityMode = "NONE" | "SSL" | "STARTTLS";

export interface EmailAccountItem {
  id: number;
  company_id: number;
  name: string;
  email_address: string;
  provider: EmailProvider;
  domain_id?: number | null;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_security?: SecurityMode | null;
  smtp_username?: string | null;
  has_smtp_password: boolean;
  imap_host?: string | null;
  imap_port?: number | null;
  imap_security?: SecurityMode | null;
  imap_username?: string | null;
  has_imap_password: boolean;
  is_active: boolean;
  last_synced_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmailAccountCreatePayload {
  name: string;
  email_address: string;
  provider: EmailProvider;
  domain_id?: number | null;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_security?: SecurityMode | null;
  smtp_username?: string | null;
  smtp_password?: string | null;
  imap_host?: string | null;
  imap_port?: number | null;
  imap_security?: SecurityMode | null;
  imap_username?: string | null;
  imap_password?: string | null;
}

export interface EmailAccountUpdatePayload {
  name?: string;
  email_address?: string;
  provider?: EmailProvider;
  domain_id?: number | null;
  smtp_host?: string | null;
  smtp_port?: number | null;
  smtp_security?: SecurityMode | null;
  smtp_username?: string | null;
  smtp_password?: string | null;
  imap_host?: string | null;
  imap_port?: number | null;
  imap_security?: SecurityMode | null;
  imap_username?: string | null;
  imap_password?: string | null;
  is_active?: boolean;
}

export interface AuthorizedEmailAccount {
  id: number;
  company_id: number;
  name: string;
  email_address: string;
  provider: string;
  is_active: boolean;
  is_sync_enabled: boolean;
}

export interface EmailSendPayload {
  email_account_id: number;
  to: string[];
  subject: string;
  body_text?: string;
  body_html?: string;
  cc?: string[];
  bcc?: string[];
  reply_to?: string;
  in_reply_to?: string;
  thread_id?: number;
  signature_id?: number;
  attachment_ids?: number[];
}

export interface EmailDraftPayload {
  email_account_id: number;
  to?: string[];
  cc?: string[];
  bcc?: string[];
  subject?: string;
  body_text?: string;
  body_html?: string;
  reply_to?: string;
  in_reply_to?: string;
  thread_id?: number;
  signature_id?: number;
}

export interface EmailTemplateItem {
  id: number;
  company_id: number;
  email_account_id?: number | null;
  user_id?: number | null;
  name: string;
  subject: string;
  body_text?: string | null;
  body_html?: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmailTemplateListResponse {
  templates: EmailTemplateItem[];
  total: number;
  limit?: number;
  offset?: number;
}

export interface EmailTemplateCreatePayload {
  name: string;
  subject?: string;
  body_text?: string | null;
  body_html?: string | null;
  email_account_id?: number | null;
  is_active?: boolean;
}

export interface EmailTemplateUpdatePayload {
  name?: string;
  subject?: string;
  body_text?: string | null;
  body_html?: string | null;
  email_account_id?: number | null;
  is_active?: boolean;
}

export interface EmailSignatureItem {
  id: number;
  company_id: number;
  email_account_id: number;
  user_id?: number | null;
  name: string;
  body_text?: string | null;
  body_html?: string | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface EmailSignatureListResponse {
  signatures: EmailSignatureItem[];
  total: number;
}

export interface EmailSignatureCreatePayload {
  name: string;
  email_account_id: number;
  body_text?: string | null;
  body_html?: string | null;
  is_default?: boolean;
}

export interface EmailSignatureUpdatePayload {
  name?: string;
  email_account_id?: number;
  body_text?: string | null;
  body_html?: string | null;
  is_default?: boolean;
}

export interface EmailSyncResult {
  email_account_id: number;
  status: "SUCCESS" | "PARTIAL" | "FAILED" | string;
  folder: string;
  total_discovered: number;
  new_messages: number;
  duplicates_skipped: number;
  malformed_skipped: number;
  synced_at: string;
  error_message?: string | null;
  task_id?: string | null;
}

export interface EmailSyncJobResponse {
  task_id: string;
  status: string;
  email_account_id?: number;
  folder?: string;
  message?: string;
}
