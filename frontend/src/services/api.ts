import type { LoginCredentials, RegisterCredentials, Token, User } from "../types/auth";
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
  EmailDraftPayload,
  EmailItem,
  EmailListParams,
  EmailListResponse,
  EmailSendPayload,
  EmailSignatureItem,
  EmailSignatureListResponse,
  EmailTemplateItem,
  EmailTemplateListResponse,
  EmailThreadDetail,
} from "../types/emails";
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
};

export const dashboardApi = {
  getStats: async (params?: DashboardFilterParams): Promise<DashboardStats> => {
    const searchParams = new URLSearchParams();
    if (params?.companyId) searchParams.set("company_id", String(params.companyId));
    if (params?.emailAccountId) searchParams.set("email_account_id", String(params.emailAccountId));
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

  getMailboxCounts: async (companyId?: number): Promise<MailboxCounts> => {
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
      sent: countsMap.sent ?? 0,
      drafts: countsMap.drafts ?? 0,
      responses: countsMap.responses ?? 0,
      bounced: countsMap.bounced ?? 0,
      trash: countsMap.trash ?? 0,
    };
  },
};

export const templatesApi = {
  listTemplates: async (accountId?: number): Promise<EmailTemplateItem[]> => {
    const url = accountId ? `/api/v1/templates?email_account_id=${accountId}` : "/api/v1/templates";
    const res = await apiClient.get<EmailTemplateListResponse>(url);
    return res.templates;
  },
};

export const signaturesApi = {
  listSignatures: async (accountId?: number): Promise<EmailSignatureItem[]> => {
    const url = accountId ? `/api/v1/signatures?email_account_id=${accountId}` : "/api/v1/signatures";
    const res = await apiClient.get<EmailSignatureListResponse>(url);
    return res.signatures;
  },
};

export const emailAccountsApi = {
  getAuthorizedAccounts: async (): Promise<AuthorizedEmailAccount[]> => {
    return apiClient.get<AuthorizedEmailAccount[]>("/api/v1/email-accounts/authorized");
  },

  triggerSync: async (accountId: number, background: boolean = true): Promise<{ message?: string; status?: string }> => {
    return apiClient.post<{ message?: string; status?: string }>(
      `/api/v1/email-accounts/${accountId}/sync?background=${background}`
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

