import type {
  CompanyMember,
  CompanyMemberAddPayload,
  CompanyMemberRoleUpdatePayload,
  CompanyUpdatePayload,
  CompanyWithRole,
  CompanyInvitationItem,
  EmailAccountAccessItem,
  LoginCredentials,
  RegisterCredentials,
  Token,
  User,
  UserInvitationItem,
  UserProfileUpdatePayload,
  UserPasswordChangePayload,
} from "../types/auth";
import type {
  AccountHealthResponse,
  DashboardActivityResponse,
  DashboardFilterParams,
  DashboardStats,
} from "../types/dashboard";
import type {
  AttachmentItem,
  AttachmentListResponse,
  AuthorizedEmailAccount,
  EmailAccountCreatePayload,
  EmailAccountItem,
  EmailAccountUpdatePayload,
  EmailDraftPayload,
  EmailItem,
  EmailListParams,
  EmailListResponse,
  EmailSendPayload,
  EmailSignatureCreatePayload,
  EmailSignatureItem,
  EmailSignatureListResponse,
  EmailSignatureUpdatePayload,
  EmailSyncJobResponse,
  EmailSyncResult,
  EmailTemplateCreatePayload,
  EmailTemplateItem,
  EmailTemplateListResponse,
  EmailTemplateUpdatePayload,
  EmailThreadDetail,
} from "../types/emails";
import type {
  Domain,
  DomainCreatePayload,
  DomainUpdatePayload,
} from "../types/domains";
import type {
  Campaign,
  CampaignDetail,
  CampaignCreatePayload,
  CampaignUpdatePayload,
  CampaignSchedulePayload,
  CampaignListParams,
  CampaignRecipient,
  CampaignRecipientCreatePayload,
  CampaignRecipientUpdatePayload,
  CampaignRecipientBulkCreateRequest,
  CampaignRecipientBulkCreateResponse,
  CampaignRecipientImportResponse,
  CampaignRecipientListParams,
  CampaignPreflightResponse,
  CampaignDispatchResponse,
  CampaignAttachment,
} from "../types/campaign";
export type { ApiError } from "../types/api";

export interface ServiceStatus {
  database: "connected" | "disconnected" | "not_configured" | string;
  redis: "connected" | "disconnected" | "not_configured" | string;
}

export interface HealthResponse {
  status: "ok" | "degraded" | string;
  app_name: string;
  environment: string;
  version: string;
  services: ServiceStatus;
}

const API_BASE_URL = import.meta.env.VITE_API_URL || "";
const TOKEN_KEY = "email_mon_auth_token";

export const tokenStorage = {
  get: (): string | null => {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set: (token: string): void => {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      // Ignore storage errors in restricted contexts
    }
  },
  clear: (): void => {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      // Ignore storage errors in restricted contexts
    }
  },
};

export class RequestError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "RequestError";
    this.status = status;
    this.detail = detail;
  }
}

type UnauthorizedCallback = () => void;
let unauthorizedListener: UnauthorizedCallback | null = null;
let isHandling401 = false;

export function onUnauthorized(callback: UnauthorizedCallback | null): void {
  unauthorizedListener = callback;
}

function handle401Unauthorized(): void {
  if (isHandling401) return;
  isHandling401 = true;
  tokenStorage.clear();
  if (unauthorizedListener) {
    try {
      unauthorizedListener();
    } catch {
      // Ignore listener errors
    }
  }
  setTimeout(() => {
    isHandling401 = false;
  }, 1000);
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = endpoint.startsWith("http") ? endpoint : `${API_BASE_URL}${endpoint}`;
  const headers = new Headers(options.headers || {});

  if (!headers.has("Content-Type") && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const token = tokenStorage.get();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    let errorDetail: unknown = null;
    let errorMessage = `HTTP Error ${response.status}: ${response.statusText}`;

    try {
      const data = await response.json();
      errorDetail = data.detail ?? data;
      if (typeof errorDetail === "string") {
        errorMessage = errorDetail;
      } else if (Array.isArray(errorDetail)) {
        errorMessage = errorDetail.map((e) => (typeof e === "object" && e?.msg ? e.msg : JSON.stringify(e))).join(", ");
      } else if (data.message) {
        errorMessage = data.message;
      }
    } catch {
      // Response was not JSON
    }

    // Intercept 401 Unauthorized for expired or invalid tokens on protected endpoints
    if (response.status === 401 && !endpoint.includes("/auth/login") && !endpoint.includes("/auth/register")) {
      handle401Unauthorized();
    }

    throw new RequestError(response.status, errorMessage, errorDetail);
  }


  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export const apiClient = {
  get: <T>(endpoint: string, options?: RequestInit) => request<T>(endpoint, { ...options, method: "GET" }),
  post: <T>(endpoint: string, body?: unknown, options?: RequestInit) =>
    request<T>(endpoint, {
      ...options,
      method: "POST",
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    }),
  put: <T>(endpoint: string, body?: unknown, options?: RequestInit) =>
    request<T>(endpoint, {
      ...options,
      method: "PUT",
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(endpoint: string, body?: unknown, options?: RequestInit) =>
    request<T>(endpoint, {
      ...options,
      method: "PATCH",
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(endpoint: string, options?: RequestInit) => request<T>(endpoint, { ...options, method: "DELETE" }),
};

export const authApi = {
  login: async (credentials: LoginCredentials): Promise<Token> => {
    return apiClient.post<Token>("/api/v1/auth/login", credentials);
  },
  register: async (userData: RegisterCredentials): Promise<User> => {
    return apiClient.post<User>("/api/v1/auth/register", userData);
  },
  getMe: async (): Promise<User> => {
    return apiClient.get<User>("/api/v1/auth/me");
  },
  updateProfile: async (data: UserProfileUpdatePayload): Promise<User> => {
    return apiClient.patch<User>("/api/v1/auth/me", data);
  },
  changePassword: async (data: UserPasswordChangePayload): Promise<{ message: string }> => {
    return apiClient.post<{ message: string }>("/api/v1/auth/me/password", data);
  },
};

export const dashboardApi = {
  getStats: async (params?: DashboardFilterParams): Promise<DashboardStats> => {
    const searchParams = new URLSearchParams();
    if (params?.companyId) searchParams.set("company_id", String(params.companyId));
    if (params?.emailAccountId) searchParams.set("email_account_id", String(params.emailAccountId));
    if (params?.allTime) searchParams.set("all_time", "true");
    if (params?.dateFrom) searchParams.set("date_from", params.dateFrom);
    if (params?.dateTo) searchParams.set("date_to", params.dateTo);
    const qs = searchParams.toString();
    const endpoint = params?.companyId
      ? `/api/v1/companies/${params.companyId}/emails/dashboard/stats${qs ? `?${qs}` : ""}`
      : `/api/v1/emails/dashboard/stats${qs ? `?${qs}` : ""}`;
    return apiClient.get<DashboardStats>(endpoint);
  },

  getActivity: async (params?: DashboardFilterParams): Promise<DashboardActivityResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.companyId) searchParams.set("company_id", String(params.companyId));
    if (params?.emailAccountId) searchParams.set("email_account_id", String(params.emailAccountId));
    if (params?.allTime) searchParams.set("all_time", "true");
    if (params?.dateFrom) searchParams.set("date_from", params.dateFrom);
    if (params?.dateTo) searchParams.set("date_to", params.dateTo);
    const qs = searchParams.toString();
    const endpoint = params?.companyId
      ? `/api/v1/companies/${params.companyId}/emails/dashboard/activity${qs ? `?${qs}` : ""}`
      : `/api/v1/emails/dashboard/activity${qs ? `?${qs}` : ""}`;
    return apiClient.get<DashboardActivityResponse>(endpoint);
  },

  getAccountHealth: async (companyId?: number): Promise<AccountHealthResponse> => {
    const endpoint = companyId
      ? `/api/v1/companies/${companyId}/emails/dashboard/account-health`
      : "/api/v1/emails/dashboard/account-health";
    return apiClient.get<AccountHealthResponse>(endpoint);
  },
};

export interface MailboxCounts {
  inbox: number;
  unread: number;
  sent: number;
  drafts: number;
  responses: number;
  bounced: number;
  trash: number;
}

export const emailsApi = {
  listEmails: async (params?: EmailListParams): Promise<EmailListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.folder) searchParams.set("folder", params.folder);
    if (params?.status) searchParams.set("status", params.status);
    if (params?.direction) searchParams.set("direction", params.direction);
    if (params?.emailAccountId) searchParams.set("email_account_id", String(params.emailAccountId));
    if (params?.companyId) searchParams.set("company_id", String(params.companyId));
    if (params?.isRead !== undefined) searchParams.set("is_read", String(params.isRead));
    if (params?.isStarred !== undefined) searchParams.set("is_starred", String(params.isStarred));
    if (params?.search) searchParams.set("search", params.search);
    if (params?.dateFrom) searchParams.set("date_from", params.dateFrom);
    if (params?.dateTo) searchParams.set("date_to", params.dateTo);
    if (params?.sort) searchParams.set("sort", params.sort);
    if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
    if (params?.offset !== undefined) searchParams.set("offset", String(params.offset));
    const qs = searchParams.toString();
    const endpoint = params?.companyId
      ? `/api/v1/companies/${params.companyId}/emails${qs ? `?${qs}` : ""}`
      : `/api/v1/emails${qs ? `?${qs}` : ""}`;
    return apiClient.get<EmailListResponse>(endpoint);
  },

  getEmailById: async (id: number, companyId?: number): Promise<EmailItem> => {
    const endpoint = companyId ? `/api/v1/companies/${companyId}/emails/${id}` : `/api/v1/emails/${id}`;
    return apiClient.get<EmailItem>(endpoint);
  },

  markRead: async (id: number, isRead: boolean): Promise<EmailItem> => {
    return apiClient.patch<EmailItem>(`/api/v1/emails/${id}/read`, { is_read: isRead });
  },

  markStarred: async (id: number, isStarred: boolean): Promise<EmailItem> => {
    return apiClient.patch<EmailItem>(`/api/v1/emails/${id}/star`, { is_starred: isStarred });
  },

  softDelete: async (id: number): Promise<EmailItem> => {
    return apiClient.delete<EmailItem>(`/api/v1/emails/${id}`);
  },

  restore: async (id: number): Promise<EmailItem> => {
    return apiClient.patch<EmailItem>(`/api/v1/emails/${id}/restore`);
  },

  permanentDelete: async (id: number): Promise<{ message: string; id: number }> => {
    return apiClient.delete<{ message: string; id: number }>(`/api/v1/emails/${id}/permanent`);
  },

  getThread: async (threadId: number, companyId?: number): Promise<EmailThreadDetail> => {
    const endpoint = companyId ? `/api/v1/companies/${companyId}/threads/${threadId}` : `/api/v1/threads/${threadId}`;
    return apiClient.get<EmailThreadDetail>(endpoint);
  },

  getAttachments: async (emailId: number, companyId?: number): Promise<AttachmentListResponse> => {
    const endpoint = companyId
      ? `/api/v1/companies/${companyId}/emails/${emailId}/attachments`
      : `/api/v1/emails/${emailId}/attachments`;
    return apiClient.get<AttachmentListResponse>(endpoint);
  },

  downloadAttachment: async (emailId: number, attachmentId: number): Promise<Blob> => {
    const token = tokenStorage.get();
    const headers = new Headers();
    if (token) headers.set("Authorization", `Bearer ${token}`);
    const url = `${API_BASE_URL}/api/v1/emails/${emailId}/attachments/${attachmentId}/download`;
    const res = await fetch(url, { headers });
    if (!res.ok) throw new Error("Failed to download attachment");
    return res.blob();
  },

  sendEmail: async (payload: EmailSendPayload): Promise<EmailItem> => {
    return apiClient.post<EmailItem>("/api/v1/emails/send", payload);
  },

  createDraft: async (payload: EmailDraftPayload): Promise<EmailItem> => {
    return apiClient.post<EmailItem>("/api/v1/emails/drafts", payload);
  },

  getDraft: async (draftId: number): Promise<EmailItem> => {
    return apiClient.get<EmailItem>(`/api/v1/emails/drafts/${draftId}`);
  },

  updateDraft: async (draftId: number, payload: Partial<EmailDraftPayload>): Promise<EmailItem> => {
    return apiClient.put<EmailItem>(`/api/v1/emails/drafts/${draftId}`, payload);
  },

  sendDraft: async (draftId: number): Promise<EmailItem> => {
    return apiClient.post<EmailItem>(`/api/v1/emails/drafts/${draftId}/send`);
  },

  discardDraft: async (draftId: number): Promise<void> => {
    return apiClient.delete<void>(`/api/v1/emails/drafts/${draftId}`);
  },

  uploadDraftAttachment: async (draftId: number, file: File): Promise<AttachmentItem> => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient.post<AttachmentItem>(`/api/v1/emails/drafts/${draftId}/attachments`, formData);
  },

  listDraftAttachments: async (draftId: number): Promise<AttachmentItem[]> => {
    const res = await apiClient.get<AttachmentListResponse>(`/api/v1/emails/drafts/${draftId}/attachments`);
    return res.attachments;
  },

  deleteDraftAttachment: async (draftId: number, attachmentId: number): Promise<void> => {
    return apiClient.delete<void>(`/api/v1/emails/drafts/${draftId}/attachments/${attachmentId}`);
  },

  applyTemplateToDraft: async (
    draftId: number,
    templateId: number,
    signatureId?: number
  ): Promise<EmailItem> => {
    const qs = signatureId ? `?signature_id=${signatureId}` : "";
    return apiClient.post<EmailItem>(`/api/v1/emails/drafts/${draftId}/apply-template/${templateId}${qs}`);
  },

  getRecentEmails: async (limit: number = 7, companyId?: number): Promise<EmailListResponse> => {
    const searchParams = new URLSearchParams();
    searchParams.set("limit", String(limit));
    searchParams.set("sort", "newest");
    if (companyId) searchParams.set("company_id", String(companyId));
    return apiClient.get<EmailListResponse>(`/api/v1/emails?${searchParams.toString()}`);
  },

  getFolderCount: async (folder: string, companyId?: number): Promise<number> => {
    const searchParams = new URLSearchParams();
    searchParams.set("folder", folder);
    searchParams.set("limit", "1");
    if (companyId) searchParams.set("company_id", String(companyId));
    const endpoint = companyId
      ? `/api/v1/companies/${companyId}/emails?${searchParams.toString()}`
      : `/api/v1/emails?${searchParams.toString()}`;
    const res = await apiClient.get<EmailListResponse>(endpoint);
    return res.total;
  },

  getMailboxCounts: async (companyId?: number, emailAccountId?: number): Promise<MailboxCounts> => {
    try {
      const searchParams = new URLSearchParams();
      if (companyId) searchParams.set("company_id", String(companyId));
      if (emailAccountId) searchParams.set("email_account_id", String(emailAccountId));
      const qs = searchParams.toString();
      const endpoint = companyId
        ? `/api/v1/companies/${companyId}/emails/counts${qs ? `?${qs}` : ""}`
        : `/api/v1/emails/counts${qs ? `?${qs}` : ""}`;
      return await apiClient.get<MailboxCounts>(endpoint);
    } catch {
      // Fallback for resilient operation
      const folders = ["inbox", "sent", "drafts", "responses", "bounced", "trash"] as const;
      const countPromises = folders.map(async (folder) => {
        try {
          const count = await emailsApi.getFolderCount(folder, companyId);
          return [folder, count] as const;
        } catch {
          return [folder, 0] as const;
        }
      });

      const results = await Promise.all(countPromises);
      const countsMap = Object.fromEntries(results) as Record<string, number>;

      return {
        inbox: countsMap.inbox ?? 0,
        unread: 0,
        sent: countsMap.sent ?? 0,
        drafts: countsMap.drafts ?? 0,
        responses: countsMap.responses ?? 0,
        bounced: countsMap.bounced ?? 0,
        trash: countsMap.trash ?? 0,
      };
    }
  },
};

export interface TemplateFilterParams {
  companyId?: number;
  emailAccountId?: number;
  isActive?: boolean;
  limit?: number;
  offset?: number;
}

export const templatesApi = {
  listTemplates: async (
    paramsOrAccountId?: number | TemplateFilterParams
  ): Promise<EmailTemplateItem[]> => {
    let params: TemplateFilterParams = {};
    if (typeof paramsOrAccountId === "number") {
      params = { emailAccountId: paramsOrAccountId };
    } else if (paramsOrAccountId) {
      params = paramsOrAccountId;
    }
    const searchParams = new URLSearchParams();
    if (params.companyId) searchParams.set("company_id", String(params.companyId));
    if (params.emailAccountId) searchParams.set("email_account_id", String(params.emailAccountId));
    if (params.isActive !== undefined) searchParams.set("is_active", String(params.isActive));
    if (params.limit) searchParams.set("limit", String(params.limit));
    if (params.offset) searchParams.set("offset", String(params.offset));
    const qs = searchParams.toString();
    const endpoint = params.companyId
      ? `/api/v1/companies/${params.companyId}/templates${qs ? `?${qs}` : ""}`
      : `/api/v1/templates${qs ? `?${qs}` : ""}`;
    const res = await apiClient.get<EmailTemplateListResponse>(endpoint);
    return res.templates;
  },

  listTemplatesWithTotal: async (
    params?: TemplateFilterParams
  ): Promise<EmailTemplateListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.companyId) searchParams.set("company_id", String(params.companyId));
    if (params?.emailAccountId) searchParams.set("email_account_id", String(params.emailAccountId));
    if (params?.isActive !== undefined) searchParams.set("is_active", String(params.isActive));
    if (params?.limit) searchParams.set("limit", String(params.limit));
    if (params?.offset) searchParams.set("offset", String(params.offset));
    const qs = searchParams.toString();
    const endpoint = params?.companyId
      ? `/api/v1/companies/${params.companyId}/templates${qs ? `?${qs}` : ""}`
      : `/api/v1/templates${qs ? `?${qs}` : ""}`;
    return apiClient.get<EmailTemplateListResponse>(endpoint);
  },

  getTemplate: async (templateId: number, companyId?: number): Promise<EmailTemplateItem> => {
    const endpoint = companyId
      ? `/api/v1/companies/${companyId}/templates/${templateId}`
      : `/api/v1/templates/${templateId}`;
    return apiClient.get<EmailTemplateItem>(endpoint);
  },

  createTemplate: async (
    payload: EmailTemplateCreatePayload,
    companyId?: number
  ): Promise<EmailTemplateItem> => {
    const endpoint = companyId
      ? `/api/v1/companies/${companyId}/templates`
      : `/api/v1/templates`;
    return apiClient.post<EmailTemplateItem>(endpoint, payload);
  },

  updateTemplate: async (
    templateId: number,
    payload: EmailTemplateUpdatePayload,
    companyId?: number
  ): Promise<EmailTemplateItem> => {
    const endpoint = companyId
      ? `/api/v1/companies/${companyId}/templates/${templateId}`
      : `/api/v1/templates/${templateId}`;
    return apiClient.put<EmailTemplateItem>(endpoint, payload);
  },

  deleteTemplate: async (templateId: number, companyId?: number): Promise<void> => {
    const endpoint = companyId
      ? `/api/v1/companies/${companyId}/templates/${templateId}`
      : `/api/v1/templates/${templateId}`;
    return apiClient.delete<void>(endpoint);
  },

  toggleTemplateActive: async (
    templateId: number,
    isActive?: boolean,
    companyId?: number
  ): Promise<EmailTemplateItem> => {
    const endpoint = companyId
      ? `/api/v1/companies/${companyId}/templates/${templateId}/active`
      : `/api/v1/templates/${templateId}/active`;
    const body = isActive !== undefined ? { is_active: isActive } : undefined;
    return apiClient.patch<EmailTemplateItem>(endpoint, body);
  },
};

export const signaturesApi = {
  listSignatures: async (accountId?: number, companyId?: number): Promise<EmailSignatureItem[]> => {
    const params = new URLSearchParams();
    if (accountId) params.append("email_account_id", String(accountId));
    if (companyId) params.append("company_id", String(companyId));
    params.append("limit", "100");
    const url = `/api/v1/signatures?${params.toString()}`;
    const res = await apiClient.get<EmailSignatureListResponse>(url);
    return res.signatures;
  },

  getSignature: async (signatureId: number): Promise<EmailSignatureItem> => {
    return apiClient.get<EmailSignatureItem>(`/api/v1/signatures/${signatureId}`);
  },

  createSignature: async (data: EmailSignatureCreatePayload): Promise<EmailSignatureItem> => {
    return apiClient.post<EmailSignatureItem>("/api/v1/signatures", data);
  },

  updateSignature: async (
    signatureId: number,
    data: EmailSignatureUpdatePayload
  ): Promise<EmailSignatureItem> => {
    return apiClient.put<EmailSignatureItem>(`/api/v1/signatures/${signatureId}`, data);
  },

  deleteSignature: async (signatureId: number): Promise<void> => {
    return apiClient.delete<void>(`/api/v1/signatures/${signatureId}`);
  },

  setDefaultSignature: async (signatureId: number): Promise<EmailSignatureItem> => {
    return apiClient.post<EmailSignatureItem>(`/api/v1/signatures/${signatureId}/set-default`);
  },

  getDefaultSignature: async (accountId: number): Promise<EmailSignatureItem | null> => {
    return apiClient.get<EmailSignatureItem | null>(`/api/v1/signatures/default?email_account_id=${accountId}`);
  },

};

export const companiesApi = {
  getMyCompanies: async (): Promise<CompanyWithRole[]> => {
    return apiClient.get<CompanyWithRole[]>("/api/v1/companies/");
  },

  createCompany: async (name: string): Promise<CompanyWithRole> => {
    return apiClient.post<CompanyWithRole>("/api/v1/companies/", { name });
  },

  updateCompany: async (companyId: number, data: CompanyUpdatePayload): Promise<CompanyWithRole> => {
    return apiClient.patch<CompanyWithRole>(`/api/v1/companies/${companyId}`, data);
  },

  getMembers: async (companyId: number): Promise<CompanyMember[]> => {
    return apiClient.get<CompanyMember[]>(`/api/v1/companies/${companyId}/members`);
  },

  addMember: async (companyId: number, data: CompanyMemberAddPayload): Promise<CompanyMember> => {
    return apiClient.post<CompanyMember>(`/api/v1/companies/${companyId}/members`, data);
  },

  updateMemberRole: async (
    companyId: number,
    userId: number,
    data: CompanyMemberRoleUpdatePayload
  ): Promise<CompanyMember> => {
    return apiClient.put<CompanyMember>(`/api/v1/companies/${companyId}/members/${userId}/role`, data);
  },

  removeMember: async (companyId: number, userId: number): Promise<void> => {
    return apiClient.delete<void>(`/api/v1/companies/${companyId}/members/${userId}`);
  },

  getCompanyEmailAccountsAccess: async (companyId: number): Promise<EmailAccountAccessItem[]> => {
    return apiClient.get<EmailAccountAccessItem[]>(`/api/v1/companies/${companyId}/email-accounts-access`);
  },
};

export const invitationsApi = {
  getMyPendingInvitations: async (): Promise<UserInvitationItem[]> => {
    return apiClient.get<UserInvitationItem[]>("/api/v1/invitations/my-pending");
  },

  acceptInvitation: async (invitationId: number): Promise<CompanyWithRole> => {
    return apiClient.post<CompanyWithRole>(`/api/v1/invitations/${invitationId}/accept`);
  },

  declineInvitation: async (invitationId: number): Promise<UserInvitationItem> => {
    return apiClient.post<UserInvitationItem>(`/api/v1/invitations/${invitationId}/decline`);
  },

  createInvitation: async (
    companyId: number,
    data: { email: string; role: "ADMIN" | "MEMBER" }
  ): Promise<CompanyInvitationItem> => {
    return apiClient.post<CompanyInvitationItem>(`/api/v1/companies/${companyId}/invitations`, data);
  },

  getCompanyInvitations: async (
    companyId: number,
    statusFilter?: "PENDING" | "ACCEPTED" | "DECLINED" | "REVOKED"
  ): Promise<CompanyInvitationItem[]> => {
    const qs = statusFilter ? `?status_filter=${statusFilter}` : "";
    return apiClient.get<CompanyInvitationItem[]>(`/api/v1/companies/${companyId}/invitations${qs}`);
  },

  revokeInvitation: async (companyId: number, invitationId: number): Promise<void> => {
    return apiClient.delete<void>(`/api/v1/companies/${companyId}/invitations/${invitationId}`);
  },

  resendInvitation: async (companyId: number, invitationId: number): Promise<CompanyInvitationItem> => {
    return apiClient.post<CompanyInvitationItem>(`/api/v1/companies/${companyId}/invitations/${invitationId}/resend`);
  },
};

export const emailAccountsApi = {
  getAuthorizedAccounts: async (): Promise<AuthorizedEmailAccount[]> => {
    return apiClient.get<AuthorizedEmailAccount[]>("/api/v1/email-accounts/authorized");
  },

  listCompanyAccounts: async (companyId: number): Promise<EmailAccountItem[]> => {
    return apiClient.get<EmailAccountItem[]>(`/api/v1/companies/${companyId}/email-accounts`);
  },

  createAccount: async (companyId: number, data: EmailAccountCreatePayload): Promise<EmailAccountItem> => {
    return apiClient.post<EmailAccountItem>(`/api/v1/companies/${companyId}/email-accounts`, data);
  },

  updateAccount: async (companyId: number, accountId: number, data: EmailAccountUpdatePayload): Promise<EmailAccountItem> => {
    return apiClient.put<EmailAccountItem>(`/api/v1/companies/${companyId}/email-accounts/${accountId}`, data);
  },

  deleteAccount: async (companyId: number, accountId: number): Promise<void> => {
    return apiClient.delete<void>(`/api/v1/companies/${companyId}/email-accounts/${accountId}`);
  },

  triggerSync: async (
    accountId: number,
    background: boolean = false
  ): Promise<EmailSyncResult | EmailSyncJobResponse> => {
    return apiClient.post<EmailSyncResult | EmailSyncJobResponse>(
      `/api/v1/email-accounts/${accountId}/sync?background=${background}`
    );
  },

  listAccountAccess: async (companyId: number, accountId: number): Promise<EmailAccountAccessItem[]> => {
    return apiClient.get<EmailAccountAccessItem[]>(`/api/v1/companies/${companyId}/email-accounts/${accountId}/access`);
  },

  grantAccess: async (
    companyId: number,
    accountId: number,
    userId: number
  ): Promise<EmailAccountAccessItem> => {
    return apiClient.post<EmailAccountAccessItem>(
      `/api/v1/companies/${companyId}/email-accounts/${accountId}/access`,
      { user_id: userId }
    );
  },

  revokeAccess: async (
    companyId: number,
    accountId: number,
    userId: number
  ): Promise<void> => {
    return apiClient.delete<void>(
      `/api/v1/companies/${companyId}/email-accounts/${accountId}/access/${userId}`
    );
  },
};

export const domainsApi = {
  listDomains: async (companyId: number): Promise<Domain[]> => {
    return apiClient.get<Domain[]>(`/api/v1/companies/${companyId}/domains`);
  },

  getDomain: async (companyId: number, domainId: number): Promise<Domain> => {
    return apiClient.get<Domain>(`/api/v1/companies/${companyId}/domains/${domainId}`);
  },

  createDomain: async (companyId: number, payload: DomainCreatePayload): Promise<Domain> => {
    return apiClient.post<Domain>(`/api/v1/companies/${companyId}/domains`, payload);
  },

  updateDomain: async (
    companyId: number,
    domainId: number,
    payload: DomainUpdatePayload
  ): Promise<Domain> => {
    return apiClient.patch<Domain>(`/api/v1/companies/${companyId}/domains/${domainId}`, payload);
  },

  deleteDomain: async (companyId: number, domainId: number): Promise<void> => {
    return apiClient.delete<void>(`/api/v1/companies/${companyId}/domains/${domainId}`);
  },

  verifyDomain: async (companyId: number, domainId: number): Promise<Domain> => {
    return apiClient.post<Domain>(`/api/v1/companies/${companyId}/domains/${domainId}/verify`);
  },
};

export const campaignsApi = {
  listCampaigns: async (
    companyId: number,
    params?: CampaignListParams
  ): Promise<Campaign[]> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
    if (params?.offset !== undefined) searchParams.set("offset", String(params.offset));
    const qs = searchParams.toString();
    return apiClient.get<Campaign[]>(
      `/api/v1/companies/${companyId}/campaigns${qs ? `?${qs}` : ""}`
    );
  },

  getCampaign: async (
    companyId: number,
    campaignId: number
  ): Promise<CampaignDetail> => {
    return apiClient.get<CampaignDetail>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}`
    );
  },

  createCampaign: async (
    companyId: number,
    payload: CampaignCreatePayload
  ): Promise<Campaign> => {
    return apiClient.post<Campaign>(
      `/api/v1/companies/${companyId}/campaigns`,
      payload
    );
  },

  updateCampaign: async (
    companyId: number,
    campaignId: number,
    payload: CampaignUpdatePayload
  ): Promise<Campaign> => {
    return apiClient.patch<Campaign>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}`,
      payload
    );
  },

  deleteCampaign: async (
    companyId: number,
    campaignId: number
  ): Promise<void> => {
    return apiClient.delete<void>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}`
    );
  },

  preflightCampaign: async (
    companyId: number,
    campaignId: number
  ): Promise<CampaignPreflightResponse> => {
    return apiClient.post<CampaignPreflightResponse>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/preflight`
    );
  },

  dispatchCampaign: async (
    companyId: number,
    campaignId: number
  ): Promise<CampaignDispatchResponse> => {
    return apiClient.post<CampaignDispatchResponse>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/dispatch`
    );
  },

  scheduleCampaign: async (
    companyId: number,
    campaignId: number,
    payload?: CampaignSchedulePayload
  ): Promise<Campaign> => {
    return apiClient.post<Campaign>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/schedule`,
      payload
    );
  },

  pauseCampaign: async (
    companyId: number,
    campaignId: number
  ): Promise<Campaign> => {
    return apiClient.post<Campaign>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/pause`
    );
  },

  resumeCampaign: async (
    companyId: number,
    campaignId: number
  ): Promise<Campaign> => {
    return apiClient.post<Campaign>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/resume`
    );
  },

  cancelCampaign: async (
    companyId: number,
    campaignId: number
  ): Promise<Campaign> => {
    return apiClient.post<Campaign>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/cancel`
    );
  },

  listRecipients: async (
    companyId: number,
    campaignId: number,
    params?: CampaignRecipientListParams
  ): Promise<CampaignRecipient[]> => {
    const searchParams = new URLSearchParams();
    if (params?.status && params.status !== "ALL") searchParams.set("status", params.status);
    if (params?.search) searchParams.set("search", params.search);
    if (params?.limit !== undefined) searchParams.set("limit", String(params.limit));
    if (params?.offset !== undefined) searchParams.set("offset", String(params.offset));
    const qs = searchParams.toString();
    return apiClient.get<CampaignRecipient[]>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/recipients${qs ? `?${qs}` : ""}`
    );
  },

  getRecipient: async (
    companyId: number,
    campaignId: number,
    recipientId: number
  ): Promise<CampaignRecipient> => {
    return apiClient.get<CampaignRecipient>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/recipients/${recipientId}`
    );
  },

  createRecipient: async (
    companyId: number,
    campaignId: number,
    payload: CampaignRecipientCreatePayload
  ): Promise<CampaignRecipient> => {
    return apiClient.post<CampaignRecipient>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/recipients`,
      payload
    );
  },

  bulkCreateRecipients: async (
    companyId: number,
    campaignId: number,
    payload: CampaignRecipientBulkCreateRequest
  ): Promise<CampaignRecipientBulkCreateResponse> => {
    return apiClient.post<CampaignRecipientBulkCreateResponse>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/recipients/bulk`,
      payload
    );
  },

  updateRecipient: async (
    companyId: number,
    campaignId: number,
    recipientId: number,
    payload: CampaignRecipientUpdatePayload
  ): Promise<CampaignRecipient> => {
    return apiClient.patch<CampaignRecipient>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/recipients/${recipientId}`,
      payload
    );
  },

  deleteRecipient: async (
    companyId: number,
    campaignId: number,
    recipientId: number
  ): Promise<void> => {
    return apiClient.delete<void>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/recipients/${recipientId}`
    );
  },

  importRecipientsCsv: async (
    companyId: number,
    campaignId: number,
    file: File
  ): Promise<CampaignRecipientImportResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient.post<CampaignRecipientImportResponse>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/recipients/import`,
      formData
    );
  },

  uploadAttachment: async (
    companyId: number,
    campaignId: number,
    file: File
  ): Promise<CampaignAttachment> => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient.post<CampaignAttachment>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/attachments`,
      formData
    );
  },

  listAttachments: async (
    companyId: number,
    campaignId: number
  ): Promise<CampaignAttachment[]> => {
    const res = await apiClient.get<{ attachments: CampaignAttachment[] }>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/attachments`
    );
    return res.attachments || [];
  },

  deleteAttachment: async (
    companyId: number,
    campaignId: number,
    attachmentId: number
  ): Promise<void> => {
    return apiClient.delete<void>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/attachments/${attachmentId}`
    );
  },

  getAttachmentDownloadUrl: (
    companyId: number,
    campaignId: number,
    attachmentId: number
  ): string => {
    const base = import.meta.env.VITE_API_URL || "";
    return `${base}/api/v1/companies/${companyId}/campaigns/${campaignId}/attachments/${attachmentId}/download`;
  },

  importDraft: async (
    companyId: number,
    campaignId: number,
    draftId: number
  ): Promise<Campaign> => {
    return apiClient.post<Campaign>(
      `/api/v1/companies/${companyId}/campaigns/${campaignId}/import-draft`,
      { draft_id: draftId }
    );
  },
};


// Preserved existing health check functions
export async function fetchHealth(): Promise<HealthResponse> {
  return apiClient.get<HealthResponse>("/api/v1/health");
}

export async function fetchPing(): Promise<{ status: string }> {
  return apiClient.get<{ status: string }>("/api/v1/ping");
}

