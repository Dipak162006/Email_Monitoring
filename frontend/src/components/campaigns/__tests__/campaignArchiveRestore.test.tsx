import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";

import type { Campaign, CampaignDetail } from "../../../types/campaign";
import type { AuthorizedEmailAccount } from "../../../types/emails";
import type { CompanyWithRole } from "../../../types/auth";
import { campaignsApi } from "../../../services/api";
import { WorkspaceContext, type WorkspaceContextType } from "../../../context/WorkspaceContext";
import { CancelCampaignModal } from "../CancelCampaignModal";
import { CampaignActionsMenu } from "../CampaignActionsMenu";
import { CampaignTableRow } from "../CampaignTableRow";
import { CampaignToolbar } from "../CampaignToolbar";
import { CampaignDetailPage } from "../../../pages/CampaignDetailPage";

const mockAdminCompany: CompanyWithRole = {
  id: 10,
  name: "Safe Archive Org",
  role: "ADMIN",
  is_active: true,
  created_at: "2026-10-01T00:00:00Z",
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

const makeMockCampaign = (overrides?: Partial<Campaign>): Campaign => ({
  id: 101,
  company_id: 10,
  email_account_id: 5,
  name: "Winter Newsletter",
  subject: "Updates for Winter",
  status: "DRAFT",
  created_at: "2026-10-10T10:00:00Z",
  updated_at: "2026-10-10T12:00:00Z",
  recipient_count: 50,
  ...overrides,
});

const mockEmailAccounts: AuthorizedEmailAccount[] = [
  {
    id: 5,
    company_id: 10,
    email_address: "outreach@acme.com",
    name: "Outreach Team",
    provider: "SMTP_IMAP",
    is_active: true,
    is_sync_enabled: true,
  },
];

describe("Milestone M3 — Safe Campaign Deletion, Archiving & Restore", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false, gcTime: 0 },
      },
    });
  });

  describe("1. CancelCampaignModal Lifecycle Modes", () => {
    it("renders Archive mode with explanation preserving history and non-destructive action", () => {
      const campaign = makeMockCampaign({ name: "Q4 Outreach", status: "COMPLETED" });
      const onConfirm = vi.fn();
      const onClose = vi.fn();

      render(
        <CancelCampaignModal
          isOpen={true}
          campaign={campaign}
          mode="archive"
          onClose={onClose}
          onConfirm={onConfirm}
        />
      );

      expect(screen.getByRole("heading", { name: /archive campaign\?/i })).toBeDefined();
      expect(
        screen.getByText(/will be moved to the archive and removed from the active campaign list/i)
      ).toBeDefined();
      expect(screen.getByText(/all campaign history, recipient data, and steps will be preserved/i)).toBeDefined();

      const archiveBtn = screen.getByRole("button", { name: /archive campaign/i });
      fireEvent.click(archiveBtn);
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it("renders Restore mode explaining safe inactive restoration without automatic sending", () => {
      const campaign = makeMockCampaign({ name: "Q4 Outreach", status: "ARCHIVED" });
      const onConfirm = vi.fn();
      const onClose = vi.fn();

      render(
        <CancelCampaignModal
          isOpen={true}
          campaign={campaign}
          mode="restore"
          onClose={onClose}
          onConfirm={onConfirm}
        />
      );

      expect(screen.getByRole("heading", { name: /restore campaign\?/i })).toBeDefined();
      expect(
        screen.getByText(/will not automatically resume or schedule email deliveries/i)
      ).toBeDefined();

      const restoreBtn = screen.getByRole("button", { name: /restore campaign/i });
      fireEvent.click(restoreBtn);
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it("renders Delete mode with permanent removal warning", () => {
      const campaign = makeMockCampaign({ name: "Old Draft", status: "ARCHIVED" });
      const onConfirm = vi.fn();
      const onClose = vi.fn();

      render(
        <CancelCampaignModal
          isOpen={true}
          campaign={campaign}
          mode="delete"
          onClose={onClose}
          onConfirm={onConfirm}
        />
      );

      expect(screen.getByRole("heading", { name: /delete archived campaign\?/i })).toBeDefined();
      expect(screen.getByText(/permanently removed\. this action cannot be undone/i)).toBeDefined();

      const deleteBtn = screen.getByRole("button", { name: /delete permanently/i });
      fireEvent.click(deleteBtn);
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });
  });

  describe("2. CampaignActionsMenu Action Visibility & Status Enforcement", () => {
    it("shows Archive Campaign and Delete Draft for DRAFT status", () => {
      const campaign = makeMockCampaign({ status: "DRAFT" });
      const onArchive = vi.fn();
      const onDelete = vi.fn();

      render(
        <CampaignActionsMenu
          campaign={campaign}
          isOpen={true}
          onToggle={vi.fn()}
          onClose={vi.fn()}
          onView={vi.fn()}
          onArchive={onArchive}
          onDelete={onDelete}
        />
      );

      expect(screen.getByRole("menuitem", { name: /archive campaign/i })).toBeDefined();
      expect(screen.getByRole("menuitem", { name: /delete draft/i })).toBeDefined();
      expect(screen.queryByRole("menuitem", { name: /restore campaign/i })).toBeNull();

      fireEvent.click(screen.getByRole("menuitem", { name: /archive campaign/i }));
      expect(onArchive).toHaveBeenCalledWith(campaign);
    });

    it("shows Restore Campaign and Delete Permanently for ARCHIVED status", () => {
      const campaign = makeMockCampaign({ status: "ARCHIVED" });
      const onRestore = vi.fn();
      const onDelete = vi.fn();

      render(
        <CampaignActionsMenu
          campaign={campaign}
          isOpen={true}
          onToggle={vi.fn()}
          onClose={vi.fn()}
          onView={vi.fn()}
          onRestore={onRestore}
          onDelete={onDelete}
        />
      );

      expect(screen.getByRole("menuitem", { name: /restore campaign/i })).toBeDefined();
      expect(screen.getByRole("menuitem", { name: /delete permanently/i })).toBeDefined();
      expect(screen.queryByRole("menuitem", { name: /archive campaign/i })).toBeNull();

      fireEvent.click(screen.getByRole("menuitem", { name: /restore campaign/i }));
      expect(onRestore).toHaveBeenCalledWith(campaign);
    });

    it("does NOT show Archive Campaign for active RUNNING campaigns", () => {
      const campaign = makeMockCampaign({ status: "RUNNING" });
      const onArchive = vi.fn();

      render(
        <CampaignActionsMenu
          campaign={campaign}
          isOpen={true}
          onToggle={vi.fn()}
          onClose={vi.fn()}
          onView={vi.fn()}
          onArchive={onArchive}
          onPause={vi.fn()}
        />
      );

      expect(screen.queryByRole("menuitem", { name: /archive campaign/i })).toBeNull();
      expect(screen.getByRole("menuitem", { name: /pause campaign/i })).toBeDefined();
    });
  });

  describe("3. CampaignTableRow Action Buttons & Tooltips", () => {
    it("renders Archive button for archivable completed campaign", () => {
      const campaign = makeMockCampaign({ status: "COMPLETED" });
      const onArchive = vi.fn();

      render(
        <table>
          <tbody>
            <CampaignTableRow
              campaign={campaign}
              senderAccount={mockEmailAccounts[0]}
              onView={vi.fn()}
              onArchive={onArchive}
            />
          </tbody>
        </table>
      );

      const archiveBtn = screen.getByRole("button", { name: /archive campaign/i });
      expect(archiveBtn).toBeDefined();
      fireEvent.click(archiveBtn);
      expect(onArchive).toHaveBeenCalledWith(campaign);
    });

    it("renders Restore and Delete Permanently buttons for ARCHIVED campaign", () => {
      const campaign = makeMockCampaign({ status: "ARCHIVED" });
      const onRestore = vi.fn();
      const onDelete = vi.fn();

      render(
        <table>
          <tbody>
            <CampaignTableRow
              campaign={campaign}
              senderAccount={mockEmailAccounts[0]}
              onView={vi.fn()}
              onRestore={onRestore}
              onDelete={onDelete}
            />
          </tbody>
        </table>
      );

      const restoreBtn = screen.getByRole("button", { name: /restore campaign/i });
      expect(restoreBtn).toBeDefined();
      fireEvent.click(restoreBtn);
      expect(onRestore).toHaveBeenCalledWith(campaign);

      const deleteBtn = screen.getByRole("button", { name: /delete campaign permanently/i });
      expect(deleteBtn).toBeDefined();
      fireEvent.click(deleteBtn);
      expect(onDelete).toHaveBeenCalledWith(campaign);
    });
  });

  describe("4. CampaignToolbar Status Filter", () => {
    it("includes ARCHIVED in status filter dropdown", () => {
      const onStatusChange = vi.fn();

      render(
        <CampaignToolbar
          searchQuery=""
          onSearchChange={vi.fn()}
          statusFilter="ALL"
          onStatusFilterChange={onStatusChange}
          senderFilter="ALL"
          onSenderFilterChange={vi.fn()}
          emailAccounts={mockEmailAccounts}
          onClearFilters={vi.fn()}
          hasActiveFilters={false}
        />
      );

      const select = screen.getByRole("combobox", { name: /filter by campaign status/i });
      expect(select).toBeDefined();

      const archivedOption = screen.getByRole("option", { name: /archived/i });
      expect(archivedOption).toBeDefined();

      fireEvent.change(select, { target: { value: "ARCHIVED" } });
      expect(onStatusChange).toHaveBeenCalledWith("ARCHIVED");
    });
  });

  describe("5. CampaignDetailPage Banner & Action Controls", () => {
    it("displays prominent archived banner and Restore action when viewing an ARCHIVED campaign", async () => {
      const archivedCampaignDetail: CampaignDetail = {
        ...makeMockCampaign({
          id: 42,
          name: "Old Fall Outreach",
          status: "ARCHIVED",
        }),
        recipient_count: 50,
        pending_count: 0,
        sent_count: 50,
        failed_count: 0,
        bounced_count: 0,
        suppressed_count: 0,
        attachments: [],
        steps: [],
      };

      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(archivedCampaignDetail);

      render(
        <QueryClientProvider client={queryClient}>
          <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
            <MemoryRouter initialEntries={["/campaigns/42"]}>
              <Routes>
                <Route path="/campaigns/:campaignId" element={<CampaignDetailPage />} />
              </Routes>
            </MemoryRouter>
          </WorkspaceContext.Provider>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByRole("heading", { name: "Old Fall Outreach" })).toBeDefined();
      });

      // Banner text
      expect(screen.getByText(/this campaign is archived/i)).toBeDefined();
      expect(
        screen.getByText(/all sending and schedule triggers are stopped\. campaign history, steps, and recipient logs are preserved/i)
      ).toBeDefined();

      // Restore button in banner
      const bannerRestoreBtn = screen.getByRole("button", { name: /restore campaign/i });
      expect(bannerRestoreBtn).toBeDefined();

      // Restore and Delete Permanently in header actions
      expect(screen.getByRole("button", { name: "Restore" })).toBeDefined();
      expect(screen.getByRole("button", { name: /delete permanently/i })).toBeDefined();
    });
  });
});
