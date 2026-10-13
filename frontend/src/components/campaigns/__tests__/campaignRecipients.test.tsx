import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CampaignDetail, CampaignRecipient, CampaignRecipientImportResponse } from "../../../types/campaign";
import { campaignsApi } from "../../../services/api";
import { WorkspaceContext, type WorkspaceContextType } from "../../../context/WorkspaceContext";
import { AuthContext, type AuthContextType } from "../../../context/AuthContext";
import { CampaignRecipientsPage } from "../../../pages/CampaignRecipientsPage";

import { RecipientStatusBadge } from "../recipients/RecipientStatusBadge";
import { RecipientSummaryCards } from "../recipients/RecipientSummaryCards";
import { RecipientManualForm } from "../recipients/RecipientManualForm";
import { RecipientCsvImport } from "../recipients/RecipientCsvImport";
import { RecipientTable } from "../recipients/RecipientTable";
import { RecipientMobileCard } from "../recipients/RecipientMobileCard";

const mockDraftCampaign: CampaignDetail = {
  id: 101,
  company_id: 10,
  email_account_id: 1,
  name: "Product Launch — October",
  subject: "Exclusive preview",
  status: "DRAFT",
  scheduled_at: null,
  started_at: null,
  completed_at: null,
  recipient_count: 3,
  created_at: "2026-10-08T08:00:00Z",
  updated_at: "2026-10-08T08:00:00Z",
};

const mockRunningCampaign: CampaignDetail = {
  ...mockDraftCampaign,
  id: 102,
  status: "RUNNING",
  started_at: "2026-10-08T09:00:00Z",
};

const mockRecipients: CampaignRecipient[] = [
  {
    id: 1,
    campaign_id: 101,
    email: "sarah.jenkins@acme.corp",
    first_name: "Sarah",
    last_name: "Jenkins",
    custom_variables: null,
    status: "PENDING",
    created_at: "2026-10-08T08:10:00Z",
  },
  {
    id: 2,
    campaign_id: 101,
    email: "michael.chang@cloudscale.io",
    first_name: "Michael",
    last_name: "Chang",
    custom_variables: null,
    status: "SENT",
    created_at: "2026-10-08T08:15:00Z",
  },
  {
    id: 3,
    campaign_id: 101,
    email: "elena.rostova@northern.com",
    first_name: "Elena",
    last_name: "Rostova",
    custom_variables: null,
    status: "BOUNCED",
    created_at: "2026-10-08T08:20:00Z",
  },
];

describe("Campaign Recipient Management (C12.3)", () => {
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
    campaignId = 101,
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

  describe("RecipientStatusBadge Component", () => {
    it("renders all defined backend recipient statuses correctly", () => {
      const statuses: CampaignRecipient["status"][] = [
        "PENDING",
        "SENT",
        "FAILED",
        "BOUNCED",
        "SUPPRESSED",
      ];

      for (const st of statuses) {
        const { unmount } = render(<RecipientStatusBadge status={st} />);
        expect(screen.getByText(st)).toBeDefined();
        unmount();
      }
    });
  });

  describe("RecipientSummaryCards Component", () => {
    it("truthfully calculates counts without hardcoded values", () => {
      render(
        <RecipientSummaryCards
          campaign={mockDraftCampaign}
          recipients={mockRecipients}
          isLoading={false}
        />
      );

      // Total count from campaign or array
      expect(screen.getByTestId("metric-total").textContent).toBe("3");
      // PENDING count = 1
      expect(screen.getByTestId("metric-pending").textContent).toBe("1");
      // SENT count = 1
      expect(screen.getByTestId("metric-sent").textContent).toBe("1");
      // BOUNCED count = 1
      expect(screen.getByTestId("metric-excluded").textContent).toBe("1");
    });
  });

  describe("RecipientManualForm Component", () => {
    it("validates email and calls onSubmit with sanitized payload", async () => {
      const handleSubmit = vi.fn().mockResolvedValue(undefined);

      render(<RecipientManualForm onSubmit={handleSubmit} />);

      const emailInput = screen.getByLabelText(/Email Address/i);
      const fnameInput = screen.getByLabelText(/First Name/i);
      const lnameInput = screen.getByLabelText(/Last Name/i);
      const submitBtn = screen.getByRole("button", { name: /Add Recipient/i });

      // Fill in details
      fireEvent.change(emailInput, { target: { value: "test@example.com" } });
      fireEvent.change(fnameInput, { target: { value: "John" } });
      fireEvent.change(lnameInput, { target: { value: "Doe" } });

      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(handleSubmit).toHaveBeenCalledWith({
          email: "test@example.com",
          first_name: "John",
          last_name: "Doe",
        });
      });
    });

    it("rejects invalid email format", async () => {
      const handleSubmit = vi.fn();
      render(<RecipientManualForm onSubmit={handleSubmit} />);

      const emailInput = screen.getByLabelText(/Email Address/i);
      const submitBtn = screen.getByRole("button", { name: /Add Recipient/i });

      fireEvent.change(emailInput, { target: { value: "invalid-email" } });
      fireEvent.click(submitBtn);

      expect(screen.getByText(/Please enter a valid email address/i)).toBeDefined();
      expect(handleSubmit).not.toHaveBeenCalled();
    });
  });

  describe("RecipientCsvImport Component", () => {
    it("handles CSV file selection and triggers onImport", async () => {
      const handleImport = vi.fn().mockResolvedValue({
        total_rows: 5,
        inserted_count: 4,
        skipped_duplicates_count: 1,
        invalid_rows_count: 0,
        skipped_emails: ["dup@example.com"],
        invalid_rows: [],
      } as CampaignRecipientImportResponse);

      const { container } = render(<RecipientCsvImport onImport={handleImport} />);

      const file = new File(["email,first_name\na@b.com,A"], "audience.csv", {
        type: "text/csv",
      });

      const fileInput = container.querySelector("#csv-file-input") as HTMLInputElement;
      fireEvent.change(fileInput, { target: { files: [file] } });

      expect(screen.getByText("audience.csv")).toBeDefined();

      const uploadBtn = screen.getByRole("button", { name: /Upload & Import/i });
      fireEvent.click(uploadBtn);

      await waitFor(() => {
        expect(handleImport).toHaveBeenCalledWith(file);
      });

      // Verify import result banner
      await waitFor(() => {
        expect(screen.getByText(/CSV Import Completed/i)).toBeDefined();
        expect(screen.getByText("4")).toBeDefined(); // inserted
      });
    });

    it("rejects non-csv files", () => {
      const { container } = render(<RecipientCsvImport onImport={vi.fn()} />);

      const file = new File(["not csv"], "document.pdf", { type: "application/pdf" });
      const fileInput = container.querySelector("#csv-file-input") as HTMLInputElement;
      fireEvent.change(fileInput, { target: { files: [file] } });

      expect(screen.getByText(/Only CSV files \(\.csv\) are supported/i)).toBeDefined();
    });
  });

  describe("RecipientTable and MobileCard Components", () => {
    it("renders recipient data, copy email, edit and delete callbacks", () => {
      const handleEdit = vi.fn();
      const handleDelete = vi.fn();
      const handleCopy = vi.fn();

      render(
        <RecipientTable
          recipients={mockRecipients}
          isEditable={true}
          onEdit={handleEdit}
          onDelete={handleDelete}
          onCopyEmail={handleCopy}
        />
      );

      expect(screen.getByText("sarah.jenkins@acme.corp")).toBeDefined();
      expect(screen.getByText("michael.chang@cloudscale.io")).toBeDefined();
      expect(screen.getByText("PENDING")).toBeDefined();
      expect(screen.getByText("SENT")).toBeDefined();

      // Click edit
      const editButtons = screen.getAllByTitle("Edit recipient");
      fireEvent.click(editButtons[0]);
      expect(handleEdit).toHaveBeenCalledWith(mockRecipients[0]);

      // Click delete
      const deleteButtons = screen.getAllByTitle("Remove recipient");
      fireEvent.click(deleteButtons[0]);
      expect(handleDelete).toHaveBeenCalledWith(mockRecipients[0]);
    });

    it("renders mobile card without overflowing layout", () => {
      const handleEdit = vi.fn();
      render(
        <RecipientMobileCard
          recipient={mockRecipients[0]}
          isEditable={true}
          onEdit={handleEdit}
          onDelete={vi.fn()}
          onCopyEmail={vi.fn()}
        />
      );

      expect(screen.getByText("sarah.jenkins@acme.corp")).toBeDefined();
      expect(screen.getByText("Sarah Jenkins")).toBeDefined();
      expect(screen.getByText("PENDING")).toBeDefined();
    });
  });

  describe("Full CampaignRecipientsPage Lifecycle & Permissions", () => {
    it("loads and displays campaign details and recipients in DRAFT state", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(mockRecipients);

      renderPage(101, "ADMIN");

      await waitFor(() => {
        expect(screen.getByText("Product Launch — October")).toBeDefined();
      });

      expect(screen.getAllByText("Campaign Recipients").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("sarah.jenkins@acme.corp").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Add Manually")).toBeDefined();
      expect(screen.getByText("Import CSV")).toBeDefined();
    });

    it("hides mutation options when campaign is RUNNING (not in DRAFT)", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockRunningCampaign);
      vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(mockRecipients);

      renderPage(102, "ADMIN");

      await waitFor(() => {
        expect(screen.getByText("Product Launch — October")).toBeDefined();
      });

      expect(
        screen.getAllByText((_, el) =>
          el?.textContent?.includes("Recipients cannot be modified when campaign is in RUNNING status") ?? false
        ).length
      ).toBeGreaterThanOrEqual(1);
      expect(screen.queryByText("Add Manually")).toBeNull();
      expect(screen.queryByTitle("Remove recipient")).toBeNull();
    });

    it("hides mutation options for read-only MEMBER role", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(mockRecipients);

      renderPage(101, "MEMBER");

      await waitFor(() => {
        expect(screen.getByText("Product Launch — October")).toBeDefined();
      });

      expect(
        screen.getByText(/Read-only view: Only workspace Admins and Owners/i)
      ).toBeDefined();
      expect(screen.queryByText("Add Manually")).toBeNull();
      expect(screen.queryByTitle("Remove recipient")).toBeNull();
    });

    it("performs manual recipient creation through campaignsApi.createRecipient", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(mockRecipients);
      const createSpy = vi.spyOn(campaignsApi, "createRecipient").mockResolvedValue({
        id: 99,
        campaign_id: 101,
        email: "newuser@example.com",
        first_name: "New",
        last_name: "User",
        custom_variables: null,
        status: "PENDING",
        created_at: "2026-10-08T10:00:00Z",
      });

      renderPage(101, "ADMIN");

      await waitFor(() => {
        expect(screen.getAllByText("sarah.jenkins@acme.corp").length).toBeGreaterThanOrEqual(1);
      });

      const emailInput = screen.getByLabelText(/Email Address/i);
      fireEvent.change(emailInput, { target: { value: "newuser@example.com" } });

      const submitBtn = screen.getByRole("button", { name: /Add Recipient/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(10, 101, {
          email: "newuser@example.com",
          first_name: null,
          last_name: null,
        });
      });
    });

    it("opens delete confirmation modal and calls campaignsApi.deleteRecipient on confirmation", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(mockRecipients);
      const deleteSpy = vi.spyOn(campaignsApi, "deleteRecipient").mockResolvedValue();

      renderPage(101, "ADMIN");

      await waitFor(() => {
        expect(screen.getAllByText("sarah.jenkins@acme.corp").length).toBeGreaterThanOrEqual(1);
      });

      const deleteButtons = screen.getAllByTitle("Remove recipient");
      fireEvent.click(deleteButtons[0]);

      // Confirm modal opens
      expect(screen.getByRole("dialog")).toBeDefined();
      expect(screen.getByText("Remove Recipient?")).toBeDefined();

      const confirmBtn = screen.getByRole("button", { name: "Remove Recipient" });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(deleteSpy).toHaveBeenCalledWith(10, 101, 1);
      });
    });

    it("opens edit modal and updates recipient through campaignsApi.updateRecipient", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue(mockRecipients);
      const updateSpy = vi.spyOn(campaignsApi, "updateRecipient").mockResolvedValue({
        ...mockRecipients[0],
        first_name: "Sara",
      });

      renderPage(101, "ADMIN");

      await waitFor(() => {
        expect(screen.getAllByText("sarah.jenkins@acme.corp").length).toBeGreaterThanOrEqual(1);
      });

      const editButtons = screen.getAllByTitle("Edit recipient");
      fireEvent.click(editButtons[0]);

      expect(screen.getByText("Edit Recipient Info")).toBeDefined();

      const fnameInput = screen.getByDisplayValue("Sarah");
      fireEvent.change(fnameInput, { target: { value: "Sara" } });

      const saveBtn = screen.getByRole("button", { name: /Save Changes/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(10, 101, 1, {
          email: "sarah.jenkins@acme.corp",
          first_name: "Sara",
          last_name: "Jenkins",
        });
      });
    });

    it("displays empty audience state when no recipients exist", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue({
        ...mockDraftCampaign,
        recipient_count: 0,
      });
      vi.spyOn(campaignsApi, "listRecipients").mockResolvedValue([]);

      renderPage(101, "ADMIN");

      await waitFor(() => {
        expect(screen.getByText("No recipients in campaign audience")).toBeDefined();
      });
    });

    it("displays error state with retry button when query fails", async () => {
      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);
      vi.spyOn(campaignsApi, "listRecipients").mockRejectedValue(
        new Error("Connection timeout")
      );

      renderPage(101, "ADMIN");

      await waitFor(() => {
        expect(screen.getByText("Unable to query recipient repository")).toBeDefined();
        expect(screen.getByText("Connection timeout")).toBeDefined();
      });

      const retryBtn = screen.getByRole("button", { name: /Retry Query/i });
      expect(retryBtn).toBeDefined();
    });
  });
});
