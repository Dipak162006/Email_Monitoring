import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

import type { SuppressionEntry } from "../../../types/campaign";
import { suppressionsApi, campaignsApi, emailAccountsApi, RequestError } from "../../../services/api";
import { WorkspaceContext, type WorkspaceContextType } from "../../../context/WorkspaceContext";
import { AuthContext, type AuthContextType } from "../../../context/AuthContext";
import { CampaignsPage } from "../../../pages/CampaignsPage";

import { SuppressionReasonBadge } from "../suppressions/SuppressionReasonBadge";
import { AddSuppressionModal } from "../suppressions/AddSuppressionModal";
import { DeleteSuppressionModal } from "../suppressions/DeleteSuppressionModal";
import { SuppressionListPanel } from "../suppressions/SuppressionListPanel";

// Mock Navigate
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

import type { CompanyWithRole } from "../../../types/auth";

// Sample Test Data
const mockCompany: CompanyWithRole = {
  id: 10,
  name: "Acme Corp",
  role: "ADMIN",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

const mockWorkspaceValue: WorkspaceContextType = {
  currentCompanyId: 10,
  currentCompany: mockCompany,
  companies: [mockCompany],
  memberships: [mockCompany],
  currentRole: "ADMIN",
  isLoading: false,
  isError: false,
  error: null,
  setActiveCompanyId: vi.fn(),
  refreshWorkspaces: vi.fn().mockResolvedValue(undefined),
  refetch: vi.fn().mockResolvedValue(undefined),
};

const mockAuthValue: AuthContextType = {
  user: {
    id: 1,
    email: "admin@acme.com",
    full_name: "Admin User",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
  },
  token: "fake-jwt",
  isAuthenticated: true,
  isLoading: false,
  login: vi.fn().mockResolvedValue(undefined),
  logout: vi.fn(),
  register: vi.fn().mockResolvedValue(undefined),
  refreshUser: vi.fn().mockResolvedValue(undefined),
};

const mockSuppressions: SuppressionEntry[] = [
  {
    id: 1,
    company_id: 10,
    email: "bounced@target.com",
    reason: "BOUNCE",
    created_at: "2026-10-10T12:00:00Z",
  },
  {
    id: 2,
    company_id: 10,
    email: "unsub@partner.com",
    reason: "UNSUBSCRIBE",
    created_at: "2026-10-11T14:30:00Z",
  },
  {
    id: 3,
    company_id: 10,
    email: "blocked@competitor.com",
    reason: "MANUAL",
    created_at: "2026-10-12T09:15:00Z",
  },
  {
    id: 4,
    company_id: 10,
    email: "spammer@report.org",
    reason: "COMPLAINT",
    created_at: "2026-10-13T16:45:00Z",
  },
];

describe("SuppressionReasonBadge Component", () => {
  it("renders all suppression reason badges with correct labels and icons", () => {
    const { rerender } = render(<SuppressionReasonBadge reason="BOUNCE" />);
    expect(screen.getByTestId("suppression-reason-bounce")).toBeDefined();
    expect(screen.getByText("Bounced")).toBeDefined();

    rerender(<SuppressionReasonBadge reason="UNSUBSCRIBE" />);
    expect(screen.getByTestId("suppression-reason-unsubscribe")).toBeDefined();
    expect(screen.getByText("Unsubscribed")).toBeDefined();

    rerender(<SuppressionReasonBadge reason="MANUAL" />);
    expect(screen.getByTestId("suppression-reason-manual")).toBeDefined();
    expect(screen.getByText("Manual")).toBeDefined();

    rerender(<SuppressionReasonBadge reason="COMPLAINT" />);
    expect(screen.getByTestId("suppression-reason-complaint")).toBeDefined();
    expect(screen.getByText("Complaint")).toBeDefined();
  });
});

describe("AddSuppressionModal Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("validates empty or invalid email input", async () => {
    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(
      <AddSuppressionModal
        isOpen={true}
        companyId={10}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    const submitBtn = screen.getByRole("button", { name: /add to suppression list/i });
    expect(submitBtn.hasAttribute("disabled")).toBe(true);

    // Type invalid email
    const textarea = screen.getByLabelText(/email address/i);
    fireEvent.change(textarea, { target: { value: "invalid-not-an-email" } });
    expect(submitBtn.hasAttribute("disabled")).toBe(false);

    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
      expect(screen.getByText(/invalid email format/i)).toBeDefined();
    });
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("successfully adds a single suppressed email", async () => {
    const createSpy = vi
      .spyOn(suppressionsApi, "createSuppression")
      .mockResolvedValueOnce({
        id: 101,
        company_id: 10,
        email: "test@blocked.com",
        reason: "MANUAL",
        created_at: "2026-10-26T12:00:00Z",
      });

    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(
      <AddSuppressionModal
        isOpen={true}
        companyId={10}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    const textarea = screen.getByLabelText(/email address/i);
    fireEvent.change(textarea, { target: { value: "test@blocked.com" } });

    const submitBtn = screen.getByRole("button", { name: /add to suppression list/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(createSpy).toHaveBeenCalledWith(10, {
        email: "test@blocked.com",
        reason: "MANUAL",
      });
      expect(onSuccess).toHaveBeenCalledWith(
        expect.stringContaining("test@blocked.com")
      );
      expect(onClose).toHaveBeenCalled();
    });
  });

  it("successfully bulk adds multiple comma and newline separated emails", async () => {
    const bulkSpy = vi
      .spyOn(suppressionsApi, "bulkCreateSuppressions")
      .mockResolvedValueOnce({
        total_submitted: 2,
        inserted_count: 2,
        skipped_count: 0,
        entries: [],
        skipped_emails: [],
      });

    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(
      <AddSuppressionModal
        isOpen={true}
        companyId={10}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    const textarea = screen.getByLabelText(/email address/i);
    fireEvent.change(textarea, {
      target: { value: "first@bulk.com,\nsecond@bulk.com" },
    });

    const reasonSelect = screen.getByLabelText(/suppression reason/i);
    fireEvent.change(reasonSelect, { target: { value: "UNSUBSCRIBE" } });

    const submitBtn = screen.getByRole("button", { name: /add to suppression list/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(bulkSpy).toHaveBeenCalledWith(10, {
        emails: ["first@bulk.com", "second@bulk.com"],
        reason: "UNSUBSCRIBE",
      });
      expect(onSuccess).toHaveBeenCalledWith(
        expect.stringContaining("Successfully added 2 email(s)")
      );
    });
  });

  it("handles 409 conflict when email is already suppressed", async () => {
    vi.spyOn(suppressionsApi, "createSuppression").mockRejectedValueOnce(
      new RequestError(409, "Email already suppressed")
    );

    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(
      <AddSuppressionModal
        isOpen={true}
        companyId={10}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    const textarea = screen.getByLabelText(/email address/i);
    fireEvent.change(textarea, { target: { value: "already@exists.com" } });

    const submitBtn = screen.getByRole("button", { name: /add to suppression list/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeDefined();
      expect(
        screen.getByText(/already in the company suppression list/i)
      ).toBeDefined();
    });
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("DeleteSuppressionModal Component", () => {
  it("renders email confirmation and calls deleteSuppression on confirm", async () => {
    const deleteSpy = vi
      .spyOn(suppressionsApi, "deleteSuppression")
      .mockResolvedValueOnce();

    const onClose = vi.fn();
    const onSuccess = vi.fn();

    render(
      <DeleteSuppressionModal
        isOpen={true}
        entry={mockSuppressions[0]}
        companyId={10}
        onClose={onClose}
        onSuccess={onSuccess}
      />
    );

    expect(screen.getByText("Unsuppress Email Address?")).toBeDefined();
    expect(screen.getAllByText(mockSuppressions[0].email).length).toBeGreaterThan(0);

    const confirmBtn = screen.getByRole("button", { name: /unsuppress email/i });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(deleteSpy).toHaveBeenCalledWith(10, mockSuppressions[0].id);
      expect(onSuccess).toHaveBeenCalledWith(mockSuppressions[0].email);
      expect(onClose).toHaveBeenCalled();
    });
  });
});

describe("SuppressionListPanel Component", () => {
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

  const renderPanel = (role: "ADMIN" | "OWNER" | "MEMBER" = "ADMIN") => {
    const company: CompanyWithRole = { ...mockCompany, role };
    const wsValue: WorkspaceContextType = {
      ...mockWorkspaceValue,
      currentRole: role,
      currentCompany: company,
      companies: [company],
    };

    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AuthContext.Provider value={mockAuthValue}>
            <WorkspaceContext.Provider value={wsValue}>
              <SuppressionListPanel />
            </WorkspaceContext.Provider>
          </AuthContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  it("loads and displays suppressed emails with reason badges", async () => {
    vi.spyOn(suppressionsApi, "listSuppressions").mockResolvedValue(mockSuppressions);

    renderPanel("ADMIN");

    await waitFor(() => {
      expect(screen.getAllByText("bounced@target.com").length).toBeGreaterThan(0);
      expect(screen.getAllByText("unsub@partner.com").length).toBeGreaterThan(0);
      expect(screen.getAllByText("blocked@competitor.com").length).toBeGreaterThan(0);
      expect(screen.getAllByText("spammer@report.org").length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText("Bounced").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Unsubscribed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Manual").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Complaint").length).toBeGreaterThan(0);
  });

  it("filters suppression records by search input", async () => {
    vi.spyOn(suppressionsApi, "listSuppressions").mockResolvedValue(mockSuppressions);

    renderPanel("ADMIN");

    await waitFor(() => {
      expect(screen.getAllByText("bounced@target.com").length).toBeGreaterThan(0);
    });

    const searchInput = screen.getByLabelText(/search suppressed email/i);
    fireEvent.change(searchInput, { target: { value: "partner" } });

    await waitFor(() => {
      expect(screen.getAllByText("unsub@partner.com").length).toBeGreaterThan(0);
      expect(screen.queryByText("bounced@target.com")).toBeNull();
    });
  });

  it("filters suppression records by reason dropdown", async () => {
    vi.spyOn(suppressionsApi, "listSuppressions").mockResolvedValue(mockSuppressions);

    renderPanel("ADMIN");

    await waitFor(() => {
      expect(screen.getAllByText("bounced@target.com").length).toBeGreaterThan(0);
    });

    const reasonSelect = screen.getByLabelText(/filter by suppression reason/i);
    fireEvent.change(reasonSelect, { target: { value: "BOUNCE" } });

    await waitFor(() => {
      expect(screen.getAllByText("bounced@target.com").length).toBeGreaterThan(0);
      expect(screen.queryByText("unsub@partner.com")).toBeNull();
      expect(screen.queryByText("blocked@competitor.com")).toBeNull();
    });
  });

  it("enforces role permissions: ADMIN / OWNER can add and unsuppress, MEMBER cannot", async () => {
    vi.spyOn(suppressionsApi, "listSuppressions").mockResolvedValue(mockSuppressions);

    // 1. Render as ADMIN: can add & unsuppress
    const { unmount } = renderPanel("ADMIN");

    await waitFor(() => {
      expect(screen.getAllByText("bounced@target.com").length).toBeGreaterThan(0);
    });

    expect(
      screen.getByRole("button", { name: /add suppressed email/i })
    ).toBeDefined();

    const unsuppressButtons = screen.getAllByRole("button", { name: /unsuppress/i });
    expect(unsuppressButtons.length).toBeGreaterThan(0);

    unmount();

    // 2. Render as MEMBER: read-only without add or unsuppress buttons
    renderPanel("MEMBER");

    await waitFor(() => {
      expect(screen.getAllByText("bounced@target.com").length).toBeGreaterThan(0);
    });

    expect(
      screen.queryByRole("button", { name: /add suppressed email/i })
    ).toBeNull();
    expect(screen.queryByRole("button", { name: /unsuppress/i })).toBeNull();
  });
});

describe("CampaignsPage Navigation & Suppression List Integration", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    vi.restoreAllMocks();
    vi.spyOn(campaignsApi, "listCampaigns").mockResolvedValue([]);
    vi.spyOn(emailAccountsApi, "getAuthorizedAccounts").mockResolvedValue([]);
  });

  const renderCampaignsPage = (role: "ADMIN" | "OWNER" | "MEMBER" = "ADMIN") => {
    const company: CompanyWithRole = { ...mockCompany, role };
    const wsValue: WorkspaceContextType = {
      ...mockWorkspaceValue,
      currentRole: role,
      currentCompany: company,
      companies: [company],
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

  it("switches to the Suppression List tab and loads suppressed emails", async () => {
    const listSuppressionsSpy = vi
      .spyOn(suppressionsApi, "listSuppressions")
      .mockResolvedValue(mockSuppressions);

    renderCampaignsPage("ADMIN");

    // Initially on Campaigns tab
    expect(screen.getByRole("tab", { name: /^campaigns/i })).toBeDefined();
    const suppressionTab = screen.getByRole("tab", { name: /^suppression list/i });
    expect(suppressionTab).toBeDefined();

    // Click Suppression List tab
    fireEvent.click(suppressionTab);

    await waitFor(() => {
      expect(listSuppressionsSpy).toHaveBeenCalledWith(
        10,
        expect.objectContaining({ limit: 100, offset: 0 })
      );
      expect(screen.getByText("Workspace Suppression Protection")).toBeDefined();
      expect(screen.getAllByText("bounced@target.com").length).toBeGreaterThan(0);
      expect(screen.getAllByText("unsub@partner.com").length).toBeGreaterThan(0);
    });
  });
});
