import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import type { Campaign, CampaignDetail, CampaignStepItem } from "../../../types/campaign";
import type { AuthorizedEmailAccount } from "../../../types/emails";
import type { CompanyWithRole } from "../../../types/auth";
import { campaignsApi, RequestError } from "../../../services/api";
import { WorkspaceContext, type WorkspaceContextType } from "../../../context/WorkspaceContext";
import { CreateCampaignPage } from "../../../pages/CreateCampaignPage";
import { CampaignTableRow } from "../CampaignTableRow";

// Mock document.execCommand for rich-text actions
document.execCommand = vi.fn();

const mockAdminCompany: CompanyWithRole = {
  id: 10,
  name: "Acme Corp",
  role: "ADMIN",
  is_active: true,
  created_at: "2026-10-08T00:00:00Z",
};

const mockMemberCompany: CompanyWithRole = {
  id: 10,
  name: "Acme Corp",
  role: "MEMBER",
  is_active: true,
  created_at: "2026-10-08T00:00:00Z",
};

const createMockWorkspace = (company: CompanyWithRole = mockAdminCompany): WorkspaceContextType => ({
  currentCompany: company,
  currentCompanyId: company.id,
  currentRole: company.role,
  companies: [company],
  memberships: [company],
  isLoading: false,
  isError: false,
  error: null,
  setActiveCompanyId: vi.fn(),
  refreshWorkspaces: vi.fn().mockResolvedValue(undefined),
  refetch: vi.fn().mockResolvedValue(undefined),
});

const mockAccounts: AuthorizedEmailAccount[] = [
  {
    id: 5,
    company_id: 10,
    name: "Outreach Lead",
    email_address: "outreach@acme.corp",
    provider: "SMTP_IMAP",
    is_active: true,
    is_sync_enabled: true,
  },
  {
    id: 6,
    company_id: 10,
    name: "Secondary Sender",
    email_address: "secondary@acme.corp",
    provider: "SMTP_IMAP",
    is_active: true,
    is_sync_enabled: true,
  },
];

const mockFollowupSteps: CampaignStepItem[] = [
  {
    id: 101,
    campaign_id: 50,
    step_number: 2,
    delay_hours: 48,
    subject: "Quick bump on proposal",
    body_html: "<p>Following up on my previous note.</p>",
    body_text: "Following up on my previous note.",
    is_active: true,
    created_at: "2026-10-20T10:00:00Z",
    updated_at: "2026-10-20T10:00:00Z",
  },
  {
    id: 102,
    campaign_id: 50,
    step_number: 3,
    delay_hours: 96,
    subject: "Final check-in",
    body_html: "<p>Closing the loop on this.</p>",
    body_text: "Closing the loop on this.",
    is_active: true,
    created_at: "2026-10-20T10:00:00Z",
    updated_at: "2026-10-20T10:00:00Z",
  },
];

const mockExistingDraftCampaign: CampaignDetail = {
  id: 50,
  company_id: 10,
  email_account_id: 5,
  name: "Existing Draft Campaign",
  subject: "Initial Proposition",
  body_text: "Hello,\nWe would like to introduce our service.\nBest,\nOutreach",
  body_html: "<p>Hello,</p><p>We would like to introduce our service.</p>",
  status: "DRAFT",
  scheduled_at: null,
  started_at: null,
  completed_at: null,
  recipient_count: 120,
  send_interval_seconds: 120,
  email_account_name: "Outreach Lead",
  email_account_address: "outreach@acme.corp",
  steps: [
    {
      id: 100,
      campaign_id: 50,
      step_number: 1,
      delay_hours: 0,
      subject: "Initial Proposition",
      body_text: "Hello,\nWe would like to introduce our service.",
      body_html: "<p>Hello,</p><p>We would like to introduce our service.</p>",
      is_active: true,
      created_at: "2026-10-20T10:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
    },
    ...mockFollowupSteps,
  ],
  followup_steps: mockFollowupSteps,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T11:00:00Z",
};

describe("Milestone M2 — Post-Creation Campaign Editing Verification", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.restoreAllMocks();
    window.scrollTo = vi.fn();
  });

  describe("1. Action Availability & Status Enforcement", () => {
    it("surfaces Edit action for DRAFT campaigns in actions menu and table row", () => {
      const handleEdit = vi.fn();
      const handleView = vi.fn();

      // Render Table Row
      render(
        <table>
          <tbody>
            <CampaignTableRow
              campaign={mockExistingDraftCampaign}
              senderAccount={mockAccounts[0]}
              onView={handleView}
              onEdit={handleEdit}
            />
          </tbody>
        </table>
      );

      // Edit draft button is rendered for DRAFT
      const editDraftBtn = screen.getByRole("button", { name: /edit draft/i });
      expect(editDraftBtn).toBeDefined();
      fireEvent.click(editDraftBtn);
      expect(handleEdit).toHaveBeenCalledWith(mockExistingDraftCampaign);
    });

    it("hides Edit action for prohibited statuses (SCHEDULED, RUNNING, PAUSED, COMPLETED, CANCELLED, FAILED)", () => {
      const prohibitedStatuses: Campaign["status"][] = [
        "SCHEDULED",
        "RUNNING",
        "PAUSED",
        "COMPLETED",
        "CANCELLED",
        "FAILED",
      ];

      for (const status of prohibitedStatuses) {
        const campaign: Campaign = {
          ...mockExistingDraftCampaign,
          id: 99,
          status,
        };

        const { unmount } = render(
          <table>
            <tbody>
              <CampaignTableRow
                campaign={campaign}
                senderAccount={mockAccounts[0]}
                onView={vi.fn()}
                onEdit={vi.fn()}
              />
            </tbody>
          </table>
        );

        // Edit button must NOT be present
        expect(screen.queryByRole("button", { name: /edit draft/i })).toBeNull();
        unmount();
      }
    });

    it("blocks direct navigation to edit wizard for non-DRAFT campaigns", async () => {
      const runningCampaign: CampaignDetail = {
        ...mockExistingDraftCampaign,
        status: "RUNNING",
      };
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(runningCampaign);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/50/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/edit"
                  element={<CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />}
                />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Editing Not Permitted")).toBeDefined();
      });
      expect(screen.getByText(/Only campaigns in DRAFT status may be edited/i)).toBeDefined();
      expect(screen.getByText(/currently RUNNING/i)).toBeDefined();
    });

    it("blocks MEMBER role from accessing edit mode with permission notice", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockExistingDraftCampaign);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/50/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockMemberCompany)}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/edit"
                  element={<CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />}
                />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Permission Required")).toBeDefined();
      });
      expect(screen.getByText(/Only company owners and administrators are authorized/i)).toBeDefined();
    });
  });

  describe("2. Form Pre-Population, M1 Follow-Up Editing, and Safe Updating", () => {
    it("pre-populates all existing campaign fields, initial email, and follow-up steps", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockExistingDraftCampaign);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/50/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/edit"
                  element={<CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />}
                />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByDisplayValue("Existing Draft Campaign")).toBeDefined();
        expect(screen.getByDisplayValue("Initial Proposition")).toBeDefined();
      });

      // Pacing interval: 120 seconds = 2 Minutes
      await waitFor(() => {
        expect(screen.getByDisplayValue("2")).toBeDefined();
        expect(screen.getByDisplayValue("Minutes")).toBeDefined();
      });

      // Navigate to Step 2 (Sender)
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      expect(screen.getAllByText(/Step 2 of 4/i).length).toBeGreaterThan(0);

      // Navigate to Step 3 (Content & Follow-up sequences)
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      expect(screen.getAllByText(/Step 3 of 4/i).length).toBeGreaterThan(0);

      // Verify follow-up step headers and content in Master-Detail sequence editor
      expect(screen.getByText("Follow-Up Step #1 (Step 2)")).toBeDefined();
      expect(screen.getByText("Follow-Up Step #2 (Step 3)")).toBeDefined();
      fireEvent.click(screen.getByText("Follow-Up Step #1 (Step 2)"));
      expect(screen.getByText("Following up on my previous note.")).toBeDefined();
      fireEvent.click(screen.getByText("Follow-Up Step #2 (Step 3)"));
      expect(screen.getByText("Closing the loop on this.")).toBeDefined();
    });

    it("updates the existing campaign in-place without creating a duplicate or modifying campaign ID", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockExistingDraftCampaign);
      const updateSpy = vi.spyOn(campaignsApi, "updateCampaign").mockResolvedValue({
        ...mockExistingDraftCampaign,
        name: "Renamed Draft Campaign",
        subject: "Renamed Proposition",
      });
      const createSpy = vi.spyOn(campaignsApi, "createCampaign");

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/50/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/edit"
                  element={<CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />}
                />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByDisplayValue("Existing Draft Campaign")).toBeDefined();
      });

      // Edit name and subject
      const nameInput = screen.getByDisplayValue("Existing Draft Campaign");
      fireEvent.change(nameInput, { target: { value: "Renamed Draft Campaign" } });

      const subjectInput = screen.getByDisplayValue("Initial Proposition");
      fireEvent.change(subjectInput, { target: { value: "Renamed Proposition" } });

      // Save Draft / Save Changes
      const saveBtn = screen.getByRole("button", { name: /save draft/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledTimes(1);
      });

      // Verify update was dispatched with exact campaign ID 50
      expect(updateSpy).toHaveBeenCalledWith(
        10,
        50,
        expect.objectContaining({
          name: "Renamed Draft Campaign",
          subject: "Renamed Proposition",
          email_account_id: 5,
        })
      );

      // createCampaign was NOT invoked
      expect(createSpy).not.toHaveBeenCalled();

      // Toast feedback confirms changes saved
      await waitFor(() => {
        expect(screen.getByText("Campaign changes saved successfully.")).toBeDefined();
      });
    });

    it("preserves M1 follow-up editing, allows adding a new step, and sends updated followup_steps", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockExistingDraftCampaign);
      const updateSpy = vi.spyOn(campaignsApi, "updateCampaign").mockResolvedValue(mockExistingDraftCampaign);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/50/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/edit"
                  element={<CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />}
                />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Edit Campaign Draft")).toBeDefined();
      });

      // Navigate to Step 3
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      expect(screen.getAllByText(/Step 3 of 4/i).length).toBeGreaterThan(0);

      // Initially 2 follow-ups
      expect(screen.getByText("2/9")).toBeDefined();

      // Add 3rd follow-up step
      const addStepBtn = screen.getByRole("button", { name: /\+ add follow-up step/i });
      fireEvent.click(addStepBtn);

      expect(screen.getByText("3/9")).toBeDefined();
      expect(screen.getByText("Follow-Up Step #3 (Step 4)")).toBeDefined();

      // Save
      const saveBtn = screen.getByRole("button", { name: /save draft/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledTimes(1);
      });

      const payload = updateSpy.mock.calls[0][2];
      expect(payload.followup_steps).toBeDefined();
      expect(payload.followup_steps?.length).toBe(3);
      expect(payload.followup_steps?.[0].step_number).toBe(2);
      expect(payload.followup_steps?.[1].step_number).toBe(3);
      expect(payload.followup_steps?.[2].step_number).toBe(4);
    });

    it("displays error toast and retains entered state when updateCampaign API fails", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockExistingDraftCampaign);
      vi.spyOn(campaignsApi, "updateCampaign").mockRejectedValue(
        new RequestError(400, "Validation failure on server")
      );

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/50/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/edit"
                  element={<CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />}
                />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByDisplayValue("Existing Draft Campaign")).toBeDefined();
      });

      const nameInput = screen.getByDisplayValue("Existing Draft Campaign");
      fireEvent.change(nameInput, { target: { value: "New Title That Fails" } });

      const saveBtn = screen.getByRole("button", { name: /save draft/i });
      fireEvent.click(saveBtn);

      // Toast renders server error message
      await waitFor(() => {
        expect(screen.getByText("Validation failure on server")).toBeDefined();
      });

      // Entered value is retained without data loss
      expect(screen.getByDisplayValue("New Title That Fails")).toBeDefined();
    });

    it("preserves sending_window and follow-up target_tags through load and update cycle", async () => {
      const campaignWithWindowAndTags: CampaignDetail = {
        ...mockExistingDraftCampaign,
        sending_window: {
          enabled: true,
          timezone: "America/New_York",
          days: [1, 2, 3, 4, 5],
          start_time: "09:00",
          end_time: "17:00",
        },
        steps: [
          mockExistingDraftCampaign.steps![0],
          {
            ...mockFollowupSteps[0],
            target_tags: ["vip", "enterprise"],
          },
        ],
        followup_steps: [
          {
            ...mockFollowupSteps[0],
            target_tags: ["vip", "enterprise"],
          },
        ],
      };

      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(campaignWithWindowAndTags);
      const updateSpy = vi.spyOn(campaignsApi, "updateCampaign").mockResolvedValue(campaignWithWindowAndTags);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/50/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/edit"
                  element={<CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />}
                />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByDisplayValue("Existing Draft Campaign")).toBeDefined();
      });

      // Save draft without altering window or tags
      const saveBtn = screen.getByRole("button", { name: /save draft/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledTimes(1);
      });

      const payload = updateSpy.mock.calls[0][2];
      expect(payload.sending_window).toEqual({
        enabled: true,
        timezone: "America/New_York",
        days: [1, 2, 3, 4, 5],
        start_time: "09:00",
        end_time: "17:00",
      });
      expect(payload.followup_steps?.[0].target_tags).toEqual(["vip", "enterprise"]);
    });

    it("normalizes structured FastAPI validation errors into readable toast instead of [object Object]", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockExistingDraftCampaign);
      vi.spyOn(campaignsApi, "updateCampaign").mockRejectedValue(
        new RequestError(422, "Validation Error", [
          { loc: ["body", "sending_window"], msg: "Start time must be strictly earlier than end time." }
        ])
      );

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/50/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/edit"
                  element={<CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />}
                />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByDisplayValue("Existing Draft Campaign")).toBeDefined();
      });

      const saveBtn = screen.getByRole("button", { name: /save draft/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(screen.getByText("Start time must be strictly earlier than end time.")).toBeDefined();
      });
      expect(screen.queryByText(/\[object Object\]/)).toBeNull();
    });
  });
});
