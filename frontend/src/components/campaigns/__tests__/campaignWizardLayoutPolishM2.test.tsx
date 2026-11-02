import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AuthorizedEmailAccount } from "../../../types/emails";
import type { CampaignStepWritePayload, SendingWindowConfig } from "../../../types/campaign";
import { CampaignContentStep } from "../CampaignContentStep";
import { CampaignReviewStep } from "../CampaignReviewStep";
import { CreateCampaignPage } from "../../../pages/CreateCampaignPage";

document.execCommand = vi.fn();

const mockSender: AuthorizedEmailAccount = {
  id: 1,
  company_id: 10,
  name: "Alex Vance",
  email_address: "sales@pulsemail.app",
  provider: "SMTP_IMAP",
  is_active: true,
  is_sync_enabled: true,
};

const mockSendingWindow: SendingWindowConfig = {
  enabled: true,
  timezone: "America/Chicago",
  days: [1, 2, 3, 4, 5],
  start_time: "08:30",
  end_time: "17:30",
};

describe("Milestone M2 — PulseMail Campaign Wizard Layout & Review Polish", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    window.scrollTo = vi.fn();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
  });

  it("1. Step 1 (Initial Outreach) shows immediate dispatch, sending window, and hides follow-up-only settings", () => {
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Checking back",
        body_html: "<p>Follow-up content</p>",
        body_text: "Follow-up content",
        is_active: true,
        target_tags: ["vip"],
      },
    ];

    render(
      <CampaignContentStep
        subject="Welcome to PulseMail"
        bodyHtml="<p>Root initial email body</p>"
        onBodyHtmlChange={vi.fn()}
        onSubjectChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={vi.fn()}
        sendingWindow={mockSendingWindow}
        initialStepNumber={1}
      />
    );

    // Initial Outreach settings
    expect(screen.getByText("Step 1: Initial Outreach")).toBeDefined();
    expect(screen.getByText("Immediately upon sequence launch")).toBeDefined();
    expect(screen.getByText(/08:30 - 17:30 \(America\/Chicago\)/i)).toBeDefined();
    expect(screen.getByText("Stop sequence if recipient replies")).toBeDefined();

    // Subject loads campaign root subject
    expect(screen.getByDisplayValue("Welcome to PulseMail")).toBeDefined();

    // Follow-up only settings MUST be hidden for initial outreach
    expect(screen.queryByText("Send as reply in the same thread")).toBeNull();
    expect(screen.queryByText("Target Recipient Tags (Optional)")).toBeNull();
    expect(screen.queryByText("Wait Duration")).toBeNull();
  });

  it("2. Selecting a follow-up step shows delay, threading, and target tags", () => {
    const onFollowupStepsChange = vi.fn();
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 72,
        subject: "Quick bump on architecture",
        body_html: "<p>Second step content</p>",
        body_text: "Second step content",
        target_tags: ["enterprise", "lead"],
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Root Subject"
        bodyHtml="<p>Root Body</p>"
        onBodyHtmlChange={vi.fn()}
        onSubjectChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={onFollowupStepsChange}
        sendingWindow={mockSendingWindow}
        initialStepNumber={1}
      />
    );

    // Switch to Step 2
    fireEvent.click(screen.getByText("Follow-Up Step #1 (Step 2)"));

    // Step 2 workspace is loaded
    expect(screen.getByText("Step 2: Follow-up #1")).toBeDefined();
    expect(screen.getByText("Wait Duration")).toBeDefined();
    expect(screen.getByDisplayValue("3")).toBeDefined(); // 72 / 24 = 3 days
    expect(screen.getByDisplayValue("Quick bump on architecture")).toBeDefined();
    expect(screen.getByText("Send as reply in the same thread")).toBeDefined();
    expect(screen.getByText("Target Recipient Tags (Optional)")).toBeDefined();
    expect(screen.getByText("#enterprise")).toBeDefined();
    expect(screen.getByText("#lead")).toBeDefined();
  });

  it("3. Review step (Step 4) displays compact ordered sequence summary with initial step and follow-up details", () => {
    const onEdit = vi.fn();
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Re: Quick check-in",
        body_html: "<p>Checking in on your review</p>",
        body_text: "Checking in on your review",
        target_tags: ["tier-1"],
        is_active: true,
      },
      {
        step_number: 3,
        delay_hours: 96,
        subject: "Closing the loop",
        body_html: "<p>Final follow-up message</p>",
        body_text: "Final follow-up message",
        is_active: true,
      },
    ];

    render(
      <CampaignReviewStep
        name="Q4 Enterprise Outreach"
        subject="Scaling Real-Time Telemetry"
        bodyHtml="<p>Our engineering team published a deep-dive.</p>"
        selectedSender={mockSender}
        sendIntervalSeconds={120}
        sendingWindow={mockSendingWindow}
        followupSteps={followupSteps}
        onEditStep={onEdit}
      />
    );

    // Header & Details
    expect(screen.getByText("Review Campaign")).toBeDefined();
    expect(screen.getByText("Q4 Enterprise Outreach")).toBeDefined();
    expect(screen.getByText("Scaling Real-Time Telemetry")).toBeDefined();
    expect(screen.getByText("2 minutes")).toBeDefined();
    expect(screen.getByText(/08:30 - 17:30 \(America\/Chicago\)/i)).toBeDefined();

    // Sender
    expect(screen.getByText("Alex Vance")).toBeDefined();
    expect(screen.getByText("sales@pulsemail.app")).toBeDefined();

    // Sequence Summary
    expect(screen.getByText("3 Steps in Sequence")).toBeDefined();
    expect(screen.getByText("Step 1: Initial Outreach")).toBeDefined();
    expect(screen.getByText("Immediate")).toBeDefined();

    // Follow-ups in sequence
    expect(screen.getByText("Automated Follow-Up Steps (2)")).toBeDefined();
    expect(screen.getByText("Follow-Up #1 (Step 2)")).toBeDefined();
    expect(screen.getByText(/Waits 2 days if no reply/i)).toBeDefined();
    expect(screen.getByText("#tier-1")).toBeDefined();

    expect(screen.getByText("Follow-Up #2 (Step 3)")).toBeDefined();
    expect(screen.getByText(/Waits 4 days if no reply/i)).toBeDefined();
    expect(screen.getByText("All recipients (untargeted)")).toBeDefined();

    // Edit buttons
    const editButtons = screen.getAllByRole("button", { name: /edit/i });
    expect(editButtons.length).toBe(3);

    // Edit Details -> Step 1
    fireEvent.click(editButtons[0]);
    expect(onEdit).toHaveBeenCalledWith(1);

    // Edit Sender -> Step 2
    fireEvent.click(editButtons[1]);
    expect(onEdit).toHaveBeenCalledWith(2);

    // Edit Sequence & Content -> Step 3
    fireEvent.click(editButtons[2]);
    expect(onEdit).toHaveBeenCalledWith(3);
  });

  it("4. End-to-end Wizard flow: Steps 1 -> 2 -> 3 -> 4, verifies Review and returns to edit step", async () => {
    const onSave = vi.fn().mockResolvedValue(101);

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/campaigns/new"]}>
          <CreateCampaignPage
            companyId={10}
            initialAccounts={[mockSender]}
            onSaveCampaign={onSave}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    // Step 1: Details
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. product launch/i), {
      target: { value: "Polished Cadence Launch" },
    });
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. introducing our new product line/i), {
      target: { value: "Keynote Follow-Up Announcement" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));

    // Step 2: Sender selection
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));

    // Step 3: Sequence Editor
    expect(screen.getByText("Sequence Steps")).toBeDefined();
    expect(screen.getByText("Step 1: Initial Outreach")).toBeDefined();
    expect(screen.queryByText("Send as reply in the same thread")).toBeNull();

    // Enter body for Step 1
    const editorCanvas = document.querySelector(".pulsemail-editor-canvas") as HTMLElement;
    if (editorCanvas) {
      editorCanvas.innerHTML = "<p>Polished body content for step 1</p>";
      fireEvent.input(editorCanvas);
    }

    // Add a Follow-up Step
    fireEvent.click(screen.getByRole("button", { name: /\+ add follow-up step/i }));
    expect(screen.getByText("Follow-Up Step #1 (Step 2)")).toBeDefined();
    expect(screen.getByText("Send as reply in the same thread")).toBeDefined();

    // Advance to Step 4 (Review)
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
    expect(screen.getByRole("heading", { name: /Review Campaign/i })).toBeDefined();
    expect(screen.getByText("Polished Cadence Launch")).toBeDefined();
    expect(screen.getByText("2 Steps in Sequence")).toBeDefined();

    // Click Edit on Email Content to navigate back to Step 3
    const editContentBtn = screen.getByRole("button", { name: /edit email content/i });
    fireEvent.click(editContentBtn);

    // Returned to Step 3 Sequence Editor
    expect(screen.getByText("Sequence Steps")).toBeDefined();
    expect(screen.getByText("Initial Outreach")).toBeDefined();
    expect(screen.getByText("Step 1: Initial Outreach")).toBeDefined();
    expect(screen.getByText("Follow-Up Step #1 (Step 2)")).toBeDefined();
  });
});
