import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import type { AuthorizedEmailAccount } from "../../../types/emails";
import type { CampaignStepWritePayload } from "../../../types/campaign";
import { CampaignContentStep } from "../CampaignContentStep";

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

describe("CampaignContentStep — Initial Email Selection & Step Switching", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.scrollTo = vi.fn();
  });

  it("1. Defaults to Step 1 (Initial Outreach) when opened without initialStepNumber, even if follow-up steps exist", () => {
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Follow-up #1 Subject",
        body_html: "<p>Follow-up #1 Body</p>",
        body_text: "Follow-up #1 Body",
        is_active: true,
      },
      {
        step_number: 3,
        delay_hours: 72,
        subject: "Follow-up #2 Subject",
        body_html: "<p>Follow-up #2 Body</p>",
        body_text: "Follow-up #2 Body",
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Initial Outreach Subject"
        bodyHtml="<p>Initial Outreach Body</p>"
        onBodyHtmlChange={vi.fn()}
        onSubjectChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={vi.fn()}
        // initialStepNumber omitted intentionally
      />
    );

    // Active step title must be Step 1
    expect(screen.getByRole("heading", { name: /Step 1: Initial Outreach/i })).toBeDefined();

    // Subject input must show the initial step subject
    const subjectInput = screen.getByLabelText(/Subject Line/i) as HTMLInputElement;
    expect(subjectInput.value).toBe("Initial Outreach Subject");

    // Preflight badge for Step 1
    expect(screen.getByText("Primary email dispatched immediately upon campaign launch")).toBeDefined();
  });

  it("2. Preserves explicitly requested step selection when opened with initialStepNumber", () => {
    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Follow-up #1 Specific Subject",
        body_html: "<p>Follow-up #1 Specific Body</p>",
        body_text: "Follow-up #1 Specific Body",
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Initial Outreach Subject"
        bodyHtml="<p>Initial Outreach Body</p>"
        onBodyHtmlChange={vi.fn()}
        onSubjectChange={vi.fn()}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={vi.fn()}
        initialStepNumber={2}
      />
    );

    // Active step title must be Step 2
    expect(screen.getByRole("heading", { name: /Step 2: Follow-up #1/i })).toBeDefined();

    // Subject input must show the follow-up step subject
    const subjectInput = screen.getByLabelText(/Subject Line/i) as HTMLInputElement;
    expect(subjectInput.value).toBe("Follow-up #1 Specific Subject");
  });

  it("3. Preserves existing Step 1 and follow-up content when switching between steps", () => {
    const onSubjectChange = vi.fn();
    const onBodyHtmlChange = vi.fn();
    const onFollowupStepsChange = vi.fn();

    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Second Step Subject",
        body_html: "<p>Second Step Body</p>",
        body_text: "Second Step Body",
        is_active: true,
      },
    ];

    const { rerender } = render(
      <CampaignContentStep
        subject="First Step Subject"
        bodyHtml="<p>First Step Body</p>"
        onBodyHtmlChange={onBodyHtmlChange}
        onSubjectChange={onSubjectChange}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={onFollowupStepsChange}
      />
    );

    // Initial state: Step 1 selected
    expect(screen.getByRole("heading", { name: /Step 1: Initial Outreach/i })).toBeDefined();
    let subjectInput = screen.getByLabelText(/Subject Line/i) as HTMLInputElement;
    expect(subjectInput.value).toBe("First Step Subject");

    // Click Follow-up Step #1 in the left rail to switch to Step 2
    const followUpNode = screen.getByText(/Follow-Up Step #1 \(Step 2\)/i);
    fireEvent.click(followUpNode);

    // Now Step 2 is active
    expect(screen.getByRole("heading", { name: /Step 2: Follow-up #1/i })).toBeDefined();
    subjectInput = screen.getByLabelText(/Subject Line/i) as HTMLInputElement;
    expect(subjectInput.value).toBe("Second Step Subject");

    // Step 1 callbacks were NOT triggered (no overwriting)
    expect(onSubjectChange).not.toHaveBeenCalled();
    expect(onBodyHtmlChange).not.toHaveBeenCalled();

    // Click Step 1 (Initial Outreach) in the left rail to switch back
    const step1Node = screen.getByText("Initial Outreach");
    fireEvent.click(step1Node);

    // Back on Step 1
    expect(screen.getByRole("heading", { name: /Step 1: Initial Outreach/i })).toBeDefined();
    subjectInput = screen.getByLabelText(/Subject Line/i) as HTMLInputElement;
    expect(subjectInput.value).toBe("First Step Subject");

    // Verify rerender with updated props preserves active selection and contents
    rerender(
      <CampaignContentStep
        subject="Updated First Step Subject"
        bodyHtml="<p>Updated First Step Body</p>"
        onBodyHtmlChange={onBodyHtmlChange}
        onSubjectChange={onSubjectChange}
        selectedSender={mockSender}
        followupSteps={followupSteps}
        onFollowupStepsChange={onFollowupStepsChange}
      />
    );

    expect(screen.getByRole("heading", { name: /Step 1: Initial Outreach/i })).toBeDefined();
    subjectInput = screen.getByLabelText(/Subject Line/i) as HTMLInputElement;
    expect(subjectInput.value).toBe("Updated First Step Subject");
  });
});

