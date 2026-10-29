import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AuthorizedEmailAccount } from "../../../types/emails";
import type { CampaignStepWritePayload, SendingWindowConfig } from "../../../types/campaign";
import { CampaignContentStep } from "../CampaignContentStep";
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
  timezone: "America/New_York",
  days: [1, 2, 3, 4, 5],
  start_time: "09:00",
  end_time: "17:00",
};

describe("M1 — PulseMail Master-Detail Sequence Editor UI/UX Verification", () => {
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

  it("1. Renders the Master-Detail layout with Timeline left-rail and Workspace right-panel", () => {
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Quick bump",
        body_html: "<p>Follow-up message</p>",
        body_text: "Follow-up message",
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Initial Outreach Subject"
        bodyHtml="<p>Welcome to PulseMail</p>"
        onBodyHtmlChange={vi.fn()}
        onSubjectChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={vi.fn()}
        sendingWindow={mockSendingWindow}
        initialStepNumber={1}
      />
    );

    // Left rail header
    expect(screen.getByText("Sequence Steps")).toBeDefined();
    expect(screen.getAllByText("2").length).toBeGreaterThanOrEqual(1); // 2 steps total
    expect(screen.getByText(/Estimated window: ~2 business days/i)).toBeDefined();

    // Timeline nodes
    expect(screen.getByText("Initial Outreach")).toBeDefined();
    expect(screen.getByText("Wait 2 days")).toBeDefined();
    expect(screen.getByText("Follow-Up Step #1 (Step 2)")).toBeDefined();

    // Active Step Workspace header (Step 1 is selected)
    expect(screen.getByText("Step 1: Initial Outreach")).toBeDefined();
    expect(screen.getByText("Immediately upon sequence launch")).toBeDefined();
    expect(screen.getByText(/09:00 - 17:00 \(America\/New_York\)/i)).toBeDefined();
  });

  it("2. Selecting a follow-up step loads its delay, subject, tags, and body into the workspace", () => {
    const onFollowupStepsChange = vi.fn();
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 72,
        subject: "Checking on your infrastructure",
        body_html: "<p>Have you had time to review?</p>",
        body_text: "Have you had time to review?",
        target_tags: ["enterprise"],
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Initial Subject"
        bodyHtml="<p>Initial Body</p>"
        onBodyHtmlChange={vi.fn()}
        onSubjectChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={onFollowupStepsChange}
        sendingWindow={mockSendingWindow}
        initialStepNumber={1}
      />
    );

    // Click Follow-up Step in the left timeline
    fireEvent.click(screen.getByText("Follow-Up Step #1 (Step 2)"));

    // Right workspace now shows Step 2 details
    expect(screen.getByText("Step 2: Follow-up #1")).toBeDefined();
    expect(screen.getByText("#enterprise")).toBeDefined();
    expect(screen.getByDisplayValue("Checking on your infrastructure")).toBeDefined();
    expect(screen.getByDisplayValue("3")).toBeDefined(); // 72 hours / 24 = 3 days

    // Switching back to Step 1 loads Step 1 into workspace
    fireEvent.click(screen.getByText("Initial Outreach"));
    expect(screen.getByText("Step 1: Initial Outreach")).toBeDefined();
    expect(screen.getByDisplayValue("Initial Subject")).toBeDefined();
  });

  it("3. Adding a step adds a new follow-up step and immediately opens its workspace", () => {
    const onFollowupStepsChange = vi.fn();
    const followupSteps: CampaignStepWritePayload[] = [];

    render(
      <CampaignContentStep
        subject="Welcome"
        bodyHtml="<p>Content</p>"
        onBodyHtmlChange={vi.fn()}
        onSubjectChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={onFollowupStepsChange}
        initialStepNumber={1}
      />
    );

    const addStepBtn = screen.getByRole("button", { name: /\+ add follow-up step/i });
    fireEvent.click(addStepBtn);

    // Handler called with new follow-up step
    expect(onFollowupStepsChange).toHaveBeenCalledWith([
      expect.objectContaining({
        step_number: 2,
        delay_hours: 72,
        is_active: true,
      }),
    ]);
  });

  it("4. Deleting a step re-indexes remaining steps and updates the sequence timeline", () => {
    const onFollowupStepsChange = vi.fn();
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 24,
        subject: "Step 2 Note",
        is_active: true,
      },
      {
        step_number: 3,
        delay_hours: 48,
        subject: "Step 3 Note",
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Welcome"
        bodyHtml="<p>Content</p>"
        onBodyHtmlChange={vi.fn()}
        onSubjectChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={onFollowupStepsChange}
        initialStepNumber={2}
      />
    );

    // Delete icons are rendered in the timeline for each follow-up step
    const deleteButtons = screen.getAllByTitle("Delete step");
    expect(deleteButtons.length).toBe(2);

    // Click delete on first follow-up (Step 2)
    fireEvent.click(deleteButtons[0]);

    // Remaining step is re-indexed from step_number 3 to step_number 2
    expect(onFollowupStepsChange).toHaveBeenCalledWith([
      expect.objectContaining({
        step_number: 2,
        subject: "Step 3 Note",
      }),
    ]);
  });

  it("5. Duplicating a step inserts a cloned step into the sequence", () => {
    const onFollowupStepsChange = vi.fn();
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Important follow-up",
        body_html: "<p>Original Body</p>",
        body_text: "Original Body",
        target_tags: ["vip"],
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Main Campaign"
        bodyHtml="<p>Main Body</p>"
        onBodyHtmlChange={vi.fn()}
        onSubjectChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={onFollowupStepsChange}
        initialStepNumber={2}
      />
    );

    const duplicateBtn = screen.getByTitle("Duplicate step");
    fireEvent.click(duplicateBtn);

    expect(onFollowupStepsChange).toHaveBeenCalledWith([
      expect.objectContaining({
        step_number: 2,
        subject: "Important follow-up",
      }),
      expect.objectContaining({
        step_number: 3,
        subject: "Important follow-up",
        target_tags: ["vip"],
      }),
    ]);
  });

  it("6. Full wizard flow: Save Draft persists initial email and sequence steps", async () => {
    const onSaveCampaign = vi.fn().mockResolvedValue({ id: 888, name: "Master-Detail Sequence" });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CreateCampaignPage
            companyId={10}
            initialAccounts={[mockSender]}
            onSaveCampaign={onSaveCampaign}
          />
        </MemoryRouter>
      </QueryClientProvider>
    );

    // Step 1: Details
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. product launch/i), {
      target: { value: "Master-Detail Outreach" },
    });
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. introducing our new product line/i), {
      target: { value: "Scaling Telemetry with PulseMail" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));

    // Step 2: Sender selection
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));

    // Step 3: Master-Detail Sequence Editor
    expect(screen.getByText("Sequence Steps")).toBeDefined();
    expect(screen.getByText("Step 1: Initial Outreach")).toBeDefined();

    // Input body for Step 1
    const editorCanvas = document.querySelector(".pulsemail-editor-canvas") as HTMLElement;
    if (editorCanvas) {
      editorCanvas.innerHTML = "<p>Initial high-throughput telemetry</p>";
      fireEvent.input(editorCanvas);
    }

    // Add Follow-up Step
    fireEvent.click(screen.getByRole("button", { name: /\+ add follow-up step/i }));
    expect(screen.getByText("Follow-Up Step #1 (Step 2)")).toBeDefined();

    // Advance to Step 4 (Review)
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
    expect(screen.getAllByText(/Step 4 of 4/i).length).toBeGreaterThan(0);

    // Save Draft
    fireEvent.click(screen.getByRole("button", { name: /^save draft$/i }));

    await waitFor(() => {
      expect(onSaveCampaign).toHaveBeenCalledTimes(1);
    });

    const payload = onSaveCampaign.mock.calls[0][1];
    expect(payload.name).toBe("Master-Detail Outreach");
    expect(payload.subject).toBe("Scaling Telemetry with PulseMail");
    expect(payload.followup_steps.length).toBe(1);
    expect(payload.followup_steps[0].step_number).toBe(2);
    expect(payload.followup_steps[0].delay_hours).toBe(72);
  });
});
