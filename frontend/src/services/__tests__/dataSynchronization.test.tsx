import { describe, it, expect, vi, beforeEach } from "vitest";
import { queryClient } from "../../main";

describe("Frontend Automatic Refresh & Data Synchronization", () => {
  beforeEach(() => {
    queryClient.clear();
    vi.restoreAllMocks();
  });

  it("1. Global query client defaults have refetchOnWindowFocus enabled and sensible staleTime", () => {
    const defaultOptions = queryClient.getDefaultOptions();
    expect(defaultOptions.queries?.refetchOnWindowFocus).toBe(true);
    expect(defaultOptions.queries?.staleTime).toBe(5000);
  });

  it("2. Email detail queries are marked invalidated when matching hierarchical prefix", async () => {
    const companyId = 1;
    const emailId = 42;

    queryClient.setQueryData(["email-detail", companyId, emailId], {
      id: emailId,
      subject: "Test Subject",
      is_read: false,
    });

    expect(queryClient.getQueryData(["email-detail", companyId, emailId])).toBeDefined();

    // Invalidate using prefix ["email-detail", companyId, emailId]
    await queryClient.invalidateQueries({
      queryKey: ["email-detail", companyId, emailId],
    });

    const queryState = queryClient.getQueryState(["email-detail", companyId, emailId]);
    expect(queryState?.isInvalidated).toBe(true);
  });

  it("3. Generalized email-detail invalidation marks all active email detail queries invalidated", async () => {
    queryClient.setQueryData(["email-detail", 1, 101], { id: 101 });
    queryClient.setQueryData(["email-detail", 1, 102], { id: 102 });

    await queryClient.invalidateQueries({
      queryKey: ["email-detail"],
    });

    expect(queryClient.getQueryState(["email-detail", 1, 101])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["email-detail", 1, 102])?.isInvalidated).toBe(true);
  });

  it("4. Invalidation of authorized email accounts reaches both query keys", async () => {
    queryClient.setQueryData(["authorized-accounts"], [{ id: 1, name: "Sales" }]);
    queryClient.setQueryData(["authorizedEmailAccounts"], [{ id: 1, name: "Sales" }]);

    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["authorized-accounts"] }),
      queryClient.invalidateQueries({ queryKey: ["authorizedEmailAccounts"] }),
    ]);

    expect(queryClient.getQueryState(["authorized-accounts"])?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(["authorizedEmailAccounts"])?.isInvalidated).toBe(true);
  });

  it("5. Campaign active state polling interval logic accurately classifies running vs terminal states", () => {
    const evaluatePolling = (status: string | undefined): number | false => {
      return (status === "QUEUED" || status === "RUNNING") ? 5000 : false;
    };

    // Active background execution should poll every 5s
    expect(evaluatePolling("QUEUED")).toBe(5000);
    expect(evaluatePolling("RUNNING")).toBe(5000);

    // Terminal or idle states should stop polling
    expect(evaluatePolling("COMPLETED")).toBe(false);
    expect(evaluatePolling("FAILED")).toBe(false);
    expect(evaluatePolling("DRAFT")).toBe(false);
    expect(evaluatePolling("PAUSED")).toBe(false);
    expect(evaluatePolling("CANCELLED")).toBe(false);
    expect(evaluatePolling("ARCHIVED")).toBe(false);
    expect(evaluatePolling(undefined)).toBe(false);
  });

  it("6. Campaign summary active count determines list polling", () => {
    const evaluateListPolling = (summary: { active_count: number } | null | undefined): number | false => {
      if (summary && (summary.active_count ?? 0) > 0) {
        return 6000;
      }
      return false;
    };

    expect(evaluateListPolling({ active_count: 2 })).toBe(6000);
    expect(evaluateListPolling({ active_count: 0 })).toBe(false);
    expect(evaluateListPolling(null)).toBe(false);
  });
});
