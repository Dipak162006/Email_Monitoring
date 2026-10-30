import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, waitFor, act } from "@testing-library/react";
import {
  apiClient,
  authApi,
  tokenStorage,
  onUnauthorized,
} from "../api";
import { AuthProvider } from "../../context/AuthContext";
import { useAuth } from "../../hooks/useAuth";

describe("Authentication Refresh Security & Verification", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    onUnauthorized(null);
  });

  it("1. Successful refresh: intercepts 401, fetches new token pair, and retries request successfully", async () => {
    tokenStorage.set("expired_access_token");
    tokenStorage.setRefreshToken("valid_refresh_token");

    let originalCallCount = 0;
    let refreshCallCount = 0;

    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);

      if (urlStr.includes("/api/v1/auth/refresh")) {
        refreshCallCount++;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              access_token: "refreshed_access_token",
              refresh_token: "refreshed_refresh_token",
              token_type: "bearer",
              expires_in: 3600,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }

      if (urlStr.includes("/api/v1/auth/me")) {
        originalCallCount++;
        const authHeader = (init?.headers as Headers)?.get("Authorization") || "";
        if (authHeader.includes("expired_access_token")) {
          return Promise.resolve(
            new Response(JSON.stringify({ detail: "Token has expired" }), {
              status: 401,
              headers: { "Content-Type": "application/json" },
            })
          );
        }
        if (authHeader.includes("refreshed_access_token")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: 42,
                email: "refreshed_user@example.com",
                full_name: "Refreshed User",
                is_active: true,
                created_at: "2026-10-30T00:00:00Z",
              }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
      }

      return Promise.reject(new Error(`Unhandled mock for ${urlStr}`));
    });

    const user = await authApi.getMe();

    expect(user.email).toBe("refreshed_user@example.com");
    expect(originalCallCount).toBe(2); // First failed (401), second succeeded (200)
    expect(refreshCallCount).toBe(1);
    expect(tokenStorage.get()).toBe("refreshed_access_token");
    expect(tokenStorage.getRefreshToken()).toBe("refreshed_refresh_token");
  });

  it("2. Concurrent 401 requests: deduplicates refresh call and resolves all requests", async () => {
    tokenStorage.set("expired_access_token");
    tokenStorage.setRefreshToken("valid_refresh_token");

    let refreshCallCount = 0;

    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);

      if (urlStr.includes("/api/v1/auth/refresh")) {
        refreshCallCount++;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              access_token: "deduped_access_token",
              refresh_token: "deduped_refresh_token",
              token_type: "bearer",
              expires_in: 3600,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }

      const authHeader = (init?.headers as Headers)?.get("Authorization") || "";
      if (authHeader.includes("expired_access_token")) {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Token has expired" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          })
        );
      }

      if (authHeader.includes("deduped_access_token")) {
        if (urlStr.includes("/api/v1/endpoint-a")) {
          return Promise.resolve(new Response(JSON.stringify({ result: "A" }), { status: 200 }));
        }
        if (urlStr.includes("/api/v1/endpoint-b")) {
          return Promise.resolve(new Response(JSON.stringify({ result: "B" }), { status: 200 }));
        }
        if (urlStr.includes("/api/v1/endpoint-c")) {
          return Promise.resolve(new Response(JSON.stringify({ result: "C" }), { status: 200 }));
        }
      }

      return Promise.reject(new Error(`Unhandled mock for ${urlStr}`));
    });

    // Fire 3 simultaneous API requests that all encounter 401
    const [resA, resB, resC] = await Promise.all([
      apiClient.get<{ result: string }>("/api/v1/endpoint-a"),
      apiClient.get<{ result: string }>("/api/v1/endpoint-b"),
      apiClient.get<{ result: string }>("/api/v1/endpoint-c"),
    ]);

    expect(resA.result).toBe("A");
    expect(resB.result).toBe("B");
    expect(resC.result).toBe("C");

    // CRITICAL: Despite 3 concurrent 401 responses, only 1 refresh request was made
    expect(refreshCallCount).toBe(1);
    expect(tokenStorage.get()).toBe("deduped_access_token");
    expect(tokenStorage.getRefreshToken()).toBe("deduped_refresh_token");
  });

  it("3. Failed refresh: clears tokens, notifies unauthorized listener, and throws RequestError", async () => {
    tokenStorage.set("expired_access_token");
    tokenStorage.setRefreshToken("revoked_refresh_token");

    const unauthorizedSpy = vi.fn();
    onUnauthorized(unauthorizedSpy);

    global.fetch = vi.fn().mockImplementation((url: string) => {
      const urlStr = String(url);

      if (urlStr.includes("/api/v1/auth/refresh")) {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Refresh token has been revoked" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          })
        );
      }

      if (urlStr.includes("/api/v1/auth/me")) {
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Token has expired" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          })
        );
      }

      return Promise.reject(new Error(`Unhandled mock for ${urlStr}`));
    });

    await expect(authApi.getMe()).rejects.toThrow();

    expect(tokenStorage.get()).toBeNull();
    expect(tokenStorage.getRefreshToken()).toBeNull();
    expect(unauthorizedSpy).toHaveBeenCalled();
  });

  it("4. Retry-loop prevention: ensures request is retried at most once after 401", async () => {
    tokenStorage.set("expired_access_token");
    tokenStorage.setRefreshToken("valid_refresh_token");

    let refreshCallCount = 0;
    let endpointCallCount = 0;

    global.fetch = vi.fn().mockImplementation((url: string) => {
      const urlStr = String(url);

      if (urlStr.includes("/api/v1/auth/refresh")) {
        refreshCallCount++;
        return Promise.resolve(
          new Response(
            JSON.stringify({
              access_token: "new_token_but_still_unauthorized",
              refresh_token: "new_refresh_token",
              token_type: "bearer",
              expires_in: 3600,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }

      if (urlStr.includes("/api/v1/protected/action")) {
        endpointCallCount++;
        // Always returns 401 even with fresh token
        return Promise.resolve(
          new Response(JSON.stringify({ detail: "Access denied" }), {
            status: 401,
            headers: { "Content-Type": "application/json" },
          })
        );
      }

      return Promise.reject(new Error(`Unhandled mock for ${urlStr}`));
    });

    await expect(apiClient.get("/api/v1/protected/action")).rejects.toThrow();

    // 1 original call + 1 retry = exactly 2 calls. No infinite loop!
    expect(endpointCallCount).toBe(2);
    // Refresh endpoint was called exactly once
    expect(refreshCallCount).toBe(1);
  });

  it("5. Server-side logout: calls /auth/logout with refresh token", async () => {
    let logoutPayload: unknown = null;

    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);
      if (urlStr.includes("/api/v1/auth/logout")) {
        logoutPayload = JSON.parse(String(init?.body));
        return Promise.resolve(
          new Response(JSON.stringify({ message: "Successfully logged out" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }
      return Promise.reject(new Error(`Unhandled mock for ${urlStr}`));
    });

    const res = await authApi.logout("active_token_to_revoke");

    expect(res.message).toBe("Successfully logged out");
    expect(logoutPayload).toEqual({ refresh_token: "active_token_to_revoke" });
  });

  it("6. Page reload with expired access token: AuthContext silently refreshes session", async () => {
    tokenStorage.set("expired_access_token");
    tokenStorage.setRefreshToken("valid_refresh_token");

    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);

      if (urlStr.includes("/api/v1/auth/refresh")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              access_token: "renewed_session_token",
              refresh_token: "renewed_session_refresh",
              token_type: "bearer",
              expires_in: 3600,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }

      if (urlStr.includes("/api/v1/auth/me")) {
        const authHeader = (init?.headers as Headers)?.get("Authorization") || "";
        if (authHeader.includes("expired_access_token")) {
          return Promise.resolve(
            new Response(JSON.stringify({ detail: "Token has expired" }), { status: 401 })
          );
        }
        if (authHeader.includes("renewed_session_token")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: 99,
                email: "restored_session@example.com",
                full_name: "Restored Session",
                is_active: true,
                created_at: "2026-10-30T00:00:00Z",
              }),
              { status: 200, headers: { "Content-Type": "application/json" } }
            )
          );
        }
      }

      return Promise.reject(new Error(`Unhandled mock for ${urlStr}`));
    });

    function TestConsumer() {
      const { user, isAuthenticated, isLoading } = useAuth();
      if (isLoading) return <div>Loading...</div>;
      return (
        <div>
          <span data-testid="auth-status">{isAuthenticated ? "authenticated" : "anonymous"}</span>
          <span data-testid="user-email">{user?.email || "none"}</span>
        </div>
      );
    }

    const { getByTestId } = render(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(getByTestId("auth-status").textContent).toBe("authenticated");
    });

    expect(getByTestId("user-email").textContent).toBe("restored_session@example.com");
    expect(tokenStorage.get()).toBe("renewed_session_token");
    expect(tokenStorage.getRefreshToken()).toBe("renewed_session_refresh");
  });

  it("7. AuthContext logout: calls server-side revocation and clears client state", async () => {
    tokenStorage.set("my_access_token");
    tokenStorage.setRefreshToken("my_refresh_token");

    let logoutCalledWith: unknown = null;

    global.fetch = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
      const urlStr = String(url);

      if (urlStr.includes("/api/v1/auth/me")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 1,
              email: "active@example.com",
              full_name: "Active User",
              is_active: true,
              created_at: "2026-10-30T00:00:00Z",
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }

      if (urlStr.includes("/api/v1/auth/logout")) {
        logoutCalledWith = JSON.parse(String(init?.body));
        return Promise.resolve(
          new Response(JSON.stringify({ message: "Successfully logged out" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          })
        );
      }

      return Promise.reject(new Error(`Unhandled mock for ${urlStr}`));
    });

    function LogoutConsumer() {
      const { isAuthenticated, logout } = useAuth();
      return (
        <div>
          <span data-testid="status">{isAuthenticated ? "logged_in" : "logged_out"}</span>
          <button data-testid="logout-btn" onClick={() => logout()}>
            Logout
          </button>
        </div>
      );
    }

    const { getByTestId } = render(
      <AuthProvider>
        <LogoutConsumer />
      </AuthProvider>
    );

    await waitFor(() => {
      expect(getByTestId("status").textContent).toBe("logged_in");
    });

    await act(async () => {
      getByTestId("logout-btn").click();
    });

    await waitFor(() => {
      expect(getByTestId("status").textContent).toBe("logged_out");
    });

    expect(logoutCalledWith).toEqual({ refresh_token: "my_refresh_token" });
    expect(tokenStorage.get()).toBeNull();
    expect(tokenStorage.getRefreshToken()).toBeNull();
  });
});
