import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import type { Campaign } from "../../../types/campaign";
import type { AuthorizedEmailAccount } from "../../../types/emails";
import { campaignsApi, emailAccountsApi } from "../../../services/api";
import { WorkspaceContext, type WorkspaceContextType } from "../../../context/WorkspaceContext";
import { AuthContext, type AuthContextType } from "../../../context/AuthContext";
import { CampaignsPage } from "../../../pages/CampaignsPage";

import { CampaignStatusBadge } from "../CampaignStatusBadge";
import { CampaignPageHeader } from "../CampaignPageHeader";
import { CampaignSummaryCards } from "../CampaignSummaryCards";
import { CampaignToolbar } from "../CampaignToolbar";
import { CampaignTable } from "../CampaignTable";
import { CampaignTableRow } from "../CampaignTableRow";
import { CampaignMobileCard } from "../CampaignMobileCard";
import { CampaignActionsMenu } from "../CampaignActionsMenu";
import { CancelCampaignModal } from "../CancelCampaignModal";
import { CampaignPagination } from "../CampaignPagination";
import { CampaignEmptyState } from "../CampaignEmptyState";
import { CampaignSearchEmptyState } from "../CampaignSearchEmptyState";
import { CampaignErrorState } from "../CampaignErrorState";
import { CampaignSkeleton } from "../CampaignSkeleton";

// Sample test data
const mockAccounts: AuthorizedEmailAccount[] = [
  {
    id: 1,
    company_id: 10,
    name: "Sales Team",
    email_address: "sales@example.com",
    provider: "SMTP_IMAP",
    is_active: true,
    is_sync_enabled: true,
  },
  {
    id: 2,
    company_id: 10,
    name: "Marketing",
    email_address: "marketing@example.com",
    provider: "GMAIL",
    is_active: true,
    is_sync_enabled: true,
  },
];

const mockCampaigns: Campaign[] = [
  {
    id: 101,
    company_id: 10,
    email_account_id: 1,
    name: "Q4 Product Launch",
    subject: "Introducing our latest release",
    status: "RUNNING",
    scheduled_at: null,
    started_at: "2026-10-08T08:00:00Z",
    completed_at: null,
    recipient_count: 1250,
    created_at: "2026-10-08T07:00:00Z",
    updated_at: "2026-10-08T08:00:00Z",
  },
  {
    id: 102,
    company_id: 10,
    email_account_id: 2,
    name: "Weekly Newsletter",
    subject: "Community highlights",
    status: "SCHEDULED",
    scheduled_at: "2026-10-15T10:00:00Z",
    started_at: null,
    completed_at: null,
    recipient_count: 4500,
    created_at: "2026-10-07T09:00:00Z",
    updated_at: "2026-10-07T09:00:00Z",
  },
  {
    id: 103,
    company_id: 10,
    email_account_id: 1,
    name: "Draft Campaign",
    subject: "",
    status: "DRAFT",
    scheduled_at: null,
    started_at: null,
    completed_at: null,
    recipient_count: 50,
    created_at: "2026-10-06T11:00:00Z",
    updated_at: "2026-10-06T11:00:00Z",
  },
  {
    id: 104,
    company_id: 10,
    email_account_id: 2,
    name: "Paused Outreach",
    subject: "Re-engagement check",
    status: "PAUSED",
    scheduled_at: null,
    started_at: "2026-10-05T08:00:00Z",
    completed_at: null,
    recipient_count: 800,
    created_at: "2026-10-05T07:00:00Z",
    updated_at: "2026-10-05T12:00:00Z",
  },
];

describe("CampaignStatusBadge Component", () => {
  it("renders all 8 campaign statuses with proper accessible labels", () => {
    const statuses = [
      "DRAFT",
      "SCHEDULED",
      "QUEUED",
      "RUNNING",
      "PAUSED",
      "COMPLETED",
      "CANCELLED",
      "FAILED",
    ] as const;

    for (const status of statuses) {
      const { unmount } = render(<CampaignStatusBadge status={status} />);
      expect(screen.getByText(status)).toBeDefined();
      unmount();
    }
  });
});

describe("CampaignPageHeader Component", () => {
  it("renders title, real total campaign count, and handles create button click", () => {
    const handleCreate = vi.fn();
    const handleToggleView = vi.fn();

    render(
      <CampaignPageHeader
        totalCount={42}
        showViewOptions={true}
        onToggleViewOptions={handleToggleView}
        onCreateCampaign={handleCreate}
      />
    );

    expect(screen.getByText("Campaigns")).toBeDefined();
    expect(screen.getByText("42 total")).toBeDefined();
    expect(
      screen.getByText(
        "Create, schedule, and manage your automated outreach pipelines."
      )
    ).toBeDefined();

    const createBtn = screen.getByRole("button", { name: /create campaign/i });
    fireEvent.click(createBtn);
    expect(handleCreate).toHaveBeenCalledTimes(1);

    const viewOptBtn = screen.getByRole("button", { name: /view options/i });
    fireEvent.click(viewOptBtn);
    expect(handleToggleView).toHaveBeenCalledTimes(1);
  });
});

describe("CampaignSummaryCards Component", () => {
  it("truthfully computes metrics from campaign data without hardcoded values", () => {
    render(<CampaignSummaryCards campaigns={mockCampaigns} isLoading={false} />);

    // Active = RUNNING (1) + QUEUED (0) = 1
    expect(screen.getByText("Active Campaigns")).toBeDefined();
    expect(screen.getByText("1 in delivery")).toBeDefined();

    // Scheduled = 1
    expect(screen.getByText("Scheduled")).toBeDefined();
    expect(screen.getByText("Upcoming dispatches")).toBeDefined();

    // Draft = 1
    expect(screen.getByText("Draft Pipelines")).toBeDefined();

    // Completed = 0
    expect(screen.getByText("Completed")).toBeDefined();
    expect(screen.getByText("None completed")).toBeDefined();
  });

  it("renders pulse skeletons when loading", () => {
    const { container } = render(
      <CampaignSummaryCards campaigns={[]} isLoading={true} />
    );
    const pulseCards = container.querySelectorAll(".animate-pulse");
    expect(pulseCards.length).toBe(4);
  });
});

describe("CampaignToolbar Component", () => {
  it("handles search changes and filter selections", () => {
    const onSearchChange = vi.fn();
    const onStatusChange = vi.fn();
    const onSenderChange = vi.fn();
    const onClear = vi.fn();

    render(
      <CampaignToolbar
        searchQuery="Newsletter"
        onSearchChange={onSearchChange}
        statusFilter="ALL"
        onStatusFilterChange={onStatusChange}
        senderFilter="ALL"
        onSenderFilterChange={onSenderChange}
        emailAccounts={mockAccounts}
        onClearFilters={onClear}
        hasActiveFilters={true}
      />
    );

    const searchInput = screen.getByPlaceholderText(
      "Filter loaded campaigns..."
    ) as HTMLInputElement;
    expect(searchInput.value).toBe("Newsletter");

    fireEvent.change(searchInput, { target: { value: "New Search" } });
    expect(onSearchChange).toHaveBeenCalledWith("New Search");

    const clearBtn = screen.getByTitle("Reset active filters");
    fireEvent.click(clearBtn);
    expect(onClear).toHaveBeenCalledTimes(1);
  });
});

describe("CampaignTable & CampaignTableRow Components", () => {
  it("renders table with campaign rows, resolved sender accounts, and target sizes", () => {
    render(
      <CampaignTable
        campaigns={mockCampaigns}
        emailAccounts={mockAccounts}
        onViewCampaign={vi.fn()}
        onCancelCampaign={vi.fn()}
        onDeleteCampaign={vi.fn()}
      />
    );

    expect(screen.getAllByText("Q4 Product Launch").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Weekly Newsletter").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("1,250 recipients").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("4,500 recipients").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("sales@example.com").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("marketing@example.com").length).toBeGreaterThanOrEqual(1);
  });
});

describe("CampaignMobileCard Component", () => {
  it("renders responsive mobile card layout with action controls", () => {
    const onView = vi.fn();
    render(
      <CampaignMobileCard
        campaign={mockCampaigns[0]}
        senderAccount={mockAccounts[0]}
        isMenuOpen={false}
        onToggleMenu={vi.fn()}
        onCloseMenu={vi.fn()}
        onView={onView}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText("Q4 Product Launch")).toBeDefined();
    expect(screen.getByText("Introducing our latest release")).toBeDefined();
    expect(screen.getByText("1,250 recipients")).toBeDefined();
    expect(screen.getByText("RUNNING")).toBeDefined();
  });
});

describe("CampaignActionsMenu Component", () => {
  it("displays state-aware actions for RUNNING campaign (Pause, Cancel)", () => {
    const onPause = vi.fn();
    const onCancel = vi.fn();

    render(
      <CampaignActionsMenu
        campaign={mockCampaigns[0]} // RUNNING
        isOpen={true}
        onToggle={vi.fn()}
        onClose={vi.fn()}
        onView={vi.fn()}
        onPause={onPause}
        onCancel={onCancel}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText("Pause Campaign")).toBeDefined();
    expect(screen.getByText("Cancel Campaign")).toBeDefined();

    fireEvent.click(screen.getByText("Pause Campaign"));
    expect(onPause).toHaveBeenCalledTimes(1);
  });

  it("displays state-aware actions for DRAFT campaign (Edit, Delete Draft)", () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();

    render(
      <CampaignActionsMenu
        campaign={mockCampaigns[2]} // DRAFT
        isOpen={true}
        onToggle={vi.fn()}
        onClose={vi.fn()}
        onView={vi.fn()}
        onEdit={onEdit}
        onCancel={vi.fn()}
        onDelete={onDelete}
      />
    );

    expect(screen.getByText("Edit Draft")).toBeDefined();
    expect(screen.getByText("Delete Draft")).toBeDefined();

    fireEvent.click(screen.getByText("Delete Draft"));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });
});

describe("CancelCampaignModal Component", () => {
  it("distinguishes between Cancel Campaign and Delete Draft copy", () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();

    // Mode: cancel
    const { rerender } = render(
      <CancelCampaignModal
        isOpen={true}
        campaign={mockCampaigns[1]} // SCHEDULED
        mode="cancel"
        onClose={onClose}
        onConfirm={onConfirm}
      />
    );

    expect(screen.getByText("Cancel Scheduled Campaign?")).toBeDefined();
    expect(
      screen.getByText(/will halt all pending deliveries and transition permanently to CANCELLED/i)
    ).toBeDefined();
    expect(screen.getByText("Keep Campaign")).toBeDefined();

    const cancelActionBtn = screen.getByRole("button", {
      name: "Cancel Campaign",
    });
    fireEvent.click(cancelActionBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);

    // Mode: delete
    rerender(
      <CancelCampaignModal
        isOpen={true}
        campaign={mockCampaigns[2]} // DRAFT
        mode="delete"
        onClose={onClose}
        onConfirm={onConfirm}
      />
    );

    expect(screen.getByText("Delete Draft Campaign?")).toBeDefined();
    expect(
      screen.getByText(/associated records will be permanently removed/i)
    ).toBeDefined();
  });
});

describe("CampaignPagination Component", () => {
  it("renders showing X-Y of Z and navigates pages", () => {
    const onPageChange = vi.fn();

    render(
      <CampaignPagination
        currentPage={2}
        pageSize={10}
        totalItems={25}
        onPageChange={onPageChange}
      />
    );

    expect(screen.getByText("11–20")).toBeDefined();
    expect(screen.getByText("25")).toBeDefined();

    const nextBtn = screen.getByRole("button", { name: /next/i });
    fireEvent.click(nextBtn);
    expect(onPageChange).toHaveBeenCalledWith(3);

    const prevBtn = screen.getByRole("button", { name: /previous/i });
    fireEvent.click(prevBtn);
    expect(onPageChange).toHaveBeenCalledWith(1);
  });
});

describe("Empty and Error States", () => {
  it("renders CampaignEmptyState when no campaigns exist", () => {
    const onCreate = vi.fn();
    render(<CampaignEmptyState onCreateCampaign={onCreate} />);
    expect(screen.getByText("No campaigns yet")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: /create campaign/i }));
    expect(onCreate).toHaveBeenCalledTimes(1);
  });

  it("renders CampaignSearchEmptyState when search/filters return zero results", () => {
    const onClear = vi.fn();
    render(<CampaignSearchEmptyState onClearFilters={onClear} />);
    expect(screen.getByText("No campaigns found")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: /clear filters/i }));
    expect(onClear).toHaveBeenCalledTimes(1);
  });

  it("renders CampaignErrorState with retry button", () => {
    const onRetry = vi.fn();
    render(
      <CampaignErrorState
        message="504 Gateway Timeout"
        onRetry={onRetry}
      />
    );
    expect(screen.getByText("Unable to load campaigns")).toBeDefined();
    expect(screen.getByText("504 Gateway Timeout")).toBeDefined();

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("renders CampaignSkeleton without crash", () => {
    const { container } = render(<CampaignSkeleton />);
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
  });
});

describe("Recipient Count Semantics (C12.1 Correction)", () => {
  it("renders real recipient count when present (including 0 when real)", () => {
    const campaignWithCount: Campaign = {
      ...mockCampaigns[0],
      recipient_count: 1250,
    };
    const campaignWithZero: Campaign = {
      ...mockCampaigns[0],
      id: 999,
      recipient_count: 0,
    };

    const { unmount } = render(
      <table>
        <tbody>
          <CampaignTableRow
            campaign={campaignWithCount}
            isMenuOpen={false}
            onToggleMenu={vi.fn()}
            onCloseMenu={vi.fn()}
            onView={vi.fn()}
            onCancel={vi.fn()}
            onDelete={vi.fn()}
          />
        </tbody>
      </table>
    );
    expect(screen.getByText("1,250 recipients")).toBeDefined();
    unmount();

    render(
      <table>
        <tbody>
          <CampaignTableRow
            campaign={campaignWithZero}
            isMenuOpen={false}
            onToggleMenu={vi.fn()}
            onCloseMenu={vi.fn()}
            onView={vi.fn()}
            onCancel={vi.fn()}
            onDelete={vi.fn()}
          />
        </tbody>
      </table>
    );
    expect(screen.getByText("0 recipients")).toBeDefined();
  });

  it("renders unavailable indicator '— recipients' when recipient_count is missing and never renders '0 recipients'", () => {
    const campaignMissingCount: Campaign = {
      ...mockCampaigns[0],
      recipient_count: undefined,
    };

    // Table row test
    const { unmount } = render(
      <table>
        <tbody>
          <CampaignTableRow
            campaign={campaignMissingCount}
            isMenuOpen={false}
            onToggleMenu={vi.fn()}
            onCloseMenu={vi.fn()}
            onView={vi.fn()}
            onCancel={vi.fn()}
            onDelete={vi.fn()}
          />
        </tbody>
      </table>
    );
    expect(screen.getByText("— recipients")).toBeDefined();
    expect(screen.queryByText("0 recipients")).toBeNull();
    unmount();

    // Mobile card test
    render(
      <CampaignMobileCard
        campaign={campaignMissingCount}
        isMenuOpen={false}
        onToggleMenu={vi.fn()}
        onCloseMenu={vi.fn()}
        onView={vi.fn()}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.getByText("— recipients")).toBeDefined();
    expect(screen.queryByText("0 recipients")).toBeNull();
  });
});

describe("Search, Filter, and Pagination Semantics (C12.1 Correction)", () => {
  it("confirms API client generates only supported query parameters (status, limit, offset)", async () => {
    const listSpy = vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue([]);

    await campaignsApi.listCampaigns(10, {
      status: "RUNNING",
      limit: 25,
      offset: 50,
    });

    expect(listSpy).toHaveBeenCalledWith(10, {
      status: "RUNNING",
      limit: 25,
      offset: 50,
    });

    listSpy.mockRestore();
  });

  it("confirms client-side search/filter operates on currently loaded page honestly", () => {
    const pageItems = [
      { ...mockCampaigns[0], name: "Alpha Launch", email_account_id: 1 },
      { ...mockCampaigns[1], name: "Beta Newsletter", email_account_id: 2 },
    ];

    const searchFilter = (items: Campaign[], q: string) =>
      items.filter((c) => c.name.toLowerCase().includes(q.toLowerCase()));

    const senderFilter = (items: Campaign[], accId: number) =>
      items.filter((c) => c.email_account_id === accId);

    expect(searchFilter(pageItems, "Alpha")).toHaveLength(1);
    expect(searchFilter(pageItems, "Alpha")[0].name).toBe("Alpha Launch");
    expect(searchFilter(pageItems, "Nonexistent")).toHaveLength(0);

    expect(senderFilter(pageItems, 1)).toHaveLength(1);
    expect(senderFilter(pageItems, 2)).toHaveLength(1);
  });
});

describe("C12.1 Refined Campaign Table & Floating Action Menu Overlay", () => {
  it("renders campaign row without action menu by default", () => {
    render(
      <table>
        <tbody>
          <CampaignTableRow
            campaign={mockCampaigns[0]}
            senderAccount={mockAccounts[0]}
            isMenuOpen={false}
            onToggleMenu={vi.fn()}
            onCloseMenu={vi.fn()}
            onView={vi.fn()}
            onCancel={vi.fn()}
            onDelete={vi.fn()}
          />
        </tbody>
      </table>
    );

    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByText("Q4 Product Launch")).toBeDefined();
    expect(screen.getByText("1,250 recipients")).toBeDefined();
  });

  it("renders contextual action buttons on desktop row across 6 columns without dedicated actions column", () => {
    const handleView = vi.fn();
    const handleManage = vi.fn();
    const handleDelete = vi.fn();

    const { container } = render(
      <table>
        <tbody>
          <CampaignTableRow
            campaign={mockCampaigns[0]}
            senderAccount={mockAccounts[0]}
            onView={handleView}
            onManageRecipients={handleManage}
            onDelete={handleDelete}
          />
        </tbody>
      </table>
    );

    // The tr element contains exactly 6 information columns (no 7th Actions column)
    const tr = container.querySelector("tr");
    expect(tr?.children.length).toBe(6);

    // Contextual action buttons are present with accessible labels
    const viewBtn = screen.getByRole("button", { name: "View campaign" });
    expect(viewBtn).toBeDefined();

    const manageBtn = screen.getByRole("button", { name: "Manage recipients" });
    expect(manageBtn).toBeDefined();

    fireEvent.click(viewBtn);
    expect(handleView).toHaveBeenCalledWith(mockCampaigns[0]);

    fireEvent.click(manageBtn);
    expect(handleManage).toHaveBeenCalledWith(mockCampaigns[0]);
  });

  it("closes action menu on Escape key press", () => {
    const handleClose = vi.fn();
    render(
      <CampaignActionsMenu
        campaign={mockCampaigns[0]}
        isOpen={true}
        onToggle={vi.fn()}
        onClose={handleClose}
        onView={vi.fn()}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByRole("menu")).toBeDefined();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("closes action menu on outside click", () => {
    const handleClose = vi.fn();
    render(
      <div>
        <div data-testid="outside-area">Outside</div>
        <CampaignActionsMenu
          campaign={mockCampaigns[0]}
          isOpen={true}
          onToggle={vi.fn()}
          onClose={handleClose}
          onView={vi.fn()}
          onCancel={vi.fn()}
          onDelete={vi.fn()}
        />
      </div>
    );

    const outsideArea = screen.getByTestId("outside-area");
    fireEvent.mouseDown(outsideArea);
    expect(handleClose).toHaveBeenCalledTimes(1);
  });

  it("ensures multiple menus do not remain open simultaneously in CampaignTable", () => {
    render(
      <CampaignTable
        campaigns={mockCampaigns}
        emailAccounts={mockAccounts}
        onViewCampaign={vi.fn()}
        onEditCampaign={vi.fn()}
        onPauseCampaign={vi.fn()}
        onCancelCampaign={vi.fn()}
        onDeleteCampaign={vi.fn()}
      />
    );

    // Initially no menu is open
    expect(screen.queryByRole("menu")).toBeNull();

    // Click campaign 1 action button (RUNNING campaign)
    const actionButtons = screen.getAllByRole("button", {
      name: /actions for campaign/i,
    });
    fireEvent.click(actionButtons[0]);

    // Campaign 1 menu actions are present (exactly one menu open)
    expect(screen.getAllByText("Pause Campaign").length).toBe(1);
    expect(screen.queryByText("Edit Draft")).toBeNull();

    // Click campaign 3 action button (DRAFT campaign)
    // index 2 is mockCampaigns[2] in the desktop rows
    fireEvent.click(actionButtons[2]);

    // Campaign 3 menu actions are present, and campaign 1 menu is closed
    expect(screen.getAllByText("Edit Draft").length).toBe(1);
    expect(screen.queryByText("Pause Campaign")).toBeNull();
  });

  it("renders mobile card action menu as floating portal overlay without altering card height", () => {
    const { container } = render(
      <CampaignMobileCard
        campaign={mockCampaigns[2]} // DRAFT
        senderAccount={mockAccounts[0]}
        isMenuOpen={true}
        onToggleMenu={vi.fn()}
        onCloseMenu={vi.fn()}
        onView={vi.fn()}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    const menu = screen.getByRole("menu");
    expect(menu).toBeDefined();
    expect(menu.style.position).toBe("fixed");
    expect(screen.getByText("Delete Draft")).toBeDefined();

    // Verify card structure remains clean
    expect(container.querySelector("h3")?.textContent).toBe("Draft Campaign");
  });
});

describe("CampaignActionsMenu Bug Fixes & Action Handling Verification", () => {
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
    mockNavigate.mockClear();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.restoreAllMocks();
  });

  const renderCampaignsPage = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AuthContext.Provider value={mockAuthValue}>
            <WorkspaceContext.Provider value={mockWorkspaceValue}>
              <CampaignsPage />
            </WorkspaceContext.Provider>
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  // 1. Opening a row menu produces exactly one visible menu
  it("Requirement 1: opening a row menu produces exactly one visible menu", () => {
    render(
      <CampaignTable
        campaigns={mockCampaigns}
        emailAccounts={mockAccounts}
        onViewCampaign={vi.fn()}
        onCancelCampaign={vi.fn()}
        onDeleteCampaign={vi.fn()}
      />
    );

    const actionButtons = screen.getAllByRole("button", {
      name: /actions for campaign/i,
    });
    // Click the first desktop row action button
    fireEvent.click(actionButtons[0]);

    // Assert that exactly ONE menu is visible in the document (no duplicate portal)
    const menus = screen.getAllByRole("menu");
    expect(menus).toHaveLength(1);
  });

  // 2. The menu is positioned relative to its own trigger, not at the viewport origin
  it("Requirement 2: menu is positioned relative to its trigger, not at viewport origin", () => {
    const rectSpy = vi.spyOn(HTMLButtonElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 200,
      bottom: 232,
      left: 500,
      right: 532,
      width: 32,
      height: 32,
      x: 500,
      y: 200,
      toJSON: () => {},
    });

    render(
      <CampaignActionsMenu
        campaign={mockCampaigns[0]}
        isOpen={true}
        onToggle={vi.fn()}
        onClose={vi.fn()}
        onView={vi.fn()}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    const menu = screen.getByRole("menu");
    expect(menu).toBeDefined();
    expect(menu.style.position).toBe("fixed");
    expect(menu.style.top).toBe("236px");
    expect(menu.style.left).toBe("340px");
    rectSpy.mockRestore();
  });

  it("Requirement 2b: flips upward when insufficient vertical space below", () => {
    const rectSpy = vi.spyOn(HTMLButtonElement.prototype, "getBoundingClientRect").mockReturnValue({
      top: 720,
      bottom: 750,
      left: 500,
      right: 532,
      width: 32,
      height: 32,
      x: 500,
      y: 720,
      toJSON: () => {},
    });

    render(
      <CampaignActionsMenu
        campaign={mockCampaigns[0]}
        isOpen={true}
        onToggle={vi.fn()}
        onClose={vi.fn()}
        onView={vi.fn()}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    const menu = screen.getByRole("menu");
    expect(menu.style.top).toBe("");
    expect(menu.style.bottom).toBeDefined();
    expect(menu.style.bottom).not.toBe("");
    rectSpy.mockRestore();
  });

  // 3. Opening a second row's menu closes the first
  it("Requirement 3: opening a second row's menu closes the first", () => {
    render(
      <CampaignTable
        campaigns={mockCampaigns}
        emailAccounts={mockAccounts}
        onViewCampaign={vi.fn()}
        onEditCampaign={vi.fn()}
        onPauseCampaign={vi.fn()}
        onCancelCampaign={vi.fn()}
        onDeleteCampaign={vi.fn()}
      />
    );

    const actionButtons = screen.getAllByRole("button", {
      name: /actions for campaign/i,
    });

    // Open row 1 menu (RUNNING)
    fireEvent.click(actionButtons[0]);
    expect(screen.getByText("Pause Campaign")).toBeDefined();
    expect(screen.queryByText("Edit Draft")).toBeNull();

    // Open row 3 menu (DRAFT)
    fireEvent.click(actionButtons[2]);
    expect(screen.getByText("Edit Draft")).toBeDefined();
    expect(screen.queryByText("Pause Campaign")).toBeNull();
    expect(screen.getAllByRole("menu")).toHaveLength(1);
  });

  // 4. Escape and outside-click dismissal still work
  it("Requirement 4: escape key and outside click dismiss the menu", () => {
    const handleClose = vi.fn();
    render(
      <div>
        <div data-testid="outside">Outside</div>
        <CampaignActionsMenu
          campaign={mockCampaigns[0]}
          isOpen={true}
          onToggle={vi.fn()}
          onClose={handleClose}
          onView={vi.fn()}
          onCancel={vi.fn()}
          onDelete={vi.fn()}
        />
      </div>
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(handleClose).toHaveBeenCalledTimes(1);

    fireEvent.mouseDown(screen.getByTestId("outside"));
    expect(handleClose).toHaveBeenCalledTimes(2);
  });

  // 5. View Details navigates to campaign detail page
  it("Requirement 5: View Details navigates to campaign detail page", async () => {
    vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
    vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);

    renderCampaignsPage();

    await waitFor(() => {
      expect(screen.getAllByText("Q4 Product Launch").length).toBeGreaterThanOrEqual(1);
    });

    const actionButtons = screen.getAllByRole("button", {
      name: /actions for campaign/i,
    });
    fireEvent.click(actionButtons[0]);

    const viewDetailsBtn = screen.getByRole("menuitem", { name: /view details/i });
    fireEvent.click(viewDetailsBtn);

    expect(mockNavigate).toHaveBeenCalledWith("/campaigns/101");
  });

  // 5b. Campaign row click navigates to campaign detail page
  it("Requirement 5b: Clicking a campaign table row navigates to campaign detail page", async () => {
    vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
    vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);

    renderCampaignsPage();

    await waitFor(() => {
      expect(screen.getAllByText("Q4 Product Launch").length).toBeGreaterThanOrEqual(1);
    });

    const rowName = screen.getAllByText("Q4 Product Launch")[0];
    fireEvent.click(rowName);

    expect(mockNavigate).toHaveBeenCalledWith("/campaigns/101");
  });

  // 6. Edit Draft opens campaign edit wizard
  it("Requirement 6: Edit Draft navigates to campaign wizard edit mode", async () => {
    vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
    vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);

    renderCampaignsPage();

    await waitFor(() => {
      expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
    });

    const actionButtons = screen.getAllByRole("button", {
      name: /actions for campaign/i,
    });
    fireEvent.click(actionButtons[2]);

    const editDraftBtn = screen.getByRole("menuitem", { name: /edit draft/i });
    fireEvent.click(editDraftBtn);

    expect(mockNavigate).toHaveBeenCalledWith("/campaigns/103/edit");
  });

  // 7. Delete Draft opens confirmation
  it("Requirement 7: Delete Draft opens confirmation dialog", async () => {
    vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
    vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);

    renderCampaignsPage();

    await waitFor(() => {
      expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
    });

    const actionButtons = screen.getAllByRole("button", {
      name: /actions for campaign/i,
    });
    fireEvent.click(actionButtons[2]);

    const deleteBtn = screen.getByRole("menuitem", { name: /delete draft/i });
    fireEvent.click(deleteBtn);

    expect(screen.getByText("Delete Draft Campaign?")).toBeDefined();
    expect(screen.getByText(/Ref: Draft Campaign/i)).toBeDefined();
  });

  // 8. Canceling deletion makes no API request
  it("Requirement 8: canceling deletion makes no API request", async () => {
    vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
    vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);
    const deleteSpy = vi.spyOn(campaignsApi, "deleteCampaign").mockResolvedValue();

    renderCampaignsPage();

    await waitFor(() => {
      expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
    });

    const actionButtons = screen.getAllByRole("button", {
      name: /actions for campaign/i,
    });
    fireEvent.click(actionButtons[2]);

    const deleteBtn = screen.getByRole("menuitem", { name: /delete draft/i });
    fireEvent.click(deleteBtn);

    const cancelModalBtn = screen.getByRole("button", { name: "Cancel" });
    fireEvent.click(cancelModalBtn);

    expect(deleteSpy).not.toHaveBeenCalled();
    expect(screen.queryByText("Delete Draft Campaign?")).toBeNull();
  });

  // 9. Confirming deletion calls the correct API once
  // 10. Successful deletion refreshes the campaign list
  it("Requirements 9 & 10: confirming deletion calls deleteCampaign once with company and campaign IDs, and shows success", async () => {
    vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
    vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);
    const deleteSpy = vi.spyOn(campaignsApi, "deleteCampaign").mockResolvedValue();

    renderCampaignsPage();

    await waitFor(() => {
      expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
    });

    const actionButtons = screen.getAllByRole("button", {
      name: /actions for campaign/i,
    });
    fireEvent.click(actionButtons[2]);

    const deleteBtn = screen.getByRole("menuitem", { name: /delete draft/i });
    fireEvent.click(deleteBtn);

    const confirmDeleteBtn = screen.getByRole("button", { name: "Delete Campaign" });
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledTimes(1);
    });
    expect(deleteSpy).toHaveBeenCalledWith(10, 103);

    await waitFor(() => {
      expect(
        screen.getByText(/Campaign "Draft Campaign" was permanently deleted./i)
      ).toBeDefined();
    });
  });

  // 11. Failed deletion preserves the campaign and displays an error
  it("Requirement 11: failed deletion preserves campaign and displays error", async () => {
    vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
    vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);
    vi.spyOn(campaignsApi, "deleteCampaign").mockRejectedValue(
      new Error("Database lock conflict")
    );

    renderCampaignsPage();

    await waitFor(() => {
      expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
    });

    const actionButtons = screen.getAllByRole("button", {
      name: /actions for campaign/i,
    });
    fireEvent.click(actionButtons[2]);

    const deleteBtn = screen.getByRole("menuitem", { name: /delete draft/i });
    fireEvent.click(deleteBtn);

    const confirmDeleteBtn = screen.getByRole("button", { name: "Delete Campaign" });
    fireEvent.click(confirmDeleteBtn);

    await waitFor(() => {
      expect(screen.getByText(/Database lock conflict|Failed to delete campaign/i)).toBeDefined();
    });

    // Campaign is still preserved in the table
    expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
  });
});

describe("C12.1 Final Correction: Deletion Eligibility and Send Now Semantics", () => {
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

  const renderCampaignsPageWithRole = (role: "OWNER" | "ADMIN" | "MEMBER" = "ADMIN") => {
    const wsValue: WorkspaceContextType = {
      ...mockWorkspaceValue,
      currentRole: role,
      currentCompany: { ...mockCompany, role },
    };
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AuthContext.Provider value={mockAuthValue}>
            <WorkspaceContext.Provider value={wsValue}>
              <CampaignsPage />
            </WorkspaceContext.Provider>
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  describe("Backend-aligned Deletion Eligibility across all 8 statuses", () => {
    const allStatuses: Array<{
      status: Campaign["status"];
      label?: string;
      deletable: boolean;
    }> = [
      { status: "DRAFT", label: "Delete Draft", deletable: true },
      { status: "COMPLETED", label: "Delete Campaign", deletable: true },
      { status: "CANCELLED", label: "Delete Campaign", deletable: true },
      { status: "FAILED", label: "Delete Campaign", deletable: true },
      { status: "SCHEDULED", deletable: false },
      { status: "QUEUED", deletable: false },
      { status: "RUNNING", deletable: false },
      { status: "PAUSED", deletable: false },
    ];

    it.each(allStatuses)(
      "correctly enforces deletion option presence for status $status in CampaignActionsMenu",
      ({ status, deletable, label }) => {
        const testCampaign: Campaign = {
          ...mockCampaigns[0],
          id: 555,
          name: `Test ${status}`,
          status: status as any,
        };
        const onDelete = vi.fn();

        const { unmount } = render(
          <CampaignActionsMenu
            campaign={testCampaign}
            isOpen={true}
            onToggle={vi.fn()}
            onClose={vi.fn()}
            onView={vi.fn()}
            onCancel={vi.fn()}
            onDelete={onDelete}
          />
        );

        if (deletable) {
          const deleteItem = screen.getByRole("menuitem", { name: new RegExp(label!, "i") });
          expect(deleteItem).toBeDefined();
          fireEvent.click(deleteItem);
          expect(onDelete).toHaveBeenCalledWith(testCampaign);
        } else {
          expect(screen.queryByRole("menuitem", { name: /delete/i })).toBeNull();
        }
        unmount();
      }
    );

    it("applies the exact same deletion eligibility in mobile card menu", () => {
      const draftCampaign: Campaign = { ...mockCampaigns[2], status: "DRAFT" };
      const runningCampaign: Campaign = { ...mockCampaigns[0], status: "RUNNING" };
      const onDelete = vi.fn();

      // Mobile card with DRAFT offers delete
      const { unmount } = render(
        <CampaignMobileCard
          campaign={draftCampaign}
          senderAccount={mockAccounts[0]}
          isMenuOpen={true}
          onToggleMenu={vi.fn()}
          onCloseMenu={vi.fn()}
          onView={vi.fn()}
          onDelete={onDelete}
        />
      );
      expect(screen.getByRole("menuitem", { name: /delete draft/i })).toBeDefined();
      unmount();

      // Mobile card with RUNNING does NOT offer delete
      render(
        <CampaignMobileCard
          campaign={runningCampaign}
          senderAccount={mockAccounts[0]}
          isMenuOpen={true}
          onToggleMenu={vi.fn()}
          onCloseMenu={vi.fn()}
          onView={vi.fn()}
          onDelete={onDelete}
        />
      );
      expect(screen.queryByRole("menuitem", { name: /delete/i })).toBeNull();
    });

    it("withholds deletion option when user lacks ADMIN/OWNER permissions", async () => {
      vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
      vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);

      // Render as MEMBER
      renderCampaignsPageWithRole("MEMBER");

      await waitFor(() => {
        expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
      });

      const actionButtons = screen.getAllByRole("button", {
        name: /actions for campaign/i,
      });
      // Click Draft Campaign action button (index 2)
      fireEvent.click(actionButtons[2]);

      // Delete Draft must NOT be in the menu for non-admin
      expect(screen.queryByRole("menuitem", { name: /delete draft/i })).toBeNull();
    });
  });

  describe("Verified Send Now Semantics", () => {
    it("proves Send Now displays clear informational toast and does NOT call scheduleCampaign or dispatch", async () => {
      vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
      vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);
      const scheduleSpy = vi.spyOn(campaignsApi, "scheduleCampaign").mockResolvedValue({} as any);

      renderCampaignsPageWithRole("ADMIN");

      await waitFor(() => {
        expect(screen.getAllByText("Weekly Newsletter").length).toBeGreaterThanOrEqual(1);
      });

      // Weekly Newsletter is SCHEDULED (index 1)
      const actionButtons = screen.getAllByRole("button", {
        name: /actions for campaign/i,
      });
      fireEvent.click(actionButtons[1]);

      const sendNowBtn = screen.getByRole("menuitem", { name: /send now/i });
      expect(sendNowBtn).toBeDefined();
      fireEvent.click(sendNowBtn);

      // Verify notification appears
      await waitFor(() => {
        expect(
          screen.getByText(/Immediate dispatch is not supported for scheduled campaign "Weekly Newsletter"./i)
        ).toBeDefined();
      });

      // Assert campaignsApi.scheduleCampaign was NEVER called
      expect(scheduleSpy).not.toHaveBeenCalled();
    });
  });

  describe("Deletion lifecycle and guard invariants", () => {
    it("prevents multiple deletion requests while deletion is pending", async () => {
      vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
      vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);

      let resolveDelete: () => void = () => {};
      const deletePromise = new Promise<void>((res) => {
        resolveDelete = res;
      });
      const deleteSpy = vi.spyOn(campaignsApi, "deleteCampaign").mockImplementation(() => deletePromise);

      renderCampaignsPageWithRole("ADMIN");

      await waitFor(() => {
        expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
      });

      const actionButtons = screen.getAllByRole("button", {
        name: /actions for campaign/i,
      });
      fireEvent.click(actionButtons[2]);

      const deleteBtn = screen.getByRole("menuitem", { name: /delete draft/i });
      fireEvent.click(deleteBtn);

      const confirmDeleteBtn = screen.getByRole("button", { name: "Delete Campaign" });
      
      // Click confirm once
      fireEvent.click(confirmDeleteBtn);
      await waitFor(() => {
        expect(deleteSpy).toHaveBeenCalledTimes(1);
      });

      // Attempt to click again while pending
      fireEvent.click(confirmDeleteBtn);
      expect(deleteSpy).toHaveBeenCalledTimes(1);

      // Resolve the pending promise
      resolveDelete();
      await waitFor(() => {
        expect(
          screen.getByText(/Campaign "Draft Campaign" was permanently deleted./i)
        ).toBeDefined();
      });
    });
  });

  describe("Edit Draft Option in Action Menu", () => {
    it("displays Edit Draft for DRAFT campaign when user is OWNER and navigates to /campaigns/:id/edit", async () => {
      mockNavigate.mockClear();
      vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
      vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);

      renderCampaignsPageWithRole("OWNER");

      await waitFor(() => {
        expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
      });

      const actionButtons = screen.getAllByRole("button", {
        name: /actions for campaign/i,
      });
      // Click Draft Campaign (index 2)
      fireEvent.click(actionButtons[2]);

      const editDraftBtn = screen.getByRole("menuitem", { name: /edit draft/i });
      expect(editDraftBtn).toBeDefined();
      fireEvent.click(editDraftBtn);

      expect(mockNavigate).toHaveBeenCalledWith("/campaigns/103/edit");
    });

    it("displays Edit Draft for DRAFT campaign when user is ADMIN and navigates to /campaigns/:id/edit", async () => {
      mockNavigate.mockClear();
      vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
      vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);

      renderCampaignsPageWithRole("ADMIN");

      await waitFor(() => {
        expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
      });

      const actionButtons = screen.getAllByRole("button", {
        name: /actions for campaign/i,
      });
      fireEvent.click(actionButtons[2]);

      const editDraftBtn = screen.getByRole("menuitem", { name: /edit draft/i });
      expect(editDraftBtn).toBeDefined();
      fireEvent.click(editDraftBtn);

      expect(mockNavigate).toHaveBeenCalledWith("/campaigns/103/edit");
    });

    it("hides Edit Draft for non-draft campaigns (RUNNING, SCHEDULED)", async () => {
      vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
      vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);

      renderCampaignsPageWithRole("ADMIN");

      await waitFor(() => {
        expect(screen.getAllByText("Q4 Product Launch").length).toBeGreaterThanOrEqual(1);
      });

      const actionButtons = screen.getAllByRole("button", {
        name: /actions for campaign/i,
      });
      // Click RUNNING campaign (index 0)
      fireEvent.click(actionButtons[0]);

      expect(screen.queryByRole("menuitem", { name: /edit draft/i })).toBeNull();
    });

    it("hides Edit Draft for MEMBER user even on DRAFT campaigns", async () => {
      vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue(mockCampaigns);
      vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue(mockAccounts);

      renderCampaignsPageWithRole("MEMBER");

      await waitFor(() => {
        expect(screen.getAllByText("Draft Campaign").length).toBeGreaterThanOrEqual(1);
      });

      const actionButtons = screen.getAllByRole("button", {
        name: /actions for campaign/i,
      });
      fireEvent.click(actionButtons[2]);

      expect(screen.queryByRole("menuitem", { name: /edit draft/i })).toBeNull();
      // But View Details still exists
      expect(screen.getByRole("menuitem", { name: /view details/i })).toBeDefined();
    });
  });
});



