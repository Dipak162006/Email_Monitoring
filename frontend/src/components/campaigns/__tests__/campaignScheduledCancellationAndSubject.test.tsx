import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import type { CampaignDetail } from "../../../types/campaign";
import type { AuthorizedEmailAccount } from "../../../types/emails";
import type { CompanyWithRole } from "../../../types/auth";
import { campaignsApi } from "../../../services/api";
import { WorkspaceContext, type WorkspaceContextType } from "../../../context/WorkspaceContext";
import { CampaignDetailPage } from "../../../pages/CampaignDetailPage";
import { CreateCampaignPage } from "../../../pages/CreateCampaignPage";
import { CampaignTableRow } from "../CampaignTableRow";
import { CampaignActionsMenu } from "../CampaignActionsMenu";

const mockAdminCompany: CompanyWithRole = {
  id: 10,
  name: "Acme Corp",
  role: "ADMIN",
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

const mockSenderAccount: AuthorizedEmailAccount = {
  id: 5,
  company_id: 10,
  email_address: "outreach@acme.corp",
  name: "Outreach Team",
  provider: "SMTP_IMAP",
  is_active: true,
  is_sync_enabled: true,
};

const mockSenderAccount2: AuthorizedEmailAccount = {
  id: 6,
  company_id: 10,
  email_address: "marketing@acme.corp",
  name: "Marketing Team",
  provider: "GMAIL",
  is_active: true,
  is_sync_enabled: true,
};

const mockScheduledCampaign: CampaignDetail = {
  id: 88,
  company_id: 10,
  email_account_id: 5,
  name: "Scheduled Webinar Outreach",
  subject: "Exclusive Product Briefing",
  body_text: "Join our webinar on Friday.",
  body_html: "<p>Join our webinar on Friday.</p>",
  status: "SCHEDULED",
  scheduled_at: "2026-12-01T15:00:00Z",
  started_at: null,
  completed_at: null,
  recipient_count: 50,
  email_account_name: "Outreach Team",
  email_account_address: "outreach@acme.corp",
  created_at: "2026-10-25T10:00:00Z",
  updated_at: "2026-10-25T11:00:00Z",
  attachments: [],
  steps: [
    {
      id: 201,
      campaign_id: 88,
      step_number: 1,
      delay_hours: 0,
      subject: "Exclusive Product Briefing",
      body_text: "Join our webinar on Friday.",
      body_html: "<p>Join our webinar on Friday.</p>",
      is_active: true,
      created_at: "2026-10-25T10:00:00Z",
      updated_at: "2026-10-25T10:00:00Z",
    },
  ],
};

describe("Scheduled Campaign Cancellation & Subject Persistence", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  });

  describe("1. Stop Scheduled Campaign from CampaignDetailPage", () => {
    it("renders Stop Campaign button for SCHEDULED campaigns and successfully cancels on confirmation", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockScheduledCampaign);
      const cancelSpy = vi.spyOn(campaignsApi, "cancelCampaign").mockResolvedValue({
        ...mockScheduledCampaign,
        status: "CANCELLED",
      });

      render(
        <QueryClientProvider client={queryClient}>
          <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
            <MemoryRouter initialEntries={["/campaigns/88"]}>
              <Routes>
                <Route path="/campaigns/:campaignId" element={<CampaignDetailPage />} />
              </Routes>
            </MemoryRouter>
          </WorkspaceContext.Provider>
        </QueryClientProvider>
      );

      // Verify campaign loads with SCHEDULED badge
      await waitFor(() => {
        expect(screen.getByText("Scheduled Webinar Outreach")).toBeDefined();
      });

      // Verify "Stop Campaign" button exists in the action bar
      const stopButton = screen.getByRole("button", { name: /stop campaign/i });
      expect(stopButton).toBeDefined();

      // Click "Stop Campaign" to open modal
      fireEvent.click(stopButton);

      // Verify confirmation dialog title and content
      await waitFor(() => {
        expect(screen.getByText("Stop Scheduled Campaign?")).toBeDefined();
        expect(screen.getByText(/the scheduled execution of "Scheduled Webinar Outreach" will be cancelled/i)).toBeDefined();
      });

      // Confirm cancellation
      const confirmButton = screen.getByRole("button", { name: "Stop Scheduled Campaign" });
      fireEvent.click(confirmButton);

      await waitFor(() => {
        expect(cancelSpy).toHaveBeenCalledWith(10, 88);
      });
    });
  });

  describe("2. Stop Scheduled Campaign from CampaignTableRow & CampaignActionsMenu", () => {
    it("renders stop/cancel quick action button on CampaignTableRow for SCHEDULED campaigns", () => {
      const onCancelMock = vi.fn();
      render(
        <table>
          <tbody>
            <CampaignTableRow
              campaign={mockScheduledCampaign}
              senderAccount={mockSenderAccount}
              onView={vi.fn()}
              onCancel={onCancelMock}
            />
          </tbody>
        </table>
      );

      const cancelBtn = screen.getByRole("button", { name: /stop scheduled campaign/i });
      expect(cancelBtn).toBeDefined();

      fireEvent.click(cancelBtn);
      expect(onCancelMock).toHaveBeenCalledWith(mockScheduledCampaign);
    });

    it("renders Stop Campaign option in CampaignActionsMenu for SCHEDULED status", () => {
      const onCancelMock = vi.fn();
      render(
        <CampaignActionsMenu
          campaign={mockScheduledCampaign}
          isOpen={true}
          onToggle={vi.fn()}
          onClose={vi.fn()}
          onView={vi.fn()}
          onCancel={onCancelMock}
        />
      );

      const stopMenuItem = screen.getByRole("menuitem", { name: /stop campaign/i });
      expect(stopMenuItem).toBeDefined();

      fireEvent.click(stopMenuItem);
      expect(onCancelMock).toHaveBeenCalledWith(mockScheduledCampaign);
    });
  });

  describe("3. Campaign Subject Persistence in CreateCampaignPage", () => {
    it("preserves custom subject entered in Step 1 through subsequent steps and navigation", async () => {
      const mockAccounts = [mockSenderAccount];

      render(
        <QueryClientProvider client={queryClient}>
          <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
            <MemoryRouter initialEntries={["/campaigns/new"]}>
              <CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />
            </MemoryRouter>
          </WorkspaceContext.Provider>
        </QueryClientProvider>
      );

      // Step 1: Fill name and subject
      const nameInput = screen.getByPlaceholderText("e.g. Product Launch — October");
      const subjectInput = screen.getByPlaceholderText("e.g. Introducing our new product line");

      fireEvent.change(nameInput, { target: { value: "Summer Announcement" } });
      fireEvent.change(subjectInput, { target: { value: "My Unique Custom Subject Line" } });

      expect((subjectInput as HTMLInputElement).value).toBe("My Unique Custom Subject Line");

      // Verify anti-autofill attributes are present on inputs
      expect(subjectInput.getAttribute("autoComplete")).toBe("one-time-code");
      expect(subjectInput.getAttribute("name")).toBe("pulsemail_camp_headline");
      expect(nameInput.getAttribute("autoComplete")).toBe("one-time-code");
      expect(nameInput.getAttribute("name")).toBe("pulsemail_camp_topic");

      // Continue to Step 2 (Sender Selection)
      const continueBtn = screen.getByRole("button", { name: /^continue$/i });
      fireEvent.click(continueBtn);

      // Verify Step 2 is active
      await waitFor(() => {
        expect(screen.getByText("Sender Account")).toBeDefined();
      });

      // Continue to Step 3 (Content)
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));

      // Verify Step 3: subject line input reflects the custom subject from Step 1
      await waitFor(() => {
        expect(screen.getByText("Subject Line")).toBeDefined();
      });

      const step3SubjectInput = screen.getByDisplayValue("My Unique Custom Subject Line");
      expect(step3SubjectInput).toBeDefined();
      expect(step3SubjectInput.getAttribute("autoComplete")).toBe("one-time-code");
      expect(step3SubjectInput.getAttribute("name")).toBe("pulsemail_step_headline");

      // Navigate Back to Step 2
      fireEvent.click(screen.getByRole("button", { name: /^back$/i }));

      await waitFor(() => {
        expect(screen.getByText("Sender Account")).toBeDefined();
      });

      // Navigate Back to Step 1
      fireEvent.click(screen.getByRole("button", { name: /^back$/i }));

      await waitFor(() => {
        expect(screen.getByText("Campaign Details")).toBeDefined();
      });

      // Verify subject is still the original custom subject in Step 1
      const restoredSubjectInput = screen.getByDisplayValue("My Unique Custom Subject Line");
      expect(restoredSubjectInput).toBeDefined();
      expect((restoredSubjectInput as HTMLInputElement).value).toBe("My Unique Custom Subject Line");

      // Verify navigating forward again to Step 2 and Step 3 keeps the subject
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => {
        expect(screen.getByText("Sender Account")).toBeDefined();
      });

      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => {
        expect(screen.getByDisplayValue("My Unique Custom Subject Line")).toBeDefined();
      });
    });

    it("accepts legitimate subjects even when text matches an account email address or sender name", async () => {
      const mockAccounts = [mockSenderAccount, mockSenderAccount2];

      render(
        <QueryClientProvider client={queryClient}>
          <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
            <MemoryRouter initialEntries={["/campaigns/new"]}>
              <CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />
            </MemoryRouter>
          </WorkspaceContext.Provider>
        </QueryClientProvider>
      );

      const nameInput = screen.getByPlaceholderText("e.g. Product Launch — October");
      const subjectInput = screen.getByPlaceholderText("e.g. Introducing our new product line");

      fireEvent.change(nameInput, { target: { value: "Email Topic Campaign" } });

      // 1. Enter subject matching connected sender's email address
      fireEvent.change(subjectInput, { target: { value: mockSenderAccount.email_address } });
      expect((subjectInput as HTMLInputElement).value).toBe(mockSenderAccount.email_address);

      // 2. Enter subject matching connected sender's name
      fireEvent.change(subjectInput, { target: { value: mockSenderAccount.name } });
      expect((subjectInput as HTMLInputElement).value).toBe(mockSenderAccount.name);

      // 3. Enter custom subject
      fireEvent.change(subjectInput, { target: { value: "Q4 Partner Updates" } });
      expect((subjectInput as HTMLInputElement).value).toBe("Q4 Partner Updates");
    });

    it("switching sender account in Step 2 does not modify the entered subject", async () => {
      const mockAccounts = [mockSenderAccount, mockSenderAccount2];
      const createCampaignSpy = vi.spyOn(campaignsApi, "createCampaign").mockResolvedValue({
        id: 150,
        company_id: 10,
        email_account_id: 6,
        name: "Sender Switch Campaign",
        subject: "Strictly Preserved Subject",
        body_text: "Body text",
        body_html: "<p>Body text</p>",
        status: "DRAFT",
        scheduled_at: null,
        started_at: null,
        completed_at: null,
        recipient_count: 0,
        email_account_name: "Marketing Team",
        email_account_address: "marketing@acme.corp",
        created_at: "2026-10-25T10:00:00Z",
        updated_at: "2026-10-25T11:00:00Z",
        attachments: [],
        steps: [],
      });

      render(
        <QueryClientProvider client={queryClient}>
          <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
            <MemoryRouter initialEntries={["/campaigns/new"]}>
              <CreateCampaignPage initialAccounts={mockAccounts} companyId={10} />
            </MemoryRouter>
          </WorkspaceContext.Provider>
        </QueryClientProvider>
      );

      // Step 1: Fill Name and Subject
      const nameInput = screen.getByPlaceholderText("e.g. Product Launch — October");
      const subjectInput = screen.getByPlaceholderText("e.g. Introducing our new product line");

      fireEvent.change(nameInput, { target: { value: "Sender Switch Campaign" } });
      fireEvent.change(subjectInput, { target: { value: "Strictly Preserved Subject" } });

      // Navigate to Step 2
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => {
        expect(screen.getByText("Sender Account")).toBeDefined();
      });

      // Switch sender account to Marketing Team (id: 6)
      const marketingCard = screen.getByText("Marketing Team").closest("div[role='button']");
      if (marketingCard) {
        fireEvent.click(marketingCard);
      } else {
        fireEvent.click(screen.getByText("Marketing Team"));
      }

      // Navigate to Step 3
      fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
      await waitFor(() => {
        expect(screen.getByText("Subject Line")).toBeDefined();
      });

      // Verify subject in Step 3 is still the custom subject, not Marketing Team or marketing@acme.corp
      const step3Subject = screen.getByDisplayValue("Strictly Preserved Subject");
      expect(step3Subject).toBeDefined();

      // Enter body text via rich editor contenteditable div to satisfy Step 3 validation
      const editorDiv = document.querySelector(".compose-editor") as HTMLElement;
      if (editorDiv) {
        editorDiv.innerHTML = "<p>Body text</p>";
        fireEvent.input(editorDiv);
      }

      // Save draft from Step 3
      const saveDraftBtn = screen.getByRole("button", { name: /save draft/i });
      fireEvent.click(saveDraftBtn);

      await waitFor(() => {
        expect(createCampaignSpy).toHaveBeenCalledWith(
          10,
          expect.objectContaining({
            name: "Sender Switch Campaign",
            subject: "Strictly Preserved Subject",
            email_account_id: 6,
          })
        );
      });
    });

    it("initializes subject and body from Step 1 in edit mode when existing campaign has steps", async () => {
      const mockCampaignWithSteps: CampaignDetail = {
        id: 99,
        company_id: 10,
        email_account_id: 5,
        name: "Step 1 Draft",
        subject: "",
        body_text: null,
        body_html: null,
        status: "DRAFT",
        scheduled_at: null,
        started_at: null,
        completed_at: null,
        recipient_count: 0,
        email_account_name: "Outreach Team",
        email_account_address: "outreach@acme.corp",
        created_at: "2026-10-25T10:00:00Z",
        updated_at: "2026-10-25T11:00:00Z",
        attachments: [],
        steps: [
          {
            id: 301,
            campaign_id: 99,
            step_number: 1,
            delay_hours: 0,
            subject: "Authoritative Step 1 Subject",
            body_text: "Authoritative Step 1 Body",
            body_html: "<p>Authoritative Step 1 Body</p>",
            is_active: true,
            created_at: "2026-10-25T10:00:00Z",
            updated_at: "2026-10-25T10:00:00Z",
          },
        ],
      };

      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockCampaignWithSteps);

      render(
        <QueryClientProvider client={queryClient}>
          <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
            <MemoryRouter initialEntries={["/campaigns/99/edit"]}>
              <Routes>
                <Route
                  path="/campaigns/:campaignId/edit"
                  element={<CreateCampaignPage initialAccounts={[mockSenderAccount]} companyId={10} />}
                />
              </Routes>
            </MemoryRouter>
          </WorkspaceContext.Provider>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByDisplayValue("Authoritative Step 1 Subject")).toBeDefined();
      });
    });
  });

  describe("4. Repeated Campaign Rescheduling in CampaignDetailPage", () => {
    it("allows a scheduled campaign to be rescheduled multiple times", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockScheduledCampaign);
      vi.spyOn(campaignsApi, "preflightCampaign").mockResolvedValue({
        eligible: true,
        can_dispatch: true,
        recipient_count: 50,
        eligible_recipient_count: 50,
        suppressed_recipient_count: 0,
        active_recipients: 50,
        sender_configured: true,
        steps_count: 1,
        checks: [],
        warnings: [],
        errors: [],
        issues: [],
      } as any);
      const rescheduleSpy = vi.spyOn(campaignsApi, "rescheduleCampaign").mockImplementation(
        async (_companyId, _campaignId, data) => ({
          ...mockScheduledCampaign,
          scheduled_at: data.scheduled_at,
        })
      );

      render(
        <QueryClientProvider client={queryClient}>
          <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
            <MemoryRouter initialEntries={["/campaigns/88"]}>
              <Routes>
                <Route path="/campaigns/:campaignId" element={<CampaignDetailPage />} />
              </Routes>
            </MemoryRouter>
          </WorkspaceContext.Provider>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Scheduled Webinar Outreach")).toBeDefined();
      });

      // Find Reschedule button
      const rescheduleBtn = screen.getByRole("button", { name: /reschedule/i });
      expect(rescheduleBtn).toBeDefined();

      // First reschedule
      fireEvent.click(rescheduleBtn);
      await waitFor(() => {
        expect(screen.getByText("Schedule Campaign Execution")).toBeDefined();
      });

      // Confirm reschedule modal
      const confirmScheduleBtn = screen.getByRole("button", { name: /confirm & reschedule/i });
      fireEvent.click(confirmScheduleBtn);

      await waitFor(() => {
        expect(rescheduleSpy).toHaveBeenCalledTimes(1);
      });

      // Second reschedule can be triggered repeatedly
      fireEvent.click(rescheduleBtn);
      await waitFor(() => {
        expect(screen.getByText("Schedule Campaign Execution")).toBeDefined();
      });

      const confirmScheduleBtn2 = screen.getByRole("button", { name: /confirm & reschedule/i });
      fireEvent.click(confirmScheduleBtn2);

      await waitFor(() => {
        expect(rescheduleSpy).toHaveBeenCalledTimes(2);
      });
    });
  });
});
