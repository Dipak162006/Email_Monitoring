import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CampaignStepAnalyticsFunnel } from "../CampaignStepAnalyticsFunnel";
import type { CampaignAnalyticsResponse } from "../../../types/campaign";

describe("CampaignStepAnalyticsFunnel Component (M7)", () => {
  const mockAnalytics: CampaignAnalyticsResponse = {
    campaign_id: 101,
    campaign_name: "Q4 Outreach Campaign",
    campaign_status: "RUNNING",
    total_recipients: 50,
    total_steps: 2,
    omitted_metrics_notice: "Open and click tracking metrics are omitted because the system does not record tracking pixels or link wraps.",
    steps: [
      {
        step_id: 1,
        step_number: 1,
        subject: "Welcome to Our Platform",
        delay_hours: 0,
        target_tags: [],
        targeted_count: 50,
        sent_count: 45,
        sending_count: 0,
        bounced_count: 2,
        failed_count: 1,
        skipped_count: 0,
        replied_count: 9,
        pending_count: 2,
        delivery_rate: 90.0,
        reply_rate: 20.0,
        bounce_rate: 4.4,
      },
      {
        step_id: 2,
        step_number: 2,
        subject: "Exclusive Offer for VIPs",
        delay_hours: 48,
        target_tags: ["vip"],
        targeted_count: 15,
        sent_count: 12,
        sending_count: 0,
        bounced_count: 0,
        failed_count: 0,
        skipped_count: 1,
        replied_count: 6,
        pending_count: 2,
        delivery_rate: 80.0,
        reply_rate: 50.0,
        bounce_rate: 0.0,
      },
    ],
  };

  it("renders loading skeleton when isLoading is true", () => {
    render(<CampaignStepAnalyticsFunnel isLoading={true} />);
    expect(screen.getByTestId("step-analytics-loading")).toBeDefined();
  });

  it("renders empty state notice when analytics has no steps", () => {
    render(
      <CampaignStepAnalyticsFunnel
        analytics={{
          campaign_id: 101,
          campaign_name: "Empty",
          campaign_status: "DRAFT",
          total_recipients: 0,
          total_steps: 0,
          steps: [],
        }}
      />
    );
    expect(screen.getByTestId("step-analytics-empty")).toBeDefined();
    expect(screen.getByText("No Step Analytics Available")).toBeDefined();
  });

  it("renders omitted metrics notice explaining absence of open/click tracking", () => {
    render(<CampaignStepAnalyticsFunnel analytics={mockAnalytics} />);
    expect(screen.getByTestId("omitted-metrics-notice")).toBeDefined();
    expect(
      screen.getByText("Open & click tracking omitted (no tracking pixels used)")
    ).toBeDefined();
  });

  it("renders step 1 and step 2 funnel cards with rates and metrics", () => {
    render(<CampaignStepAnalyticsFunnel analytics={mockAnalytics} />);

    // Check Step 1
    expect(screen.getByTestId("step-funnel-card-1")).toBeDefined();
    expect(screen.getByText("Initial Dispatch")).toBeDefined();
    expect(screen.getByText("All Recipients")).toBeDefined();
    expect(screen.getByTestId("delivery-rate-1").textContent).toContain("90%");
    expect(screen.getByTestId("reply-rate-1").textContent).toContain("20%");
    expect(screen.getByTestId("bounce-rate-1").textContent).toContain("4.4%");

    expect(screen.getByTestId("metric-targeted-1").textContent).toContain("50");
    expect(screen.getByTestId("metric-sent-1").textContent).toContain("45");
    expect(screen.getByTestId("metric-replied-1").textContent).toContain("9");
    expect(screen.getByTestId("metric-pending-1").textContent).toContain("2");
    expect(screen.getByTestId("metric-bounced-1").textContent).toContain("2");

    // Check Step 2
    expect(screen.getByTestId("step-funnel-card-2")).toBeDefined();
    expect(screen.getByText("Follow-Up (+48h delay)")).toBeDefined();
    expect(screen.getByText("vip")).toBeDefined();
    expect(screen.getByTestId("delivery-rate-2").textContent).toContain("80%");
    expect(screen.getByTestId("reply-rate-2").textContent).toContain("50%");
    expect(screen.getByTestId("bounce-rate-2").textContent).toContain("0%");

    expect(screen.getByTestId("metric-targeted-2").textContent).toContain("15");
    expect(screen.getByTestId("metric-sent-2").textContent).toContain("12");
    expect(screen.getByTestId("metric-replied-2").textContent).toContain("6");
    expect(screen.getByTestId("metric-pending-2").textContent).toContain("2");
    expect(screen.getByTestId("metric-skipped-2").textContent).toContain("1");
  });
});
