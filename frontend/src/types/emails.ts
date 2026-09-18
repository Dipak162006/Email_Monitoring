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

