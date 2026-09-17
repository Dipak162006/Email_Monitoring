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
