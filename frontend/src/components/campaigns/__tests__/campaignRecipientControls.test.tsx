import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CampaignDetail, CampaignRecipient } from "../../../types/campaign";
import { campaignsApi } from "../../../services/api";
import { WorkspaceContext, type WorkspaceContextType } from "../../../context/WorkspaceContext";
import { AuthContext, type AuthContextType } from "../../../context/AuthContext";
import { CampaignRecipientsPage } from "../../../pages/CampaignRecipientsPage";

describe("Milestone M4 — Recipient Operational Controls", () => {
  let queryClient: QueryClient;

  const mockCompany = {
    id: 10,
    name: "Acme Corp",
    role: "ADMIN" as const,
    is_active: true,
    created_at: "2026-10-08T00:00:00Z",
  };

  const mockWorkspaceValue: WorkspaceContextType = {
    currentCompany: mockCompany,
    currentCompanyId: 10,
    currentRole: "ADMIN",
    companies: [mockCompany],
    memberships: [mockCompany],
    isLoading: false,
    isError: false,
    error: null,
    setActiveCompanyId: vi.fn(),
    refreshWorkspaces: vi.fn().mockResolvedValue(undefined),
    refetch: vi.fn().mockResolvedValue(undefined),
  };

  const mockAuthValue: AuthContextType = {
    user: { id: 1, email: "admin@example.com", is_active: true } as any,
    token: "test-token",
    isAuthenticated: true,
    isLoading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
    refreshUser: vi.fn(),
  };

  const liveCampaign: CampaignDetail = {
    id: 201,
    company_id: 10,
    email_account_id: 1,
    name: "Outreach 2026",
    subject: "Hello",
    status: "RUNNING",
    scheduled_at: null,
    started_at: "2026-10-27T00:00:00Z",
    completed_at: null,
    created_at: "2026-10-27T00:00:00Z",
    updated_at: "2026-10-27T00:00:00Z",
    recipient_count: 4,
  };

  const liveRecipients: CampaignRecipient[] = [
    {
      id: 1,
      campaign_id: 201,
      email: "scheduled@test.com",
      first_name: "Scheduled",
      status: "SENT",
      current_step_number: 1,
      next_step_due_at: "2026-10-30T14:00:00Z",
      created_at: "2026-10-27T00:00:00Z",
    },
    {
      id: 2,
      campaign_id: 201,
      email: "stopped@test.com",
      first_name: "Stopped",
      status: "STOPPED",
      stopped_reason: "MANUAL",
      created_at: "2026-10-27T00:00:00Z",
    },
    {
      id: 3,
      campaign_id: 201,
      email: "replied@test.com",
      first_name: "Replied",
      status: "STOPPED",
      stopped_reason: "REPLIED",
      created_at: "2026-10-27T00:00:00Z",
    },
    {
      id: 4,
      campaign_id: 201,
      email: "completed@test.com",
      first_name: "Completed",
      status: "COMPLETED",
      current_step_number: 3,
      created_at: "2026-10-27T00:00:00Z",
    },
  ];

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.restoreAllMocks();
  });

  const renderPage = (
    campaignId = 201,
    role: "OWNER" | "ADMIN" | "MEMBER" = "ADMIN"
  ) => {
    const wsValue: WorkspaceContextType = {
      ...mockWorkspaceValue,
      currentRole: role,
      currentCompany: { ...mockCompany, role },
    };

    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/campaigns/${campaignId}/recipients`]}>
          <AuthContext.Provider value={mockAuthValue}>
            <WorkspaceContext.Provider value={wsValue}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/recipients"
                  element={<CampaignRecipientsPage />}
                />
              </Routes>
            </WorkspaceContext.Provider>
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  it("displays sequence status labels and scheduled send times correctly", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(liveCampaign);
    vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(liveRecipients);

    renderPage(201, "ADMIN");

    await waitFor(() => {
      expect(screen.getAllByText("Step 2 scheduled").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Stopped manually").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Stopped — replied").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Sequence completed").length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("renders follow-up action buttons only for actionable recipients", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(liveCampaign);
    vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(liveRecipients);

    renderPage(201, "ADMIN");

    await waitFor(() => {
      // scheduled@test.com is actionable: has reschedule, skip, stop
      expect(
        screen.getAllByRole("button", {
          name: /Reschedule next step for scheduled@test.com/i,
        }).length
      ).toBeGreaterThan(0);
      expect(
        screen.getAllByRole("button", {
          name: /Skip next step for scheduled@test.com/i,
        }).length
      ).toBeGreaterThan(0);
      expect(
        screen.getAllByRole("button", {
          name: /Stop follow-ups for scheduled@test.com/i,
        }).length
      ).toBeGreaterThan(0);

      // stopped, replied, completed recipients do NOT have action buttons
      expect(
        screen.queryByRole("button", {
          name: /Stop follow-ups for stopped@test.com/i,
        })
      ).toBeNull();
      expect(
        screen.queryByRole("button", {
          name: /Stop follow-ups for replied@test.com/i,
        })
      ).toBeNull();
      expect(
        screen.queryByRole("button", {
          name: /Stop follow-ups for completed@test.com/i,
        })
      ).toBeNull();
    });
  });

  it("opens stop modal and confirms stopping follow-ups", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(liveCampaign);
    vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(liveRecipients);
    const stopSpy = vi.spyOn(campaignsApi, "stopRecipient").mockResolvedValue({
      ...liveRecipients[0],
      status: "STOPPED",
      stopped_reason: "MANUAL",
      next_step_due_at: null,
    });

    renderPage(201, "ADMIN");

    await waitFor(() => {
      expect(
        screen.getAllByRole("button", {
          name: /Stop follow-ups for scheduled@test.com/i,
        })[0]
      ).toBeDefined();
    });

    fireEvent.click(
      screen.getAllByRole("button", {
        name: /Stop follow-ups for scheduled@test.com/i,
      })[0]
    );

    await waitFor(() => {
      expect(screen.getByText("Stop Follow-Ups?")).toBeDefined();
      expect(screen.getByRole("button", { name: "Stop Follow-Ups" })).toBeDefined();
    });

    fireEvent.click(screen.getByRole("button", { name: "Stop Follow-Ups" }));

    await waitFor(() => {
      expect(stopSpy).toHaveBeenCalledWith(10, 201, 1);
      expect(screen.getByText(/Stopped follow-ups for scheduled@test.com/i)).toBeDefined();
    });
  });

  it("opens skip modal and confirms advancing to subsequent step", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(liveCampaign);
    vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(liveRecipients);
    const skipSpy = vi.spyOn(campaignsApi, "skipRecipientNextStep").mockResolvedValue({
      ...liveRecipients[0],
      current_step_number: 2,
      status: "SENT",
    });

    renderPage(201, "ADMIN");

    await waitFor(() => {
      expect(
        screen.getAllByRole("button", {
          name: /Skip next step for scheduled@test.com/i,
        })[0]
      ).toBeDefined();
    });

    fireEvent.click(
      screen.getAllByRole("button", {
        name: /Skip next step for scheduled@test.com/i,
      })[0]
    );

    await waitFor(() => {
      expect(screen.getByText("Skip Step 2?")).toBeDefined();
      expect(screen.getByRole("button", { name: "Skip Step 2" })).toBeDefined();
    });

    fireEvent.click(screen.getByRole("button", { name: "Skip Step 2" }));

    await waitFor(() => {
      expect(skipSpy).toHaveBeenCalledWith(10, 201, 1);
      expect(screen.getByText(/Advanced scheduled@test.com to Step 2/i)).toBeDefined();
    });
  });

  it("opens reschedule modal and validates future date before submit", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(liveCampaign);
    vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(liveRecipients);
    const reschedSpy = vi.spyOn(campaignsApi, "rescheduleRecipient").mockResolvedValue({
      ...liveRecipients[0],
      next_step_due_at: "2030-11-01T10:00:00.000Z",
    });

    renderPage(201, "ADMIN");

    await waitFor(() => {
      expect(
        screen.getAllByRole("button", {
          name: /Reschedule next step for scheduled@test.com/i,
        })[0]
      ).toBeDefined();
    });

    fireEvent.click(
      screen.getAllByRole("button", {
        name: /Reschedule next step for scheduled@test.com/i,
      })[0]
    );

    await waitFor(() => {
      expect(screen.getByText("Reschedule Step 2")).toBeDefined();
    });

    const datetimeInput = screen.getByLabelText(/New Send Date & Time/i);
    const confirmBtn = screen.getByRole("button", { name: "Confirm Reschedule" });

    // Past date fails validation
    fireEvent.change(datetimeInput, { target: { value: "2020-01-01T10:00" } });
    fireEvent.click(confirmBtn);

    expect(screen.getByText("Rescheduled time must be in the future.")).toBeDefined();
    expect(reschedSpy).not.toHaveBeenCalled();

    // Valid future date succeeds
    fireEvent.change(datetimeInput, { target: { value: "2030-11-01T10:00" } });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(reschedSpy).toHaveBeenCalledWith(10, 201, 1, {
        next_step_due_at: expect.stringMatching(/^2030-11-01/),
      });
      expect(
        screen.getByText(/Rescheduled next follow-up for scheduled@test.com/i)
      ).toBeDefined();
    });
  });

  it("hides operational controls when user has MEMBER role", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(liveCampaign);
    vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(liveRecipients);

    renderPage(201, "MEMBER");

    await waitFor(() => {
      expect(screen.getAllByText("scheduled@test.com").length).toBeGreaterThan(0);
    });

    // Member cannot see reschedule, skip, or stop buttons
    expect(
      screen.queryByRole("button", {
        name: /Reschedule next step for scheduled@test.com/i,
      })
    ).toBeNull();
    expect(
      screen.queryByRole("button", {
        name: /Skip next step for scheduled@test.com/i,
      })
    ).toBeNull();
    expect(
      screen.queryByRole("button", {
        name: /Stop follow-ups for scheduled@test.com/i,
      })
    ).toBeNull();
  });
});
