import type { LoginCredentials, RegisterCredentials, Token, User } from "../types/auth";
import type {
  AccountHealthResponse,
  DashboardActivityResponse,
  DashboardFilterParams,
  DashboardStats,
} from "../types/dashboard";
import type { EmailListResponse } from "../types/emails";
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
      body: body ? JSON.stringify(body) : undefined,
    }),
  put: <T>(endpoint: string, body?: unknown, options?: RequestInit) =>
    request<T>(endpoint, {
      ...options,
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
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


export const emailAccountsApi = {
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

