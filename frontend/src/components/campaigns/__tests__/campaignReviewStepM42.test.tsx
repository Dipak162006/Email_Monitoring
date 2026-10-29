import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CampaignReviewStep } from "../CampaignReviewStep";
import type { AuthorizedEmailAccount } from "../../../types/emails";
import type { CampaignStepWritePayload } from "../../../types/campaign";

const mockSender: AuthorizedEmailAccount = {
  id: 10,
  company_id: 1,
  name: "Dipak Odhavani",
  email_address: "dipakodhavani@gmail.com",
  provider: "GOOGLE",
  is_active: true,
  is_sync_enabled: true,
};

describe("M4.2 — PulseMail Campaign Review Page Full-Page UI/UX", () => {
  const followupSteps: CampaignStepWritePayload[] = [
    {
      step_number: 2,
      delay_hours: 1,
      subject: "Re: Campaign 1",
      body_html: "<p>Follow-up 1 body content with <strong>bold text</strong>.</p>",
      target_tags: [],
    },
    {
      step_number: 3,
      delay_hours: 48,
      subject: "Second Check-in",
      body_html: "<p>Follow-up 2 body with custom offer.</p>",
      target_tags: ["vip-leads"],
    },
    {
      step_number: 4,
      delay_hours: 120,
      subject: "Final Breakup Email",
      body_text: "Final attempt plain text body.",
      target_tags: ["cold"],
    },
  ];

  it("1. Renders top row summary cards for Campaign Details and Sender Account matching reference layout", () => {
    const onEdit = vi.fn();

    render(
      <CampaignReviewStep
        name="Cmapign_test"
        subject="dipakodhavani@gmail.com"
        bodyHtml="<h2>Discover Our Newest Product!</h2>"
        selectedSender={mockSender}
        sendIntervalSeconds={0}
        sendingWindow={null}
        followupSteps={followupSteps}
        onEditStep={onEdit}
      />
    );

    // Card 1: Campaign Details
    expect(screen.getByText("Campaign Details")).toBeDefined();
    expect(screen.getByText("Cmapign_test")).toBeDefined();
    expect(screen.getByText("No intentional delay")).toBeDefined();
    expect(screen.getByText("Unrestricted (24/7)")).toBeDefined();

    // Card 2: Sender Account
    expect(screen.getByText("Sender Account")).toBeDefined();
    expect(screen.getByText("Dipak Odhavani")).toBeDefined();
    expect(screen.getByText("Active")).toBeDefined();
    expect(screen.getByText("Google")).toBeDefined();

    // Check Edit buttons
    const editButtons = screen.getAllByRole("button", { name: /edit/i });
    expect(editButtons.length).toBe(3);

    fireEvent.click(editButtons[0]);
    expect(onEdit).toHaveBeenCalledWith(1);

    fireEvent.click(editButtons[1]);
    expect(onEdit).toHaveBeenCalledWith(2);

    fireEvent.click(editButtons[2]);
    expect(onEdit).toHaveBeenCalledWith(3);
  });

  it("2. Renders two-column Email Content layout with Step 1 on the left and Follow-up Sequence on the right", () => {
    render(
      <CampaignReviewStep
        name="Outreach"
        subject="Product Demo"
        bodyHtml="<div>Welcome email</div>"
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onEditStep={vi.fn()}
      />
    );

    expect(screen.getByText("Email Content")).toBeDefined();
    expect(screen.getByText("4 Steps in Sequence")).toBeDefined();

    // Left Panel: Initial Outreach
    expect(screen.getByText("Step 1: Initial Outreach")).toBeDefined();
    expect(screen.getByText("Immediate")).toBeDefined();
    expect(document.getElementById("review-content-snippet")).not.toBeNull();

    // Right Panel: Follow-up Sequence
    expect(screen.getByText("Follow-Up Sequence")).toBeDefined();
    expect(screen.getByText("Select a step to view its email content.")).toBeDefined();

    // Tabs rendered
    expect(screen.getByRole("button", { name: "Follow-up 1" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Follow-up 2" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Follow-up 3" })).toBeDefined();
  });

  it("3. Selecting different follow-up tabs switches active step metadata and email preview content", () => {
    render(
      <CampaignReviewStep
        name="Outreach"
        subject="Product Demo"
        bodyHtml="<div>Welcome email</div>"
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onEditStep={vi.fn()}
      />
    );

    // Step 1 selected by default (Follow-Up #1 / Step 2)
    expect(screen.getByText("Follow-Up #1 (Step 2)")).toBeDefined();
    expect(screen.getByText(/Waits 1 hour if no reply/i)).toBeDefined();
    expect(screen.getByText('Subject: "Re: Campaign 1"')).toBeDefined();
    expect(screen.getByText("bold text")).toBeDefined();

    // Click Tab 2
    fireEvent.click(screen.getByRole("button", { name: "Follow-up 2" }));

    // Now Step 3 should be displayed
    expect(screen.getByText("Follow-Up #2 (Step 3)")).toBeDefined();
    expect(screen.getByText(/Waits 2 days if no reply/i)).toBeDefined();
    expect(screen.getByText('Subject: "Second Check-in"')).toBeDefined();
    expect(screen.getByText("#vip-leads")).toBeDefined();
    expect(screen.getByText("Follow-up 2 body with custom offer.")).toBeDefined();

    // Click Tab 3 (plain text body)
    fireEvent.click(screen.getByRole("button", { name: "Follow-up 3" }));

    expect(screen.getByText("Follow-Up #3 (Step 4)")).toBeDefined();
    expect(screen.getByText(/Waits 5 days if no reply/i)).toBeDefined();
    expect(screen.getByText('Subject: "Final Breakup Email"')).toBeDefined();
    expect(screen.getByText("#cold")).toBeDefined();
    expect(screen.getByText("Final attempt plain text body.")).toBeDefined();

    // Switch back to Tab 1
    fireEvent.click(screen.getByRole("button", { name: "Follow-up 1" }));
    expect(screen.getByText("Follow-Up #1 (Step 2)")).toBeDefined();
    expect(screen.getByText("bold text")).toBeDefined();
  });

  it("4. Displays a friendly empty state when no follow-up steps are configured", () => {
    render(
      <CampaignReviewStep
        name="Single Outreach"
        subject="Single Email"
        bodyHtml="<p>Just one email</p>"
        selectedSender={mockSender}
        followupSteps={[]}
        onEditStep={vi.fn()}
      />
    );

    expect(screen.getByText("Single Outreach Step")).toBeDefined();
    expect(screen.getByText("No follow-up steps configured for this campaign.")).toBeDefined();
  });

  it("5. Renders compact full-width Recipients section with next-step notice", () => {
    render(
      <CampaignReviewStep
        name="Campaign"
        subject="Subject"
        bodyHtml="<p>Body</p>"
        selectedSender={mockSender}
        onEditStep={vi.fn()}
      />
    );

    expect(screen.getByText("Recipients Configuration")).toBeDefined();
    expect(screen.getByText("Next, you'll select which recipients to include in this campaign.")).toBeDefined();
    expect(screen.getByText("Recipients will be configured in the next step.")).toBeDefined();
    expect(screen.getByText("You can import from CSV, select existing lists, or define filters.")).toBeDefined();
  });
});

