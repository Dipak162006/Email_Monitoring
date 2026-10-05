export type DomainVerificationStatus = "PENDING" | "VERIFIED" | "WARNING" | "FAILED";

export interface Domain {
  id: number;
  company_id: number;
  domain_name: string;
  verification_status: DomainVerificationStatus;
  spf_status: DomainVerificationStatus;
  dkim_status: DomainVerificationStatus;
  dmarc_status: DomainVerificationStatus;
  mx_status: DomainVerificationStatus;
  dkim_selector: string | null;
  last_checked_at: string | null;
  verification_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface DomainCreatePayload {
  domain_name: string;
  dkim_selector?: string | null;
}

export interface DomainUpdatePayload {
  dkim_selector?: string | null;
}
