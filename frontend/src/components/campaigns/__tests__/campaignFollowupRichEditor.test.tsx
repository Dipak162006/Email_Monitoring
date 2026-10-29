import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AuthorizedEmailAccount } from "../../../types/emails";
import type { CampaignStepWritePayload } from "../../../types/campaign";
import { CampaignContentStep, MAX_FOLLOWUP_STEPS } from "../CampaignContentStep";
import { CreateCampaignPage } from "../../../pages/CreateCampaignPage";

// Mock document.execCommand for rich text actions
document.execCommand = vi.fn();

const mockSender: AuthorizedEmailAccount = {
  id: 1,
  company_id: 10,
  name: "Sales Outreach",
  email_address: "outreach@example.com",
  provider: "SMTP_IMAP",
  is_active: true,
  is_sync_enabled: true,
};

describe("M1 — Follow-Up Rich-Text Editing & Maximum Step Limit Verification", () => {
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

  it("1. Renders an independent rich-text editor for each follow-up step", () => {
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Quick bump",
        body_html: "<p>Following up on my initial email.</p>",
        body_text: "Following up on my initial email.",
        is_active: true,
      },
      {
        step_number: 3,
        delay_hours: 96,
        subject: "Second reminder",
        body_html: "<p>Wanted to make sure you saw this.</p>",
        body_text: "Wanted to make sure you saw this.",
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Main Campaign Subject"
        bodyHtml="<p>Initial announcement message</p>"
        onBodyHtmlChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={vi.fn()}
      />
    );

    // Verify Step 1 content is rendered in its container
    expect(screen.getByText("Main Campaign Subject")).toBeDefined();

    // Verify Follow-up Step #1 and Step #2 card headers in timeline
    expect(screen.getByText("Follow-Up Step #1 (Step 2)")).toBeDefined();
    expect(screen.getByText("Follow-Up Step #2 (Step 3)")).toBeDefined();

    // Active step has an editor toolbar
    const toolbars = screen.getAllByRole("toolbar");
    expect(toolbars.length).toBeGreaterThan(0);

    // Verify active editor contains its respective content
    expect(screen.getByText("Following up on my initial email.")).toBeDefined();

    // Selecting Step 3 loads its editor content into workspace
    fireEvent.click(screen.getByText("Follow-Up Step #2 (Step 3)"));
    expect(screen.getByText("Wanted to make sure you saw this.")).toBeDefined();
  });

  it("2. Editing one follow-up step does not modify another follow-up step or Step 1", () => {
    const onFollowupStepsChange = vi.fn();
    const onBodyHtmlChange = vi.fn();

    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Follow-up 1",
        body_html: "<p>Step 2 Body</p>",
        body_text: "Step 2 Body",
        is_active: true,
      },
      {
        step_number: 3,
        delay_hours: 72,
        subject: "Follow-up 2",
        body_html: "<p>Step 3 Body</p>",
        body_text: "Step 3 Body",
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Step 1 Subject"
        bodyHtml="<p>Step 1 Content</p>"
        onBodyHtmlChange={onBodyHtmlChange}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={onFollowupStepsChange}
      />
    );

    // Change subject of follow-up step 1
    const subjectInput = screen.getByPlaceholderText(/Re: Step 1 Subject/i);
    fireEvent.change(subjectInput, { target: { value: "Updated Step 2 Subject" } });

    // Step 1 onBodyHtmlChange was NOT called
    expect(onBodyHtmlChange).not.toHaveBeenCalled();

    // onFollowupStepsChange was called updating only index 0
    expect(onFollowupStepsChange).toHaveBeenCalled();
    const lastCallArg = onFollowupStepsChange.mock.calls[onFollowupStepsChange.mock.calls.length - 1][0];
    expect(lastCallArg[0].subject).toBe("Updated Step 2 Subject");
    expect(lastCallArg[1].subject).toBe("Follow-up 2"); // Step 3 unchanged
  });

  it("3. Correctly maps rich-text content into the existing campaign payload via CreateCampaignPage", async () => {
    const onSaveCampaign = vi.fn().mockResolvedValue({ id: 999, name: "Rich Outreach" });

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
    const nameInput = screen.getByPlaceholderText(/e\.g\. product launch/i);
    const subjectInput = screen.getByPlaceholderText(/e\.g\. introducing our new product line/i);
    fireEvent.change(nameInput, { target: { value: "Rich Outreach" } });
    fireEvent.change(subjectInput, { target: { value: "Initial Message" } });

    // Continue to Step 2 (Sender)
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));

    // Continue to Step 3 (Content & Sequences)
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
    expect(screen.getAllByText(/Step 3 of 4/i).length).toBeGreaterThan(0);

    // Provide initial Step 1 body so Step 3 validation succeeds
    const editorCanvas = document.querySelector(".pulsemail-editor-canvas") as HTMLElement;
    if (editorCanvas) {
      editorCanvas.innerHTML = "<p>Initial message body content</p>";
      fireEvent.input(editorCanvas);
    }

    // Add a follow-up step
    const addStepBtn = screen.getByRole("button", { name: /\+ add follow-up step/i });
    fireEvent.click(addStepBtn);

    expect(screen.getByText("Follow-Up Step #1 (Step 2)")).toBeDefined();

    // Continue to Step 4 (Review)
    fireEvent.click(screen.getByRole("button", { name: /^continue$/i }));
    expect(screen.getAllByText(/Step 4 of 4/i).length).toBeGreaterThan(0);

    // Save as Draft
    const saveDraftBtn = screen.getByRole("button", { name: /^save draft$/i });
    fireEvent.click(saveDraftBtn);

    await waitFor(() => {
      expect(onSaveCampaign).toHaveBeenCalledTimes(1);
    });

    const payload = onSaveCampaign.mock.calls[0][1];
    expect(payload.name).toBe("Rich Outreach");
    expect(payload.subject).toBe("Initial Message");
    expect(payload.followup_steps).toBeDefined();
    expect(payload.followup_steps.length).toBe(1);
    expect(payload.followup_steps[0].step_number).toBe(2);
    expect(payload.followup_steps[0].delay_hours).toBe(72);
  });

  it("4. Existing plain-text content in follow-up step remains visible and editable", () => {
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 24,
        subject: "",
        body_text: "Existing plain text note without html tags",
        body_html: null,
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Announcement"
        bodyHtml="<p>Hello</p>"
        onBodyHtmlChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={vi.fn()}
      />
    );

    // Plain text is wrapped into HTML paragraph and displayed inside the editor
    expect(screen.getByText("Existing plain text note without html tags")).toBeDefined();
  });

  it("5. Switching between Edit and Preview modes preserves follow-up content and renders preview", () => {
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Hi {{first_name}} - Quick Follow-Up",
        body_html: "<p>Hi <b>{{first_name}}</b>, did you get a chance to review {{company_name}}?</p>",
        body_text: "Hi Jane, did you get a chance to review Acme Corp?",
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Announcement"
        bodyHtml="<p>Initial</p>"
        onBodyHtmlChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={vi.fn()}
      />
    );

    // Step 2 card is initially in Edit mode
    const previewBtn = screen.getByRole("button", { name: /^preview$/i });
    fireEvent.click(previewBtn);

    // Preview mode renders simulated preview with merge tags substituted
    expect(screen.getByText("Threaded Follow-up")).toBeDefined();
    expect(screen.getAllByText("Subject:").length).toBeGreaterThan(0);
    expect(screen.getByText("Hi Jane - Quick Follow-Up")).toBeDefined();
    expect(screen.getByText(/did you get a chance to review Acme Corp\?/i)).toBeDefined();

    // Switch back to Edit mode
    const editBtn = screen.getByRole("button", { name: /^edit$/i });
    fireEvent.click(editBtn);

    // Editor is restored with original content
    expect(screen.getByText(/did you get a chance to review/i)).toBeDefined();
  });

  it("6. Merge-tag buttons insert standard tags into the follow-up rich text editor", () => {
    const onFollowupStepsChange = vi.fn();
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 24,
        subject: "Checking in",
        body_html: "<p>Hello</p>",
        body_text: "Hello",
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Main"
        bodyHtml="<p>Main</p>"
        onBodyHtmlChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={onFollowupStepsChange}
      />
    );

    // Find merge tag button inside follow-up step
    const firstNameTagBtn = screen.getAllByRole("button", { name: "{{first_name}}" });
    expect(firstNameTagBtn.length).toBeGreaterThan(0);

    // Click {{first_name}} on the follow-up step card
    fireEvent.click(firstNameTagBtn[firstNameTagBtn.length - 1]);

    // Either rich editor insertText called document.execCommand or fallback updated state
    expect(document.execCommand).toHaveBeenCalledWith("insertText", false, "{{first_name}}");
  });

  it("7. The UI permits adding up to MAX_FOLLOWUP_STEPS (9 follow-ups = 10 total steps) and disables further additions", () => {
    expect(MAX_FOLLOWUP_STEPS).toBe(9);

    const onFollowupStepsChange = vi.fn();

    // 8 existing follow-up steps (steps 2 to 9)
    const existingEightSteps: CampaignStepWritePayload[] = Array.from({ length: 8 }, (_, i) => ({
      step_number: i + 2,
      delay_hours: 24 * (i + 1),
      subject: `Step ${i + 2}`,
      body_html: `<p>Content ${i + 2}</p>`,
      body_text: `Content ${i + 2}`,
      is_active: true,
    }));

    const { rerender } = render(
      <CampaignContentStep
        subject="Initial"
        bodyHtml="<p>Initial</p>"
        onBodyHtmlChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={existingEightSteps}
        onFollowupStepsChange={onFollowupStepsChange}
      />
    );

    // Add button is still enabled at 8/9
    const addBtn = screen.getByRole("button", { name: /\+ add follow-up step/i });
    expect(addBtn.hasAttribute("disabled")).toBe(false);
    expect(screen.getByText("8/9")).toBeDefined();

    fireEvent.click(addBtn);
    expect(onFollowupStepsChange).toHaveBeenCalled();

    // Re-render at maximum 9 follow-up steps (Steps 2..10)
    const maxNineSteps: CampaignStepWritePayload[] = [
      ...existingEightSteps,
      {
        step_number: 10,
        delay_hours: 216,
        subject: "Step 10",
        body_html: "<p>Content 10</p>",
        body_text: "Content 10",
        is_active: true,
      },
    ];

    rerender(
      <CampaignContentStep
        subject="Initial"
        bodyHtml="<p>Initial</p>"
        onBodyHtmlChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={maxNineNineSteps(maxNineSteps)}
        onFollowupStepsChange={onFollowupStepsChange}
      />
    );

    // Verify button is now disabled and limit message displayed
    const disabledAddBtn = screen.getByRole("button", { name: /\+ add follow-up step/i });
    expect(disabledAddBtn.hasAttribute("disabled")).toBe(true);
    expect(screen.getByText("9/9")).toBeDefined();
    expect(
      screen.getByText(/maximum sequence limit reached \(1 initial email \+ 9 follow-up steps = 10 total steps\)/i)
    ).toBeDefined();
  });
});

function maxNineNineSteps(steps: CampaignStepWritePayload[]): CampaignStepWritePayload[] {
  return steps;
}
