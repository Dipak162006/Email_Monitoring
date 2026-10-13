import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import type { CampaignDetail } from "../../../types/campaign";
import type { AuthorizedEmailAccount } from "../../../types/emails";
import type { CompanyWithRole } from "../../../types/auth";
import { campaignsApi, RequestError } from "../../../services/api";
import { WorkspaceContext, type WorkspaceContextType } from "../../../context/WorkspaceContext";
import { CampaignDetailPage } from "../../../pages/CampaignDetailPage";
import { CreateCampaignPage } from "../../../pages/CreateCampaignPage";
import { CampaignTableRow } from "../CampaignTableRow";
import { CampaignMobileCard } from "../CampaignMobileCard";

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

const mockDraftCampaign: CampaignDetail = {
  id: 42,
  company_id: 10,
  email_account_id: 5,
  name: "Q4 Customer Outreach",
  subject: "Exclusive Q4 Offer",
  body_text: "Hi {{first_name}},\nCheck out our new launch.\nBest,\nTeam",
  body_html: "<p>Hi <b>{{first_name}}</b>,</p><p>Check out our new launch.</p>",
  status: "DRAFT",
  scheduled_at: null,
  started_at: null,
  completed_at: null,
  recipient_count: 350,
  email_account_name: "Sales Primary",
  email_account_address: "sales@acme.corp",
  created_at: "2026-10-08T10:00:00Z",
  updated_at: "2026-10-08T11:00:00Z",
};

const mockRunningCampaign: CampaignDetail = {
  ...mockDraftCampaign,
  id: 43,
  status: "RUNNING",
  started_at: "2026-10-08T12:00:00Z",
};

const mockAccounts: AuthorizedEmailAccount[] = [
  {
    id: 5,
    company_id: 10,
    name: "Sales Primary",
    email_address: "sales@acme.corp",
    provider: "SMTP_IMAP",
    is_active: true,
    is_sync_enabled: true,
  },
];

describe("Campaign Detail & Navigation (C12.3 Integration)", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.restoreAllMocks();
  });

  const renderDetailPage = (campaignId: number, company: CompanyWithRole = mockAdminCompany) => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/campaigns/${campaignId}`]}>
          <WorkspaceContext.Provider value={createMockWorkspace(company)}>
            <Routes>
              <Route path="/campaigns/:campaignId" element={<CampaignDetailPage />} />
              <Route path="/campaigns/:campaignId/recipients" element={<div>Recipients View</div>} />
              <Route path="/campaigns/:campaignId/edit" element={<div>Edit Draft View</div>} />
              <Route path="/campaigns" element={<div>Campaigns List View</div>} />
            </Routes>
          </WorkspaceContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("1. CampaignDetailPage Rendering & State Handling", () => {
    it("renders real campaign details, status badge, and Manage Recipients action", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);

      renderDetailPage(42);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      // Verify status badge
      expect(screen.getByText("DRAFT")).toBeDefined();

      // Verify sender details
      expect(screen.getAllByText("Sales Primary").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("sales@acme.corp").length).toBeGreaterThanOrEqual(1);

      // Verify recipient count
      expect(screen.getByText("350 recipients")).toBeDefined();

      // Verify subject
      expect(screen.getAllByText("Exclusive Q4 Offer").length).toBeGreaterThanOrEqual(1);

      // Verify Manage Recipients button
      const manageRecipientsBtn = screen.getByRole("link", { name: /manage recipients/i });
      expect(manageRecipientsBtn).toBeDefined();
      expect(manageRecipientsBtn.getAttribute("href")).toBe("/campaigns/42/recipients");

      // Verify Edit Draft button for DRAFT & ADMIN
      const editDraftBtn = screen.getByRole("link", { name: /edit draft/i });
      expect(editDraftBtn).toBeDefined();
      expect(editDraftBtn.getAttribute("href")).toBe("/campaigns/42/edit");
    });

    it("copies subject line to clipboard when clicking copy icon", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      const writeTextMock = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, {
        clipboard: { writeText: writeTextMock },
      });

      renderDetailPage(42);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      const copyBtn = screen.getByTitle("Copy Subject Line");
      fireEvent.click(copyBtn);

      expect(writeTextMock).toHaveBeenCalledWith("Exclusive Q4 Offer");
      await waitFor(() => {
        expect(screen.getByText("Copied!")).toBeDefined();
      });
    });

    it("toggles between formatted preview, HTML source, and plaintext fallback views", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);

      renderDetailPage(42);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      // Initially on formatted preview: contains sanitized HTML text
      expect(screen.getByText(/Check out our new launch/i)).toBeDefined();

      // Switch to HTML source
      const htmlBtn = screen.getByRole("button", { name: /html source/i });
      fireEvent.click(htmlBtn);
      expect(screen.getByText(/template_source.html/i)).toBeDefined();
      expect(screen.getByText(/<p>Hi <b>\{\{first_name\}\}<\/b>/i)).toBeDefined();

      // Switch to Plaintext fallback
      const plaintextBtn = screen.getByRole("button", { name: /plaintext fallback/i });
      fireEvent.click(plaintextBtn);
      expect(screen.getByText(/plaintext_fallback.txt/i)).toBeDefined();
      expect(screen.getByText(/Check out our new launch/i)).toBeDefined();
    });

    it("toggles between desktop and mobile viewport widths for the preview frame", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);

      renderDetailPage(42);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      const mobileBtn = screen.getByTitle("Mobile Viewport");
      fireEvent.click(mobileBtn);

      // Mobile frame width applied
      const desktopBtn = screen.getByTitle("Desktop Viewport");
      expect(desktopBtn).toBeDefined();
      fireEvent.click(desktopBtn);
    });

    it("displays not-found state when campaign does not exist (404)", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockRejectedValue(
        new RequestError(404, "Campaign not found", "NOT_FOUND")
      );

      renderDetailPage(999);

      await waitFor(() => {
        expect(screen.getByText("Campaign Not Found")).toBeDefined();
      });

      expect(screen.getByText(/Campaign #999 does not exist/i)).toBeDefined();
      const backLink = screen.getByRole("link", { name: /back to campaigns/i });
      expect(backLink.getAttribute("href")).toBe("/campaigns");
    });

    it("displays recoverable error state with Retry on network failure", async () => {
      const getSpy = vi
        .spyOn(campaignsApi, "getCampaign")
        .mockRejectedValueOnce(new Error("Network failed"))
        .mockResolvedValueOnce(mockDraftCampaign);

      renderDetailPage(42);

      await waitFor(() => {
        expect(screen.getByText("Unable to load campaign details")).toBeDefined();
      });

      const retryBtn = screen.getByRole("button", { name: /retry/i });
      fireEvent.click(retryBtn);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });
      expect(getSpy).toHaveBeenCalledTimes(2);
    });

    it("hides Edit Draft for non-DRAFT campaigns (RUNNING)", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockRunningCampaign);

      renderDetailPage(43);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      expect(screen.getAllByText("RUNNING").length).toBeGreaterThanOrEqual(1);
      expect(screen.queryByRole("link", { name: /edit draft/i })).toBeNull();
      // Pause and Cancel actions are present for RUNNING
      expect(screen.getByRole("button", { name: /pause/i })).toBeDefined();
      expect(screen.getByRole("button", { name: /cancel/i })).toBeDefined();
    });

    it("hides Edit Draft for MEMBER role even on DRAFT campaigns", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);

      renderDetailPage(42, mockMemberCompany);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      // Member can see details and Manage Recipients (read-only)
      expect(screen.getByRole("link", { name: /manage recipients/i })).toBeDefined();
      // But no Edit Draft or Delete Draft buttons
      expect(screen.queryByRole("link", { name: /edit draft/i })).toBeNull();
      expect(screen.queryByRole("button", { name: /delete/i })).toBeNull();
    });

    it("displays configured sending interval and next recipient ETA in schedule card", async () => {
      const pacedCampaign: CampaignDetail = {
        ...mockDraftCampaign,
        send_interval_seconds: 300,
        status: "RUNNING",
        next_send_at: "2026-10-15T10:05:00Z",
      };
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(pacedCampaign);

      renderDetailPage(42);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      expect(screen.getByText("5 minutes")).toBeDefined();
      expect(screen.getByText(/Next Recipient/i)).toBeDefined();
    });
  });

  describe("2. CreateCampaignPage in Edit Mode (/campaigns/:campaignId/edit)", () => {
    it("fetches and pre-populates existing draft data and updates via PATCH", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      const updateSpy = vi.spyOn(campaignsApi, "updateCampaign").mockResolvedValue({
        ...mockDraftCampaign,
        name: "Q4 Outreach Updated",
      });
      const saveSpy = vi.spyOn(campaignsApi, "createCampaign");

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/42/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/edit"
                  element={<CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />}
                />
                <Route path="/campaigns/:campaignId/recipients" element={<div>Recipients Step View</div>} />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Prepopulated title & fields
      await waitFor(() => {
        expect(screen.getByText("Edit Campaign Draft")).toBeDefined();
      });

      expect(screen.getByDisplayValue("Q4 Customer Outreach")).toBeDefined();
      expect(screen.getByDisplayValue("Exclusive Q4 Offer")).toBeDefined();

      // Modify the name
      const nameInput = screen.getByDisplayValue("Q4 Customer Outreach");
      fireEvent.change(nameInput, { target: { value: "Q4 Customer Outreach Modified" } });

      // Click Save Draft
      const saveBtn = screen.getByRole("button", { name: /save draft/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          10,
          42,
          expect.objectContaining({
            name: "Q4 Customer Outreach Modified",
            email_account_id: 5,
            subject: "Exclusive Q4 Offer",
          })
        );
      });

      // Crucial: createCampaign must NOT have been called
      expect(saveSpy).not.toHaveBeenCalled();
    });

    it("pre-populates existing custom sending interval and preserves it in update payload", async () => {
      const pacedDraft: CampaignDetail = {
        ...mockDraftCampaign,
        send_interval_seconds: 300,
      };
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(pacedDraft);
      const updateSpy = vi.spyOn(campaignsApi, "updateCampaign").mockResolvedValue({
        ...pacedDraft,
        subject: "Updated Subject",
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/42/edit"]}>
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

      // Verify custom pacing radio is checked and interval shows 5 Minutes
      const radioCustom = screen.getByRole("radio", { name: /paced sending delay/i });
      expect((radioCustom as HTMLInputElement).checked).toBe(true);
      expect(screen.getByDisplayValue("5")).toBeDefined();
      expect(screen.getByDisplayValue("Minutes")).toBeDefined();

      // Modify subject only and save
      const subjectInput = screen.getByDisplayValue("Exclusive Q4 Offer");
      fireEvent.change(subjectInput, { target: { value: "Updated Subject" } });

      const saveBtn = screen.getByRole("button", { name: /save draft/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          10,
          42,
          expect.objectContaining({
            subject: "Updated Subject",
            send_interval_seconds: 300,
          })
        );
      });
    });

    it("blocks editing non-DRAFT campaigns with clear notice and detail link", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockRunningCampaign);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/43/edit"]}>
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
      expect(screen.getByRole("button", { name: /view campaign details/i })).toBeDefined();
    });

    it("blocks MEMBER role from accessing edit mode with permission notice", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/42/edit"]}>
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
      expect(
        screen.getByText(/Only company owners and administrators are authorized/i)
      ).toBeDefined();
    });
  });

  describe("3. Table Row & Card Click Target Isolation", () => {
    it("clicking non-navigation row areas does not navigate, while clicking campaign name does", () => {
      const handleView = vi.fn();
      const handleEdit = vi.fn();

      render(
        <table>
          <tbody>
            <CampaignTableRow
              campaign={mockDraftCampaign}
              senderAccount={mockAccounts[0]}
              onView={handleView}
              onEdit={handleEdit}
            />
          </tbody>
        </table>
      );

      // 1. Clicking status badge cell does NOT trigger onView
      const statusBadge = screen.getByText("DRAFT");
      fireEvent.click(statusBadge);
      expect(handleView).not.toHaveBeenCalled();

      // 2. Clicking sender cell does NOT trigger onView
      const senderText = screen.getByText("sales@acme.corp");
      fireEvent.click(senderText);
      expect(handleView).not.toHaveBeenCalled();

      // 3. Clicking recipient count does NOT trigger onView
      const recipientCount = screen.getByText(/350 recipients/i);
      fireEvent.click(recipientCount);
      expect(handleView).not.toHaveBeenCalled();

      // 4. Clicking campaign name button explicitly DOES trigger onView
      const campaignBtn = screen.getByRole("button", { name: "Q4 Customer Outreach" });
      fireEvent.click(campaignBtn);
      expect(handleView).toHaveBeenCalledTimes(1);

      // 5. Clicking contextual Edit draft action button triggers onEdit without calling onView
      const editBtn = screen.getByRole("button", { name: /edit draft/i });
      fireEvent.click(editBtn);
      expect(handleEdit).toHaveBeenCalledTimes(1);
      expect(handleView).toHaveBeenCalledTimes(1);
    });

    it("clicking mobile card surface areas does not navigate, while clicking campaign name does", () => {
      const handleView = vi.fn();
      const handleToggle = vi.fn();

      render(
        <CampaignMobileCard
          campaign={mockDraftCampaign}
          senderAccount={mockAccounts[0]}
          isMenuOpen={false}
          onToggleMenu={handleToggle}
          onCloseMenu={vi.fn()}
          onView={handleView}
        />
      );

      // 1. Clicking status badge on card does NOT trigger onView
      const statusBadge = screen.getByText("DRAFT");
      fireEvent.click(statusBadge);
      expect(handleView).not.toHaveBeenCalled();

      // 2. Clicking recipient count does NOT trigger onView
      const recipientCount = screen.getByText(/350 recipients/i);
      fireEvent.click(recipientCount);
      expect(handleView).not.toHaveBeenCalled();

      // 3. Clicking the campaign name button explicitly DOES trigger onView
      const campaignBtn = screen.getByRole("button", { name: "Q4 Customer Outreach" });
      fireEvent.click(campaignBtn);
      expect(handleView).toHaveBeenCalledTimes(1);
    });
  });

  describe("4. Preflight, Scheduling & Launch Flow", () => {
    it("runs preflight validation on Launch Now and blocks dispatch if blocking issues exist", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      vi.spyOn(campaignsApi, "preflightCampaign").mockResolvedValue({
        eligible: false,
        campaign_id: 42,
        recipient_count: 0,
        eligible_recipient_count: 0,
        suppressed_recipient_count: 0,
        issues: [
          {
            code: "NO_RECIPIENTS",
            message: "Campaign has no recipients configured.",
            severity: "BLOCKING",
            blocking: true,
          },
        ],
      });
      const dispatchSpy = vi.spyOn(campaignsApi, "dispatchCampaign");

      renderDetailPage(42);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      // Click Launch Now button
      const launchNowBtns = screen.getAllByRole("button", { name: /launch now/i });
      fireEvent.click(launchNowBtns[0]);

      // Preflight modal opens and displays blocked status
      await waitFor(() => {
        expect(screen.getByText("Preflight Validation Blocked")).toBeDefined();
      });
      expect(screen.getByText("Campaign has no recipients configured.")).toBeDefined();

      // Confirm button is disabled
      const confirmBtn = screen.getByRole("button", { name: /confirm & launch now/i });
      expect(confirmBtn.hasAttribute("disabled")).toBe(true);
      expect(dispatchSpy).not.toHaveBeenCalled();
    });

    it("allows immediate dispatch via dispatchCampaign when preflight is eligible", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      vi.spyOn(campaignsApi, "preflightCampaign").mockResolvedValue({
        eligible: true,
        campaign_id: 42,
        recipient_count: 350,
        eligible_recipient_count: 350,
        suppressed_recipient_count: 0,
        issues: [],
      });
      const dispatchSpy = vi.spyOn(campaignsApi, "dispatchCampaign").mockResolvedValue({
        campaign_id: 42,
        company_id: 10,
        status: "QUEUED",
        task_id: "celery-task-123",
        dispatched_at: "2026-10-09T10:00:00Z",
        eligible_recipient_count: 350,
        total_recipient_count: 350,
      });

      renderDetailPage(42);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      const launchNowBtns = screen.getAllByRole("button", { name: /launch now/i });
      fireEvent.click(launchNowBtns[0]);

      await waitFor(() => {
        expect(screen.getByText("Preflight Validation Passed")).toBeDefined();
      });

      const confirmBtn = screen.getByRole("button", { name: /confirm & launch now/i });
      expect(confirmBtn.hasAttribute("disabled")).toBe(false);
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(dispatchSpy).toHaveBeenCalledWith(10, 42);
      });
    });

    it("schedules campaign with future datetime via scheduleCampaign when preflight is eligible", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      vi.spyOn(campaignsApi, "preflightCampaign").mockResolvedValue({
        eligible: true,
        campaign_id: 42,
        recipient_count: 350,
        eligible_recipient_count: 350,
        suppressed_recipient_count: 0,
        issues: [],
      });
      const scheduleSpy = vi.spyOn(campaignsApi, "scheduleCampaign").mockResolvedValue({
        ...mockDraftCampaign,
        status: "SCHEDULED",
        scheduled_at: "2026-10-15T09:00:00Z",
      });

      renderDetailPage(42);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      const scheduleBtns = screen.getAllByRole("button", { name: /schedule/i });
      fireEvent.click(scheduleBtns[0]);

      await waitFor(() => {
        expect(screen.getByText("Preflight Validation Passed")).toBeDefined();
      });

      const confirmBtn = screen.getByRole("button", { name: /confirm & schedule/i });
      expect(confirmBtn.hasAttribute("disabled")).toBe(false);
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(scheduleSpy).toHaveBeenCalledWith(10, 42, expect.objectContaining({
          scheduled_at: expect.any(String),
        }));
      });
    });

    it("allows rescheduling an already SCHEDULED campaign to a new datetime", async () => {
      const mockScheduledCampaign: CampaignDetail = {
        ...mockDraftCampaign,
        id: 44,
        status: "SCHEDULED",
        scheduled_at: "2026-10-20T14:00:00Z",
      };
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockScheduledCampaign);
      vi.spyOn(campaignsApi, "preflightCampaign").mockResolvedValue({
        eligible: true,
        campaign_id: 44,
        recipient_count: 350,
        eligible_recipient_count: 350,
        suppressed_recipient_count: 0,
        issues: [],
      });
      const scheduleSpy = vi.spyOn(campaignsApi, "scheduleCampaign").mockResolvedValue({
        ...mockScheduledCampaign,
        scheduled_at: "2026-10-25T10:00:00Z",
      });

      renderDetailPage(44);

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Q4 Customer Outreach" })).toBeDefined();
      });

      // Status badge is SCHEDULED
      expect(screen.getByText("SCHEDULED")).toBeDefined();

      // "Reschedule" buttons are rendered (in header and schedule card)
      const rescheduleBtns = screen.getAllByRole("button", { name: /reschedule/i });
      expect(rescheduleBtns.length).toBeGreaterThanOrEqual(1);
      fireEvent.click(rescheduleBtns[0]);

      // Preflight modal opens
      await waitFor(() => {
        expect(screen.getByText("Preflight Validation Passed")).toBeDefined();
      });

      // Confirm button displays "Confirm & Reschedule"
      const confirmBtn = screen.getByRole("button", { name: /confirm & reschedule/i });
      expect(confirmBtn.hasAttribute("disabled")).toBe(false);
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(scheduleSpy).toHaveBeenCalledWith(10, 44, expect.objectContaining({
          scheduled_at: expect.any(String),
        }));
      });
    });
  });

  describe("5. Wizard Bottom Back Button Navigation", () => {
    it("navigates back to previous step without clearing entered values", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/42/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route path="/campaigns/:campaignId/edit" element={<CreateCampaignPage initialAccounts={mockAccounts} />} />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByDisplayValue("Q4 Customer Outreach")).toBeDefined();
      });

      // Step 1 -> Step 2
      const continueBtn = screen.getByRole("button", { name: /continue/i });
      fireEvent.click(continueBtn);

      await waitFor(() => {
        expect(screen.getByText(/Select which authenticated mailbox/i)).toBeDefined();
      });

      // Click Back button on step 2
      const backBtn = screen.getByRole("button", { name: /^back$/i });
      fireEvent.click(backBtn);

      // Returns to Step 1 and preserves values
      await waitFor(() => {
        expect(screen.getByDisplayValue("Q4 Customer Outreach")).toBeDefined();
        expect(screen.getByDisplayValue("Exclusive Q4 Offer")).toBeDefined();
      });
    });
  });

  describe("6. Wizard 'Continue to recipients' Navigation (C11.3)", () => {
    it("navigates to /campaigns/{campaignId}/recipients after creating a new campaign", async () => {
      const mockCreatedCampaign: CampaignDetail = {
        ...mockDraftCampaign,
        id: 88,
        name: "Product Launch — October",
      };
      const createSpy = vi.spyOn(campaignsApi, "createCampaign").mockResolvedValue(mockCreatedCampaign);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/new"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route path="/campaigns/new" element={<CreateCampaignPage initialAccounts={mockAccounts} />} />
                <Route path="/campaigns/:campaignId/recipients" element={<div data-testid="recipients-page">Recipients Management Page</div>} />
                <Route path="/campaigns" element={<div data-testid="campaigns-list">Campaigns List</div>} />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Step 1 -> Step 2
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. product launch/i), { target: { value: "Product Launch — October" } });
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. introducing our new product/i), { target: { value: "Introducing our new product line" } });
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => {
        expect(screen.getByText(/Select which authenticated mailbox/i)).toBeDefined();
      });

      // Step 2 -> Step 3
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => {
        expect(screen.getByRole("heading", { name: /Email Content/i })).toBeDefined();
      });
      const editor1 = document.querySelector(".compose-editor") as HTMLElement;
      if (editor1) {
        editor1.innerHTML = "<p>Product Launch content</p>";
        fireEvent.input(editor1);
      }

      // Step 3 -> Step 4
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => {
        expect(screen.getByRole("heading", { name: /Review Campaign/i })).toBeDefined();
      });

      // Click "Continue to Recipients"
      fireEvent.click(screen.getByRole("button", { name: /continue to recipients/i }));

      // Navigates to /campaigns/88/recipients using the created campaign ID
      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(10, expect.objectContaining({
          name: "Product Launch — October",
        }));
        expect(screen.getByTestId("recipients-page")).toBeDefined();
      });
      expect(screen.queryByTestId("campaigns-list")).toBeNull();
    });

    it("navigates to /campaigns/{campaignId}/recipients when editing an existing draft", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      const updateSpy = vi.spyOn(campaignsApi, "updateCampaign").mockResolvedValue({
        ...mockDraftCampaign,
        name: "Q4 Customer Outreach Updated",
      });

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/42/edit"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route path="/campaigns/:campaignId/edit" element={<CreateCampaignPage initialAccounts={mockAccounts} />} />
                <Route path="/campaigns/:campaignId/recipients" element={<div data-testid="recipients-page">Recipients Management Page</div>} />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByDisplayValue("Q4 Customer Outreach")).toBeDefined();
      });

      // Step 1 -> Step 2
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => {
        expect(screen.getByText(/Select which authenticated mailbox/i)).toBeDefined();
      });

      // Step 2 -> Step 3
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => {
        expect(screen.getByRole("heading", { name: /Email Content/i })).toBeDefined();
      });

      // Step 3 -> Step 4
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => {
        expect(screen.getByRole("heading", { name: /Review Campaign/i })).toBeDefined();
      });

      // Click "Continue to Recipients"
      fireEvent.click(screen.getByRole("button", { name: /continue to recipients/i }));

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(10, 42, expect.objectContaining({
          name: "Q4 Customer Outreach",
        }));
        expect(screen.getByTestId("recipients-page")).toBeDefined();
      });
    });

    it("does not navigate if saving the campaign fails", async () => {
      const createSpy = vi.spyOn(campaignsApi, "createCampaign").mockRejectedValue(
        new RequestError(500, "Network timeout", "Network timeout")
      );

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/new"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route path="/campaigns/new" element={<CreateCampaignPage initialAccounts={mockAccounts} />} />
                <Route path="/campaigns/:campaignId/recipients" element={<div data-testid="recipients-page">Recipients Management Page</div>} />
                <Route path="/campaigns" element={<div data-testid="campaigns-list">Campaigns List</div>} />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Step 1 -> Step 2 -> Step 3 -> Step 4
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. product launch/i), { target: { value: "Product Launch — October" } });
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. introducing our new product/i), { target: { value: "Introducing our new product line" } });
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => expect(screen.getByText(/Select which authenticated mailbox/i)).toBeDefined());
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => expect(screen.getByRole("heading", { name: /Email Content/i })).toBeDefined());
      const editor2 = document.querySelector(".compose-editor") as HTMLElement;
      if (editor2) {
        editor2.innerHTML = "<p>Product Launch content</p>";
        fireEvent.input(editor2);
      }
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => expect(screen.getByRole("heading", { name: /Review Campaign/i })).toBeDefined());

      // Click "Continue to Recipients"
      fireEvent.click(screen.getByRole("button", { name: /continue to recipients/i }));

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalled();
        expect(screen.getByText("Network timeout")).toBeDefined();
      });
      expect(screen.queryByTestId("recipients-page")).toBeNull();
      expect(screen.queryByTestId("campaigns-list")).toBeNull();
    });

    it("does not trigger duplicate campaign creation on repeated clicks while save is in progress", async () => {
      let resolvePromise: (value: CampaignDetail) => void;
      const deferred = new Promise<CampaignDetail>((resolve) => {
        resolvePromise = resolve;
      });
      const createSpy = vi.spyOn(campaignsApi, "createCampaign").mockReturnValue(deferred);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={["/campaigns/new"]}>
            <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
              <Routes>
                <Route path="/campaigns/new" element={<CreateCampaignPage initialAccounts={mockAccounts} />} />
                <Route path="/campaigns/:campaignId/recipients" element={<div data-testid="recipients-page">Recipients Management Page</div>} />
              </Routes>
            </WorkspaceContext.Provider>
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Step 1 -> Step 2 -> Step 3 -> Step 4
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. product launch/i), { target: { value: "Product Launch — October" } });
      fireEvent.change(screen.getByPlaceholderText(/e\.g\. introducing our new product/i), { target: { value: "Introducing our new product line" } });
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => expect(screen.getByText(/Select which authenticated mailbox/i)).toBeDefined());
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => expect(screen.getByRole("heading", { name: /Email Content/i })).toBeDefined());
      const editor3 = document.querySelector(".compose-editor") as HTMLElement;
      if (editor3) {
        editor3.innerHTML = "<p>Product Launch content</p>";
        fireEvent.input(editor3);
      }
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => expect(screen.getByRole("heading", { name: /Review Campaign/i })).toBeDefined());

      const continueBtn = screen.getByRole("button", { name: /continue to recipients/i });
      fireEvent.click(continueBtn);
      // Repeated rapid clicks while save in progress
      fireEvent.click(continueBtn);
      fireEvent.click(continueBtn);

      expect(createSpy).toHaveBeenCalledTimes(1);

      // Resolve the save
      resolvePromise!({
        ...mockDraftCampaign,
        id: 77,
      });

      await waitFor(() => {
        expect(screen.getByTestId("recipients-page")).toBeDefined();
      });
    });
  });
});
