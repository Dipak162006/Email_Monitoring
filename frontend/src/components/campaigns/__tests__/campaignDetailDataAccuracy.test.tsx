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

const mockCampaignWithDetailedSequence: CampaignDetail = {
  id: 77,
  company_id: 10,
  email_account_id: 5,
  name: "Product Launch 2026",
  subject: "Exclusive Preview: Enterprise AI Suite",
  body_text: "Welcome to our exclusive product preview for enterprise teams.",
  body_html: "<p>Welcome to our exclusive product preview for enterprise teams.</p>",
  status: "RUNNING",
  scheduled_at: "2026-11-15T15:00:00Z",
  started_at: "2026-11-01T09:00:00Z",
  completed_at: null,
  recipient_count: 500,
  pending_count: 350,
  sent_count: 120,
  bounced_count: 20,
  failed_count: 10,
  suppressed_count: 0,
  replied_count: 25,
  email_account_name: "Sarah Connor",
  email_account_address: "s.connor@acme.corp",
  created_at: "2026-10-25T10:00:00Z",
  updated_at: "2026-10-26T14:30:00Z",
  sending_window: {
    enabled: true,
    start_time: "09:00",
    end_time: "17:00",
    timezone: "America/New_York",
    days: [1, 2, 3, 4, 5],
  },
  // Steps intentionally ordered out of sequence (Step 3 before Step 2)
  // Step 3 is marked is_active: false to test that it is preserved and flagged as Inactive
  steps: [
    {
      id: 201,
      campaign_id: 77,
      step_number: 1,
      subject: "Exclusive Preview: Enterprise AI Suite",
      body_text: "Welcome to our exclusive product preview for enterprise teams.",
      body_html: "<p>Welcome to our exclusive product preview for enterprise teams.</p>",
      delay_hours: 0,
      is_active: true,
      created_at: "2026-10-25T10:00:00Z",
      updated_at: "2026-10-25T10:00:00Z",
    },
    {
      id: 203,
      campaign_id: 77,
      step_number: 3,
      subject: "Final check-in before launch closes",
      body_text: "This is our final reminder regarding enterprise suite access.",
      body_html: "<p>This is our final reminder regarding enterprise suite access.</p>",
      delay_hours: 72,
      is_active: false,
      created_at: "2026-10-25T10:00:00Z",
      updated_at: "2026-10-25T10:00:00Z",
    },
    {
      id: 202,
      campaign_id: 77,
      step_number: 2,
      subject: "Quick follow-up on our preview demo",
      body_text: "Did you get a chance to review the enterprise suite preview?",
      body_html: "<p>Did you get a chance to review the enterprise suite preview?</p>",
      delay_hours: 24,
      is_active: true,
      created_at: "2026-10-25T10:00:00Z",
      updated_at: "2026-10-25T10:00:00Z",
    },
  ],
};

describe("Campaign Detail Data Accuracy & Mapping Verification", () => {
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

  const renderDetailPage = (initialRoute = "/campaigns/77") => {
    return render(
      <QueryClientProvider client={queryClient}>
        <WorkspaceContext.Provider value={createMockWorkspace()}>
          <MemoryRouter initialEntries={[initialRoute]}>
            <Routes>
              <Route path="/campaigns/:campaignId" element={<CampaignDetailPage />} />
            </Routes>
          </MemoryRouter>
        </WorkspaceContext.Provider>
      </QueryClientProvider>
    );
  };

  it("accurately renders Step 1 and follow-up steps with persisted content, order, delays, and active status", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockCampaignWithDetailedSequence);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Product Launch 2026" })).toBeDefined();
    });

    // 1. Step 1 displays persisted subject and content excerpt (NOT a hardcoded sentence)
    expect(screen.getAllByText("Exclusive Preview: Enterprise AI Suite").length).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText("Welcome to our exclusive product preview for enterprise teams.").length
    ).toBeGreaterThanOrEqual(2);

    // 2. Step 1 has Active status
    const step1Status = screen.getByTestId("step-1-status");
    expect(step1Status.textContent).toBe("Active");

    // 3. Follow-up steps are sorted by step_number ascending (Step 2 before Step 3)
    const stepCards = screen.getAllByText(/Follow-Up #/i);
    expect(stepCards[0].textContent).toContain("Follow-Up #1");
    expect(stepCards[1].textContent).toContain("Follow-Up #2");

    // Step 2 has 24h delay (1 day) and is Active
    expect(screen.getByText(/Waits 1 day if no reply/i)).toBeDefined();
    const step2Status = screen.getByTestId("step-2-status");
    expect(step2Status.textContent).toBe("Active");
    expect(screen.getByText(/Quick follow-up on our preview demo/i)).toBeDefined();

    // Step 3 has 72h delay (3 days) and is Inactive (NOT filtered out)
    expect(screen.getByText(/Waits 3 days if no reply/i)).toBeDefined();
    const step3Status = screen.getByTestId("step-3-status");
    expect(step3Status.textContent).toBe("Inactive");
    expect(screen.getByText(/Final check-in before launch closes/i)).toBeDefined();
    expect(
      screen.getByText("This is our final reminder regarding enterprise suite access.")
    ).toBeDefined();
  });

  it("accurately renders sending window with timezone and schedule information across tabs", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockCampaignWithDetailedSequence);

    renderDetailPage("/campaigns/77?tab=overview");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Product Launch 2026" })).toBeDefined();
    });

    // Overview Tab: Sending Window includes start, end and timezone
    const windowEl = screen.getByTestId("detail-sending-window");
    expect(windowEl.textContent).toContain("09:00 - 17:00 (America/New_York)");

    // Overview Tab: Dedicated Timezone field renders timezone accurately
    const tzEl = screen.getByTestId("detail-timezone");
    expect(tzEl.textContent).toBe("America/New_York");

    // Switch to Sequence Tab
    const sequenceTab = screen.getByRole("tab", { name: /email sequence/i });
    fireEvent.click(sequenceTab);

    // Sequence Tab: Window is NOT hardcoded to "Scheduled"; displays actual window with timezone
    const seqWindowEl = screen.getByTestId("sequence-sending-window");
    expect(seqWindowEl.textContent).toBe("Window: 09:00 - 17:00 (America/New_York)");
  });

  it("Step Performance Table reflects individual step active/inactive status without overriding with campaign status", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockCampaignWithDetailedSequence);

    renderDetailPage("/campaigns/77?tab=analytics");

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Product Launch 2026" })).toBeDefined();
    });

    // Step Performance Table renders all 3 steps
    const rows = screen.getAllByRole("row");
    // Row 0 is the table header
    expect(rows.length).toBeGreaterThanOrEqual(4);

    // Step 2 is active -> displays Active
    // Step 3 is inactive -> displays Inactive (not the campaign's "RUNNING" status)
    expect(screen.getAllByText("Active").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Inactive")).toBeDefined();
  });

  it("activeStepItem preview does not synthesize phantom 24h delay steps when switching steps", async () => {
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockCampaignWithDetailedSequence);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Product Launch 2026" })).toBeDefined();
    });

    // Initially Step 1 is selected in Email Preview: displays Step 1 subject and body
    expect(screen.getAllByText("Exclusive Preview: Enterprise AI Suite").length).toBeGreaterThanOrEqual(1);

    // Switch to Follow-Up #1 (Step 2)
    const step2Btn = screen.getByRole("button", { name: "Follow-Up #1" });
    fireEvent.click(step2Btn);

    // Subject in preview updates to Step 2 persisted subject
    expect(screen.getByText("Quick follow-up on our preview demo")).toBeDefined();

    // Switch to Follow-Up #2 (Step 3)
    const step3Btn = screen.getByRole("button", { name: "Follow-Up #2" });
    fireEvent.click(step3Btn);

    // Subject in preview updates to Step 3 persisted subject (does not synthesize "Re: Campaign")
    expect(screen.getByText("Final check-in before launch closes")).toBeDefined();
  });

  it("displays accurate live pacing and started timing for RUNNING campaigns without stale scheduled labels", async () => {
    const runningCampaign: CampaignDetail = {
      ...mockCampaignWithDetailedSequence,
      status: "RUNNING",
      scheduled_at: "2026-11-02T12:36:00Z",
      started_at: "2026-11-02T12:36:00Z",
      next_send_at: "2026-11-02T12:46:01Z",
      send_interval_seconds: 300,
    };
    vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(runningCampaign);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Product Launch 2026" })).toBeDefined();
    });

    // 1. Header shows Started timestamp and NOT Scheduled
    expect(screen.queryByText(/^Scheduled:/)).toBeNull();
    expect(screen.getByText(/^Started:/)).toBeDefined();

    // 2. Card 2 Schedule & Timing shows Live Dispatch lifecycle
    expect(screen.getByText("Live Dispatch")).toBeDefined();
    expect(screen.getByText("Live Dispatch In Progress")).toBeDefined();
    expect(screen.getByText(/Started /)).toBeDefined();
    expect(screen.getByText("Next Recipient")).toBeDefined();
  });
});
