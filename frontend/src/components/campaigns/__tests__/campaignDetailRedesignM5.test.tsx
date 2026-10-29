import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CampaignDetailPage } from "../../../pages/CampaignDetailPage";
import { WorkspaceContext } from "../../../context/WorkspaceContext";
import { campaignsApi } from "../../../services/api";
import type { CampaignDetail } from "../../../types/campaign";
import type { CompanyWithRole } from "../../../types/auth";
import type { WorkspaceContextType } from "../../../context/WorkspaceContext";

const mockAdminCompany: CompanyWithRole = {
  id: 10,
  name: "Acme Corp",
  role: "ADMIN",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
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

const mockCampaignWithSequence: CampaignDetail = {
  id: 3,
  company_id: 10,
  email_account_id: 5,
  name: "Cmapign_test",
  subject: "dipakodhavani@gmail.com",
  body_text: "Discover Our Newest Product! Upgrade your daily routine with our newly released item.",
  body_html: "<h2>Discover Our Newest Product!</h2><p>Upgrade your daily routine with our newly released item.</p>",
  status: "DRAFT",
  scheduled_at: null,
  started_at: null,
  completed_at: null,
  recipient_count: 1,
  pending_count: 1,
  sent_count: 0,
  bounced_count: 0,
  failed_count: 0,
  suppressed_count: 0,
  replied_count: 0,
  email_account_name: "Odhavani Dipak",
  email_account_address: "odhavanidipak@gmail.com",
  created_at: "2026-10-28T13:01:00Z",
  updated_at: "2026-10-29T13:13:00Z",
  steps: [
    {
      id: 101,
      campaign_id: 3,
      step_number: 1,
      subject: "dipakodhavani@gmail.com",
      body_text: "Discover Our Newest Product! Upgrade your daily routine.",
      body_html: "<h2>Discover Our Newest Product!</h2>",
      delay_hours: 0,
      is_active: true,
      created_at: "2026-10-28T13:01:00Z",
      updated_at: "2026-10-28T13:01:00Z",
    },
    {
      id: 102,
      campaign_id: 3,
      step_number: 2,
      subject: "Re: Campaign 1",
      body_text: "Hello {{first_name}}, Discover Our Newest Product!",
      body_html: "<p>Hello {{first_name}}, Discover Our Newest Product!</p>",
      delay_hours: 1,
      is_active: true,
      created_at: "2026-10-28T13:01:00Z",
      updated_at: "2026-10-28T13:01:00Z",
    },
  ],
  followup_steps: [
    {
      id: 102,
      campaign_id: 3,
      step_number: 2,
      delay_hours: 1,
      subject: "Re: Campaign 1",
      body_text: "Hello {{first_name}}, Discover Our Newest Product!",
      body_html: "<p>Hello {{first_name}}, Discover Our Newest Product!</p>",
      is_active: true,
      created_at: "2026-10-28T13:01:00Z",
      updated_at: "2026-10-28T13:01:00Z",
    },
  ],
};

describe("PulseMail — Campaign Detail Page UI/UX Redesign (Master Verification)", () => {
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

  const renderPage = (initialRoute = "/campaigns/3") => {
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialRoute]}>
          <WorkspaceContext.Provider value={createMockWorkspace(mockAdminCompany)}>
            <Routes>
              <Route path="/campaigns/:campaignId" element={<CampaignDetailPage />} />
            </Routes>
          </WorkspaceContext.Provider>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  it("1. Renders the modern compact header with metadata and 3 primary tabs", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockCampaignWithSequence);
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Cmapign_test" })).toBeDefined();
    });

    // Badges & metadata
    expect(screen.getByText("DRAFT")).toBeDefined();
    expect(screen.getByText("1 recipient")).toBeDefined();
    expect(screen.getByText(/ID: #3/i)).toBeDefined();

    // Primary action buttons
    expect(screen.getByRole("link", { name: /edit draft/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /schedule/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /launch now/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /more/i })).toBeDefined();

    // The exactly 3 navigation tabs
    const overviewTab = screen.getByRole("tab", { name: /overview/i });
    const sequenceTab = screen.getByRole("tab", { name: /email sequence/i });
    const analyticsTab = screen.getByRole("tab", { name: /analytics/i });

    expect(overviewTab).toBeDefined();
    expect(sequenceTab).toBeDefined();
    expect(analyticsTab).toBeDefined();
    expect(overviewTab.getAttribute("aria-selected")).toBe("true");
  });

  it("2. Overview Tab renders 4 summary cards, connected timeline, preview box, and funnels", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockCampaignWithSequence);
    renderPage("/campaigns/3?tab=overview");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Cmapign_test" })).toBeDefined();
    });

    // 4 Summary cards
    expect(screen.getByText("Sender Identity")).toBeDefined();
    expect(screen.getByText("odhavanidipak@gmail.com")).toBeDefined();
    expect(screen.getByText("Schedule & Timing")).toBeDefined();
    expect(screen.getByText("Target Audience")).toBeDefined();
    expect(screen.getByText(/Quick Stats/i)).toBeDefined();

    // Bottom sections
    expect(screen.getByText("Performance Overview")).toBeDefined();
    expect(screen.getByText("Step-Level Analytics Funnel")).toBeDefined();
    expect(screen.getByRole("button", { name: /view detailed analytics/i })).toBeDefined();
  });

  it("3. Email Sequence Tab allows switching steps to update the preview frame", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockCampaignWithSequence);
    renderPage("/campaigns/3?tab=sequence");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Cmapign_test" })).toBeDefined();
    });

    // In sequence tab: Initial outreach is active by default
    expect(screen.getByRole("tab", { name: /email sequence/i }).getAttribute("aria-selected")).toBe("true");

    // Click Follow-up #1 pill switcher
    const followupBtn = screen.getByRole("button", { name: /follow-up #1/i });
    fireEvent.click(followupBtn);

    // Subject updates to Follow-Up #1 subject
    await waitFor(() => {
      expect(screen.getAllByText("Re: Campaign 1").length).toBeGreaterThanOrEqual(1);
    });
  });

  it("4. Analytics Tab renders 5 KPI tiles, SVG Delivery Trend, SVG Donut, and Step Performance table", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockCampaignWithSequence);
    renderPage("/campaigns/3?tab=analytics");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Cmapign_test" })).toBeDefined();
    });

    expect(screen.getByRole("tab", { name: /analytics/i }).getAttribute("aria-selected")).toBe("true");

    // 5 KPI tiles
    expect(screen.getByText("Total Recipients")).toBeDefined();
    expect(screen.getAllByText("Sent").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Replies").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Bounced").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Failed").length).toBeGreaterThanOrEqual(1);

    // Charts & Tables
    expect(screen.getByText("Delivery Trend")).toBeDefined();
    expect(screen.getByText("No time-series dispatch trend recorded")).toBeDefined();
    expect(screen.getByText("Email Status Distribution")).toBeDefined();
    expect(screen.getByText("Step Performance")).toBeDefined();
    expect(screen.getByText("Recipient Engagement")).toBeDefined();
    expect(screen.getByText("Top Performing Insights")).toBeDefined();

    // Verify uninstrumented engagement metrics are honestly labeled as Not Tracked and never show 0%
    expect(screen.getAllByText("Not Tracked").length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText("Opened 0%")).toBeNull();
    expect(screen.queryByText("Clicked 0%")).toBeNull();
    expect(screen.queryByText("Unsubscribed 0%")).toBeNull();
  });

  it("5. Navigating via 'View Detailed Analytics ->' switches tab to Analytics", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockCampaignWithSequence);
    renderPage("/campaigns/3?tab=overview");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Cmapign_test" })).toBeDefined();
    });

    const viewAnalyticsBtn = screen.getByRole("button", { name: /view detailed analytics/i });
    fireEvent.click(viewAnalyticsBtn);

    await waitFor(() => {
      expect(screen.getByRole("tab", { name: /analytics/i }).getAttribute("aria-selected")).toBe("true");
      expect(screen.getByText("Delivery Trend")).toBeDefined();
    });
  });
});
