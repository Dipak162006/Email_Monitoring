import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CampaignEngagementOverview } from "../analytics/CampaignEngagementOverview";
import { CampaignRecipientEngagementTable } from "../analytics/CampaignRecipientEngagementTable";
import { AnalyticsScopeToolbar } from "../analytics/AnalyticsScopeToolbar";
import { CampaignSequencePerformanceTable } from "../analytics/CampaignSequencePerformanceTable";
import type {
  CampaignAnalyticsResponse,
  CampaignRecipientEngagementResponse,
  CampaignStepAnalytics,
} from "../../../types/campaign";
import { campaignsApi } from "../../../services/api";

// Mock Workspace hook
vi.mock("../../../hooks/useWorkspace", () => ({
  useWorkspace: () => ({
    currentCompanyId: 42,
    currentRole: "OWNER",
  }),
}));

describe("T5.5 & T5.5.1 — Campaign Engagement Analytics Frontend", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
    vi.clearAllMocks();
  });

  const mockSteps: CampaignStepAnalytics[] = [
    {
      step_number: 1,
      subject: "Welcome Introduction",
      delay_hours: 0,
      is_active: true,
      target_tags: [],
      targeted_count: 100,
      sent_count: 80,
      unique_recipients_sent: 70,
      sending_count: 0,
      bounced_count: 3,
      failed_count: 1,
      skipped_count: 0,
      replied_count: 6,
      pending_count: 0,
      delivery_rate: 96,
      reply_rate: 8.0,
      bounce_rate: 4.0,
      raw_open_count: 45,
      unique_open_recipients: 35,
      raw_click_count: 14,
      unique_click_recipients: 7,
      open_rate: 50.0,
      click_rate: 10.0,
      click_to_open_rate: 20.0,
    },
    {
      step_number: 2,
      subject: "Quick Follow-Up",
      delay_hours: 24,
      is_active: true,
      target_tags: [],
      targeted_count: 100,
      sent_count: 10,
      unique_recipients_sent: 10,
      sending_count: 0,
      bounced_count: 2,
      failed_count: 1,
      skipped_count: 0,
      replied_count: 2,
      pending_count: 0,
      delivery_rate: 80,
      reply_rate: 20.0,
      bounce_rate: 20.0,
      raw_open_count: 10,
      unique_open_recipients: 5,
      raw_click_count: 6,
      unique_click_recipients: 4,
      open_rate: 50.0,
      click_rate: 40.0,
      click_to_open_rate: 80.0,
    },
  ];

  const mockAnalytics: CampaignAnalyticsResponse = {
    campaign_id: 101,
    campaign_name: "Summer Growth Campaign",
    campaign_status: "RUNNING",
    total_recipients: 100,
    total_steps: 2,
    total_sent_count: 85,
    unique_recipients_sent: 75,
    estimated_delivered_count: 80,
    delivered_count: 80,
    bounced_count: 5,
    failed_count: 2,
    suppressed_count: 3,
    raw_open_count: 45,
    unique_open_recipients: 30,
    open_rate: 40.0,
    raw_click_count: 18,
    unique_click_recipients: 12,
    click_rate: 16.0,
    click_to_open_rate: 40.0,
    bot_events_count: 8,
    non_bot_events_count: 50,
    unknown_events_count: 5,
    steps: mockSteps,
  };

  describe("AnalyticsScopeToolbar", () => {
    it("renders selector with All Campaign Emails and step options", () => {
      const handleSelect = vi.fn();
      render(
        <AnalyticsScopeToolbar
          steps={mockSteps}
          selectedStepNumber={null}
          onSelectStep={handleSelect}
        />
      );

      expect(screen.getByTestId("scope-select-dropdown")).toBeDefined();
      expect(screen.getByText("All Campaign Emails (Aggregate)")).toBeDefined();
      expect(screen.getByText("Step 1: Initial Outreach — Welcome Introduction")).toBeDefined();
      expect(screen.getByText("Step 2: Follow-Up #1 — Quick Follow-Up")).toBeDefined();
    });

    it("triggers onSelectStep when changing the scope selector", () => {
      const handleSelect = vi.fn();
      render(
        <AnalyticsScopeToolbar
          steps={mockSteps}
          selectedStepNumber={null}
          onSelectStep={handleSelect}
        />
      );

      fireEvent.change(screen.getByTestId("scope-select-dropdown"), { target: { value: "1" } });
      expect(handleSelect).toHaveBeenCalledWith(1);
    });

    it("displays reset button when scoped to a specific step", () => {
      const handleSelect = vi.fn();
      render(
        <AnalyticsScopeToolbar
          steps={mockSteps}
          selectedStepNumber={1}
          onSelectStep={handleSelect}
        />
      );

      expect(screen.getByTestId("reset-scope-button")).toBeDefined();
      fireEvent.click(screen.getByTestId("reset-scope-button"));
      expect(handleSelect).toHaveBeenCalledWith(null);
    });
  });

  describe("CampaignSequencePerformanceTable", () => {
    it("renders sequence steps with sent, opens, clicks, replies, bounces", () => {
      const handleSelect = vi.fn();
      render(
        <CampaignSequencePerformanceTable
          steps={mockSteps}
          selectedStepNumber={null}
          onSelectStep={handleSelect}
        />
      );

      expect(screen.getByText("Initial Outreach")).toBeDefined();
      expect(screen.getByText("Follow-Up #1")).toBeDefined();
      expect(screen.getByText("Sent (Total / Uniq)")).toBeDefined();
      expect(screen.getByText("(70 uniq)")).toBeDefined();
      expect(screen.getByTestId("sequence-row-1")).toBeDefined();
      expect(screen.getByTestId("sequence-row-2")).toBeDefined();
    });

    it("triggers onSelectStep when clicking a step row", () => {
      const handleSelect = vi.fn();
      render(
        <CampaignSequencePerformanceTable
          steps={mockSteps}
          selectedStepNumber={null}
          onSelectStep={handleSelect}
        />
      );

      fireEvent.click(screen.getByTestId("sequence-row-1"));
      expect(handleSelect).toHaveBeenCalledWith(1);
    });
  });

  describe("CampaignEngagementOverview", () => {
    it("renders loading skeleton when isLoading is true", () => {
      render(<CampaignEngagementOverview isLoading={true} />);
      expect(screen.getByTestId("engagement-overview-loading")).toBeDefined();
    });

    it("renders campaign-wide delivery & engagement metrics when scope is null", () => {
      render(<CampaignEngagementOverview analytics={mockAnalytics} selectedStepNumber={null} />);

      // Top KPI Cards (unified 7 non-redundant cards)
      expect(screen.getByTestId("metric-unique-sent").textContent).toBe("75");
      expect(screen.getByTestId("metric-top-open-rate").textContent).toBe("40.0%");
      expect(screen.getByTestId("metric-top-click-rate").textContent).toBe("16.0%");
      expect(screen.getByTestId("metric-total-sent").textContent).toBe("85");
      expect(screen.getByTestId("metric-estimated-delivered").textContent).toBe("80");
      expect(screen.getByTestId("metric-bounced").textContent).toBe("5");

      // Engagement performance
      expect(screen.getByTestId("metric-unique-opens").textContent).toBe("30");
      expect(screen.getByTestId("metric-raw-opens").textContent).toBe("45");
      expect(screen.getByTestId("metric-unique-clicks").textContent).toBe("12");
      expect(screen.getByTestId("metric-raw-clicks").textContent).toBe("18");
      expect(screen.getByTestId("metric-ctor").textContent).toContain("40.0% CTOR");
    });

    it("renders step-level metrics and scope banner when scoped to Step 1", () => {
      render(<CampaignEngagementOverview analytics={mockAnalytics} selectedStepNumber={1} />);

      // Scope banner
      expect(screen.getByTestId("step-scope-banner")).toBeDefined();
      expect(screen.getByText(/Scoped to Step 1: Initial Outreach/i)).toBeDefined();

      // Step 1 KPIs using unique_recipients_sent (70) and total sent (80)
      expect(screen.getByTestId("metric-unique-sent").textContent).toBe("70");
      expect(screen.getByTestId("metric-top-open-rate").textContent).toBe("50.0%");
      expect(screen.getByTestId("metric-top-click-rate").textContent).toBe("10.0%");
      expect(screen.getByTestId("metric-total-sent").textContent).toBe("80");
      expect(screen.getByTestId("metric-bounced").textContent).toBe("3");

      // Step 1 Engagement
      expect(screen.getByTestId("metric-unique-opens").textContent).toBe("35");
      expect(screen.getByTestId("metric-raw-opens").textContent).toBe("45");
      expect(screen.getByTestId("metric-unique-clicks").textContent).toBe("7");
      expect(screen.getByTestId("metric-raw-clicks").textContent).toBe("14");
      expect(screen.getByTestId("metric-ctor").textContent).toBe("20.0% CTOR");
    });

    it("renders conservative classification breakdown without calling them 'Human'", () => {
      render(<CampaignEngagementOverview analytics={mockAnalytics} />);

      expect(screen.getByText("Non-Bot-Classified")).toBeDefined();
      expect(screen.queryByText(/Human opens/i)).toBeNull();
      expect(screen.queryByText(/Human clicks/i)).toBeNull();

      expect(screen.getByTestId("metric-non-bot-events").textContent).toBe("50");
      expect(screen.getByTestId("metric-bot-events").textContent).toBe("8");
      expect(screen.getByTestId("metric-unknown-events").textContent).toBe("5");

      // Verify classification disclaimer
      expect(screen.getByText(/Non-bot classification confirms no known automated security scanner signatures/i)).toBeDefined();
    });

    it("triggers onSelectEventType callback when clicking engagement cards", () => {
      const handleSelect = vi.fn();
      render(<CampaignEngagementOverview analytics={mockAnalytics} onSelectEventType={handleSelect} />);

      fireEvent.click(screen.getByTestId("card-opens"));
      expect(handleSelect).toHaveBeenCalledWith("OPEN");

      fireEvent.click(screen.getByTestId("card-clicks"));
      expect(handleSelect).toHaveBeenCalledWith("CLICK");
    });
  });

  describe("CampaignRecipientEngagementTable", () => {
    const mockDrilldownOpenResponse: CampaignRecipientEngagementResponse = {
      campaign_id: 101,
      event_type: "OPEN",
      total: 2,
      limit: 10,
      offset: 0,
      items: [
        {
          recipient_id: 1,
          masked_email: "a***e@example.com",
          first_event_at: "2026-11-20T08:00:00Z",
          last_event_at: "2026-11-20T08:30:00Z",
          total_events_count: 3,
          bot_events_count: 0,
          non_bot_events_count: 3,
          unknown_events_count: 0,
        },
        {
          recipient_id: 2,
          masked_email: "b***b@corp.org",
          first_event_at: "2026-11-20T08:15:00Z",
          last_event_at: "2026-11-20T08:15:00Z",
          total_events_count: 1,
          bot_events_count: 1,
          non_bot_events_count: 0,
          unknown_events_count: 0,
        },
      ],
    };

    it("renders recipient table with masked emails, counts, and classification badges", async () => {
      vi.spyOn(campaignsApi, "getCampaignRecipientEngagement").mockResolvedValue(mockDrilldownOpenResponse);

      render(
        <QueryClientProvider client={queryClient}>
          <CampaignRecipientEngagementTable campaignId={101} initialEventType="OPEN" />
        </QueryClientProvider>
      );

      // Loading state check
      expect(screen.getByTestId("drilldown-loading")).toBeDefined();

      // Wait for table to render
      await waitFor(() => {
        expect(screen.getByTestId("drilldown-table")).toBeDefined();
      });

      // Masked emails
      expect(screen.getByText("a***e@example.com")).toBeDefined();
      expect(screen.getByText("b***b@corp.org")).toBeDefined();

      // Classification breakdown
      expect(screen.getByTestId("drilldown-row-1")).toBeDefined();
      expect(screen.getByTestId("drilldown-row-2")).toBeDefined();

      // Verify pagination text
      expect(screen.getByText(/Showing/i)).toBeDefined();
      expect(screen.getByText(/Page 1 of 1/i)).toBeDefined();
    });

    it("passes step_number to API when stepNumber prop is provided", async () => {
      const spy = vi.spyOn(campaignsApi, "getCampaignRecipientEngagement").mockResolvedValue(mockDrilldownOpenResponse);

      render(
        <QueryClientProvider client={queryClient}>
          <CampaignRecipientEngagementTable campaignId={101} stepNumber={1} eventType="OPEN" />
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId("drilldown-table")).toBeDefined();
      });

      expect(spy).toHaveBeenCalledWith(42, 101, {
        event_type: "OPEN",
        limit: 10,
        offset: 0,
        step_number: 1,
      });

      // Scope badge visible
      expect(screen.getByTestId("drilldown-scope-indicator")).toBeDefined();
      expect(screen.getByText(/Step 1 Scoped/i)).toBeDefined();
    });

    it("switches event type when toggling between Opened and Clicked recipients", async () => {
      const spy = vi.spyOn(campaignsApi, "getCampaignRecipientEngagement").mockResolvedValue(mockDrilldownOpenResponse);

      render(
        <QueryClientProvider client={queryClient}>
          <CampaignRecipientEngagementTable campaignId={101} initialEventType="OPEN" />
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId("drilldown-table")).toBeDefined();
      });

      expect(spy).toHaveBeenCalledWith(42, 101, {
        event_type: "OPEN",
        limit: 10,
        offset: 0,
        step_number: null,
      });

      // Click on Clicked Recipients tab
      fireEvent.click(screen.getByTestId("tab-clicks"));

      await waitFor(() => {
        expect(spy).toHaveBeenCalledWith(42, 101, {
          event_type: "CLICK",
          limit: 10,
          offset: 0,
          step_number: null,
        });
      });
    });

    it("renders empty state when no recipients match the query", async () => {
      vi.spyOn(campaignsApi, "getCampaignRecipientEngagement").mockResolvedValue({
        campaign_id: 101,
        event_type: "OPEN",
        total: 0,
        limit: 10,
        offset: 0,
        items: [],
      });

      render(
        <QueryClientProvider client={queryClient}>
          <CampaignRecipientEngagementTable campaignId={101} initialEventType="OPEN" />
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByTestId("drilldown-empty")).toBeDefined();
      });
      expect(screen.getByText(/No opened recipients recorded/i)).toBeDefined();
    });
  });
});
