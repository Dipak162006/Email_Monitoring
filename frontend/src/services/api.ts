import type { LoginCredentials, RegisterCredentials, Token, User } from "../types/auth";
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

// Preserved existing health check functions
export async function fetchHealth(): Promise<HealthResponse> {
  return apiClient.get<HealthResponse>("/api/v1/health");
}

export async function fetchPing(): Promise<{ status: string }> {
  return apiClient.get<{ status: string }>("/api/v1/ping");
}
