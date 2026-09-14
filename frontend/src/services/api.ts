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

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/health`);
  if (!response.ok) {
    throw new Error(`Health check failed with HTTP status ${response.status}`);
  }
  return response.json();
}

export async function fetchPing(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE_URL}/api/v1/ping`);
  if (!response.ok) {
    throw new Error(`Ping check failed with HTTP status ${response.status}`);
  }
  return response.json();
}
