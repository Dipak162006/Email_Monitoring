import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { RecipientTagModal } from "../recipients/RecipientTagModal";
import { RecipientTable } from "../recipients/RecipientTable";
import { CampaignContentStep } from "../CampaignContentStep";
import type { CampaignRecipient, CampaignStepWritePayload } from "../../../types/campaign";

describe("Milestone M5 — Recipient Tags & Selective Targeting UI", () => {
  const sampleRecipient: CampaignRecipient = {
    id: 101,
    campaign_id: 201,
    email: "tag_user@test.com",
    first_name: "Tag",
    last_name: "Tester",
    tags: ["vip", "lead"],
    status: "ACTIVE",
    current_step_number: 1,
    next_step_due_at: "2026-11-01T12:00:00Z",
    created_at: "2026-10-28T10:00:00Z",
  };

  it("1. RecipientTable displays tag chips and provides tag management action", () => {
    const onManageTagsMock = vi.fn();

    render(
      <RecipientTable
        recipients={[sampleRecipient]}
        isEditable={false}
        canManageFollowups={true}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
        onCopyEmail={vi.fn()}
        onManageTags={onManageTagsMock}
      />
    );

    // Verify tag chips render
    expect(screen.getByText("#vip")).toBeDefined();
    expect(screen.getByText("#lead")).toBeDefined();

    // Verify manage tags button triggers callback
    const tagButton = screen.getByRole("button", {
      name: /Manage tags for tag_user@test.com/i,
    });
    fireEvent.click(tagButton);
    expect(onManageTagsMock).toHaveBeenCalledWith(sampleRecipient);
  });

  it("2. RecipientTagModal adds, validates, removes, and saves tags", async () => {
    const onUpdateTagsMock = vi.fn().mockResolvedValue(undefined);
    const onCloseMock = vi.fn();

    render(
      <RecipientTagModal
        isOpen={true}
        onClose={onCloseMock}
        recipient={sampleRecipient}
        onUpdateTags={onUpdateTagsMock}
      />
    );

    // Initial tags are displayed
    expect(screen.getByText("#vip")).toBeDefined();
    expect(screen.getByText("#lead")).toBeDefined();

    // Add a new tag
    const input = screen.getByPlaceholderText(/e\.g\. vip, lead, enterprise/i);
    fireEvent.change(input, { target: { value: "enterprise" } });
    fireEvent.click(screen.getByRole("button", { name: /Add/i }));

    expect(screen.getByText("#enterprise")).toBeDefined();

    // Remove the 'vip' tag
    const removeVipBtn = screen.getByRole("button", { name: /Remove tag vip/i });
    fireEvent.click(removeVipBtn);
    expect(screen.queryByText("#vip")).toBeNull();

    // Click Save
    const saveBtn = screen.getByRole("button", { name: /Save Changes/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(onUpdateTagsMock).toHaveBeenCalledWith(101, ["lead", "enterprise"]);
      expect(onCloseMock).toHaveBeenCalled();
    });
  });

  it("3. Follow-up step tag targeting in CampaignContentStep allows tag configuration", () => {
    const onFollowupStepsChangeMock = vi.fn();

    const followupSteps: CampaignStepWritePayload[] = [
      {
        step_number: 2,
        delay_hours: 48,
        subject: "Followup Step 2",
        body_text: "Targeted message",
        target_tags: ["vip"],
        is_active: true,
      },
    ];

    render(
      <CampaignContentStep
        subject="Main Subject"
        bodyHtml="<p>Main content</p>"
        onBodyHtmlChange={vi.fn()}
        followupSteps={followupSteps}
        onFollowupStepsChange={onFollowupStepsChangeMock}
      />
    );

    // Tag chip #vip should be visible
    expect(screen.getByText("#vip")).toBeDefined();
    expect(
      screen.getByText(/Applies to recipients matching ANY tag/i)
    ).toBeDefined();

    // Add another tag
    const addInput = screen.getByPlaceholderText(/Add tag \(e\.g\. vip\)\.\.\./i);
    fireEvent.change(addInput, { target: { value: "enterprise" } });
    const addBtn = screen.getByRole("button", { name: /^Add$/i });
    fireEvent.click(addBtn);

    expect(onFollowupStepsChangeMock).toHaveBeenCalledWith([
      expect.objectContaining({
        step_number: 2,
        target_tags: ["vip", "enterprise"],
      }),
    ]);
  });
});
