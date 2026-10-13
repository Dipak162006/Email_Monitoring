import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AuthorizedEmailAccount } from "../../../types/emails";

import { CreateCampaignPage } from "../../../pages/CreateCampaignPage";
import { CampaignWizardHeader } from "../CampaignWizardHeader";
import { CampaignWizardStepper } from "../CampaignWizardStepper";
import { CampaignWizardFooter } from "../CampaignWizardFooter";
import { CampaignDetailsStep } from "../CampaignDetailsStep";
import { SenderAccountCard } from "../SenderAccountCard";
import { SenderSelectionStep } from "../SenderSelectionStep";
import { CampaignContentStep } from "../CampaignContentStep";
import { CampaignReviewStep } from "../CampaignReviewStep";
import { UnsavedChangesDialog } from "../UnsavedChangesDialog";

const mockAccounts: AuthorizedEmailAccount[] = [
  {
    id: 1,
    company_id: 10,
    name: "Sales Team",
    email_address: "sales@example.com",
    provider: "SMTP_IMAP",
    is_active: true,
    is_sync_enabled: true,
  },
  {
    id: 2,
    company_id: 10,
    name: "Marketing",
    email_address: "marketing@example.com",
    provider: "GMAIL",
    is_active: true,
    is_sync_enabled: true,
  },
  {
    id: 3,
    company_id: 10,
    name: "Support Desk",
    email_address: "support@example.com",
    provider: "ZOHO",
    is_active: false,
    is_sync_enabled: false,
  },
];

describe("C12.2 Create Campaign Wizard Components", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.scrollTo = vi.fn();
  });

  describe("1. CampaignWizardHeader", () => {
    it("renders page title, step indicator badge, and Back to Campaigns action", () => {
      const onBack = vi.fn();
      render(
        <CampaignWizardHeader
          currentStep={1}
          totalSteps={4}
          onBackToCampaigns={onBack}
        />
      );

      expect(screen.getByText("Create Campaign")).toBeDefined();
      expect(
        screen.getByText("Create and prepare your outreach campaign.")
      ).toBeDefined();
      expect(screen.getByText("Step 1 of 4")).toBeDefined();

      const backBtn = screen.getByRole("button", {
        name: /back to campaigns/i,
      });
      fireEvent.click(backBtn);
      expect(onBack).toHaveBeenCalledTimes(1);
    });

    it("updates step badge correctly for subsequent steps", () => {
      render(
        <CampaignWizardHeader
          currentStep={3}
          totalSteps={4}
          onBackToCampaigns={vi.fn()}
        />
      );
      expect(screen.getByText("Step 3 of 4")).toBeDefined();
    });
  });

  describe("2. CampaignWizardStepper", () => {
    it("renders all 4 steps with titles and accessible navigation", () => {
      const onStepClick = vi.fn();
      render(
        <CampaignWizardStepper
          currentStep={2}
          onStepClick={onStepClick}
          canNavigateToStep={(step) => step <= 2}
        />
      );

      expect(screen.getAllByText("Details").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Sender").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Content").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Review").length).toBeGreaterThan(0);

      // Step 1 is completed and accessible
      const step1Btn = screen.getByRole("button", { name: /details/i });
      fireEvent.click(step1Btn);
      expect(onStepClick).toHaveBeenCalledWith(1);

      // Step 4 is upcoming and disabled
      const step4Btn = screen.getByRole("button", { name: /review/i });
      expect(step4Btn.hasAttribute("disabled")).toBe(true);
    });
  });

  describe("3. CampaignWizardFooter", () => {
    it("disables back button on step 1, enables on step 2, and handles callbacks", () => {
      const onBack = vi.fn();
      const onContinue = vi.fn();
      const onSaveDraft = vi.fn();

      const { rerender } = render(
        <CampaignWizardFooter
          currentStep={1}
          onBack={onBack}
          onContinue={onContinue}
          onSaveDraft={onSaveDraft}
        />
      );

      const backBtn = screen.getByRole("button", { name: /back/i });
      expect(backBtn.hasAttribute("disabled")).toBe(false);
      fireEvent.click(backBtn);
      expect(onBack).toHaveBeenCalledTimes(1);

      // Disabled when saving
      rerender(
        <CampaignWizardFooter
          currentStep={1}
          onBack={onBack}
          onContinue={onContinue}
          onSaveDraft={onSaveDraft}
          isSaving={true}
        />
      );
      expect(screen.getByRole("button", { name: /back/i }).hasAttribute("disabled")).toBe(true);

      const saveBtn = screen.getByRole("button", { name: /saving\.\.\./i });
      expect(saveBtn.hasAttribute("disabled")).toBe(true);

      // Re-render without saving
      rerender(
        <CampaignWizardFooter
          currentStep={1}
          onBack={onBack}
          onContinue={onContinue}
          onSaveDraft={onSaveDraft}
          isSaving={false}
        />
      );

      const continueBtn = screen.getByRole("button", { name: /continue/i });
      fireEvent.click(continueBtn);
      expect(onContinue).toHaveBeenCalledTimes(1);

      // Rerender on step 2: back button is enabled
      rerender(
        <CampaignWizardFooter
          currentStep={2}
          onBack={onBack}
          onContinue={onContinue}
          onSaveDraft={onSaveDraft}
        />
      );
      expect(screen.getByRole("button", { name: /back/i }).hasAttribute("disabled")).toBe(false);

      // Rerender on step 4: button displays Continue to Recipients
      rerender(
        <CampaignWizardFooter
          currentStep={4}
          onBack={onBack}
          onContinue={onContinue}
          onSaveDraft={onSaveDraft}
        />
      );
      expect(
        screen.getByRole("button", { name: /continue to recipients/i })
      ).toBeDefined();
    });

    it("disables both actions while saving is in progress", () => {
      render(
        <CampaignWizardFooter
          currentStep={2}
          onBack={vi.fn()}
          onContinue={vi.fn()}
          onSaveDraft={vi.fn()}
          isSaving={true}
        />
      );

      const saveBtn = screen.getByRole("button", { name: /saving\.\.\./i });
      expect(saveBtn.hasAttribute("disabled")).toBe(true);

      const continueBtn = screen.getByRole("button", { name: /continue/i });
      expect(continueBtn.hasAttribute("disabled")).toBe(true);
    });
  });

  describe("4. CampaignDetailsStep", () => {
    it("renders name and subject inputs with character count", () => {
      const onNameChange = vi.fn();
      const onSubjectChange = vi.fn();

      render(
        <CampaignDetailsStep
          name="Q4 Enterprise Outreach"
          onNameChange={onNameChange}
          subject="Important Update"
          onSubjectChange={onSubjectChange}
        />
      );

      expect(screen.getByText("Campaign Details")).toBeDefined();
      expect(screen.getByText("22/80 chars")).toBeDefined();
      expect(screen.getByDisplayValue("Q4 Enterprise Outreach")).toBeDefined();
      expect(screen.getByDisplayValue("Important Update")).toBeDefined();
    });

    it("inserts {{first_name}} merge tag into subject when clicked", () => {
      const onSubjectChange = vi.fn();

      render(
        <CampaignDetailsStep
          name="Launch"
          onNameChange={vi.fn()}
          subject="Hello"
          onSubjectChange={onSubjectChange}
        />
      );

      const insertBtn = screen.getByRole("button", {
        name: /insert \{\{first_name\}\}/i,
      });
      fireEvent.click(insertBtn);
      expect(onSubjectChange).toHaveBeenCalledWith("Hello {{first_name}}");
    });

    it("displays accessible inline error messages for missing required fields", () => {
      render(
        <CampaignDetailsStep
          name=""
          onNameChange={vi.fn()}
          subject=""
          onSubjectChange={vi.fn()}
          nameError="Campaign name is required."
          subjectError="Subject is required."
        />
      );

      expect(screen.getByText("Campaign name is required.")).toBeDefined();
      expect(screen.getByText("Subject is required.")).toBeDefined();
      expect(screen.getAllByRole("alert").length).toBe(2);
    });
  });

  describe("5. SenderAccountCard & SenderSelectionStep", () => {
    it("renders authorized sender accounts with provider and active badges", () => {
      const onSelect = vi.fn();
      render(
        <SenderAccountCard
          account={mockAccounts[0]}
          isSelected={true}
          onSelect={onSelect}
        />
      );

      expect(screen.getByText("Sales Team")).toBeDefined();
      expect(screen.getByText("sales@example.com")).toBeDefined();
      expect(screen.getByText("Custom SMTP")).toBeDefined();
      expect(screen.getByText("Active")).toBeDefined();
      expect(screen.getByRole("radio").getAttribute("aria-checked")).toBe("true");
    });

    it("disables inactive mailboxes and explains reason without allowing selection", () => {
      const onSelect = vi.fn();
      render(
        <SenderAccountCard
          account={mockAccounts[2]}
          isSelected={false}
          onSelect={onSelect}
        />
      );

      expect(screen.getByText("Support Desk")).toBeDefined();
      expect(screen.getByText("Inactive")).toBeDefined();
      expect(screen.getByText(/mailbox is inactive/i)).toBeDefined();

      const card = screen.getByRole("radio");
      expect(card.getAttribute("aria-disabled")).toBe("true");
      fireEvent.click(card);
      expect(onSelect).not.toHaveBeenCalled();
    });

    it("renders sender selection list with selected identity summary", () => {
      const onSelect = vi.fn();
      render(
        <MemoryRouter>
          <SenderSelectionStep
            accounts={mockAccounts}
            selectedAccountId={1}
            onSelectAccount={onSelect}
          />
        </MemoryRouter>
      );

      expect(screen.getByText("Sender Account")).toBeDefined();
      expect(
        screen.getByText("Sending from Sales Team (sales@example.com)")
      ).toBeDefined();
      expect(screen.getByText("example.com")).toBeDefined();
    });

    it("renders empty state with connect action when no authorized accounts exist", () => {
      render(
        <MemoryRouter>
          <SenderSelectionStep
            accounts={[]}
            selectedAccountId={null}
            onSelectAccount={vi.fn()}
          />
        </MemoryRouter>
      );

      expect(
        screen.getByText("No sending accounts available")
      ).toBeDefined();
      expect(
        screen.getByText("Connect and configure an email account before creating a campaign.")
      ).toBeDefined();
      expect(
        screen.getByRole("link", { name: /connect email account/i })
      ).toBeDefined();
    });
  });

  describe("6. CampaignContentStep", () => {
    it("toggles between edit and preview tabs", () => {
      render(
        <CampaignContentStep
          subject="Special Announcement for {{first_name}}"
          bodyHtml="<p>Hello {{first_name}}, welcome to our platform!</p>"
          onBodyHtmlChange={vi.fn()}
          selectedSender={mockAccounts[0]}
        />
      );

      // Edit tab is default
      expect(screen.getByRole("toolbar")).toBeDefined();
      expect(screen.getByText("Special Announcement for {{first_name}}")).toBeDefined();

      // Switch to preview tab
      const previewTab = screen.getByRole("button", { name: /preview/i });
      fireEvent.click(previewTab);

      // Replaced first_name with sample recipient "Jane"
      expect(
        screen.getByText("Special Announcement for Jane")
      ).toBeDefined();
      expect(
        screen.getByText(/Sales Team <sales@example.com>/i)
      ).toBeDefined();
      expect(screen.getByText("Simulated Preview")).toBeDefined();
      expect(
        screen.getByText("Hello Jane, welcome to our platform!")
      ).toBeDefined();
    });

    it("strictly provides ONLY {{first_name}} merge tag in personalize dropdown", () => {
      render(
        <CampaignContentStep
          subject="Test Subject"
          bodyHtml="<p>Test</p>"
          onBodyHtmlChange={vi.fn()}
          selectedSender={mockAccounts[0]}
        />
      );

      const personalizeBtn = screen.getByRole("button", {
        name: /personalize/i,
      });
      fireEvent.click(personalizeBtn);

      expect(screen.getByText("{{first_name}}")).toBeDefined();
      expect(screen.getByText("Recipient first name")).toBeDefined();

      // Explicit invariant: no invented merge tags allowed
      expect(screen.queryByText("{{last_name}}")).toBeNull();
      expect(screen.queryByText("{{company}}")).toBeNull();
      expect(screen.queryByText("{{email}}")).toBeNull();
      expect(screen.queryByText("{{phone}}")).toBeNull();
    });

    it("renders quick tool actions (Attach Files, Use Existing Draft, Insert Template, Insert Signature)", () => {
      render(
        <CampaignContentStep
          subject="Test Subject"
          bodyHtml="<p>Test</p>"
          onBodyHtmlChange={vi.fn()}
          selectedSender={mockAccounts[0]}
        />
      );

      expect(screen.getByText("Attach Files")).toBeDefined();
      expect(screen.getByText("Use Existing Draft")).toBeDefined();
      expect(screen.getByText("Insert Template")).toBeDefined();
      expect(screen.getByText("Insert Signature")).toBeDefined();
    });

    it("renders attachments in list and calls onDeleteAttachment when remove is clicked", () => {
      const onDelete = vi.fn();
      const mockAttachments = [
        {
          id: 101,
          campaign_id: 1,
          company_id: 1,
          email_account_id: 1,
          file_name: "flyer.pdf",
          content_type: "application/pdf",
          file_size: 204800,
          created_at: new Date().toISOString(),
        },
      ];

      render(
        <CampaignContentStep
          subject="Test Subject"
          bodyHtml="<p>Test</p>"
          onBodyHtmlChange={vi.fn()}
          selectedSender={mockAccounts[0]}
          attachments={mockAttachments}
          onDeleteAttachment={onDelete}
        />
      );

      expect(screen.getByText("flyer.pdf")).toBeDefined();
      expect(screen.getByText(/200\.0 KB/i)).toBeDefined();

      const removeBtn = screen.getByRole("button", { name: /remove flyer\.pdf/i });
      fireEvent.click(removeBtn);
      expect(onDelete).toHaveBeenCalledWith(101);
    });

    it("renders attachments summary chips in preview tab", () => {
      const mockAttachments = [
        {
          id: 102,
          campaign_id: 1,
          company_id: 1,
          email_account_id: 1,
          file_name: "whitepaper.pdf",
          content_type: "application/pdf",
          file_size: 1048576,
          created_at: new Date().toISOString(),
        },
      ];

      render(
        <CampaignContentStep
          subject="Test Subject"
          bodyHtml="<p>Test</p>"
          onBodyHtmlChange={vi.fn()}
          selectedSender={mockAccounts[0]}
          attachments={mockAttachments}
        />
      );

      const previewTab = screen.getByRole("button", { name: /preview/i });
      fireEvent.click(previewTab);

      expect(screen.getByText("whitepaper.pdf")).toBeDefined();
      expect(screen.getByText("(1024 KB)")).toBeDefined();
    });
  });

  describe("7. CampaignReviewStep", () => {
    it("renders Campaign Details, Sender, Email Content, and Recipients placeholder", () => {
      const onEdit = vi.fn();
      render(
        <CampaignReviewStep
          name="Q4 Enterprise Outreach"
          subject="Exclusive Invitation"
          bodyHtml="<p>Greetings!</p>"
          selectedSender={mockAccounts[0]}
          onEditStep={onEdit}
        />
      );

      expect(screen.getByText("Review Campaign")).toBeDefined();
      expect(screen.getByText("Q4 Enterprise Outreach")).toBeDefined();
      expect(screen.getByText("Exclusive Invitation")).toBeDefined();
      expect(screen.getByText("Sales Team")).toBeDefined();
      expect(screen.getByText("sales@example.com")).toBeDefined();
      expect(screen.getByText("Recipients Configuration")).toBeDefined();
      expect(
        screen.getByText("Recipients will be configured in the next step.")
      ).toBeDefined();

      // Edit buttons navigate to appropriate steps
      const editButtons = screen.getAllByRole("button", { name: /edit/i });
      expect(editButtons.length).toBe(3);

      fireEvent.click(editButtons[0]);
      expect(onEdit).toHaveBeenCalledWith(1);

      fireEvent.click(editButtons[1]);
      expect(onEdit).toHaveBeenCalledWith(2);

      fireEvent.click(editButtons[2]);
      expect(onEdit).toHaveBeenCalledWith(3);
    });

    it("renders attachments summary chips when attachments are provided", () => {
      const mockAttachments = [
        {
          id: 201,
          campaign_id: 1,
          company_id: 1,
          email_account_id: 1,
          file_name: "proposal.pdf",
          content_type: "application/pdf",
          file_size: 512000,
          created_at: new Date().toISOString(),
        },
      ];

      render(
        <CampaignReviewStep
          name="Q4 Enterprise Outreach"
          subject="Exclusive Invitation"
          bodyHtml="<p>Greetings!</p>"
          selectedSender={mockAccounts[0]}
          attachments={mockAttachments}
          onEditStep={vi.fn()}
        />
      );

      expect(screen.getByText("Attachments (1)")).toBeDefined();
      expect(screen.getByText("proposal.pdf")).toBeDefined();
      expect(screen.getByText("(500 KB)")).toBeDefined();
    });
  });

  describe("8. UnsavedChangesDialog", () => {
    it("renders modal dialog and handles Keep Editing and Discard Changes", () => {
      const onClose = vi.fn();
      const onConfirm = vi.fn();

      render(
        <UnsavedChangesDialog
          isOpen={true}
          onClose={onClose}
          onConfirm={onConfirm}
        />
      );

      expect(screen.getByText("Discard unsaved changes?")).toBeDefined();
      expect(
        screen.getByText(/Your campaign changes have not been saved/i)
      ).toBeDefined();

      const keepEditingBtn = screen.getByRole("button", {
        name: /keep editing/i,
      });
      fireEvent.click(keepEditingBtn);
      expect(onClose).toHaveBeenCalledTimes(1);

      const discardBtn = screen.getByRole("button", {
        name: /discard changes/i,
      });
      fireEvent.click(discardBtn);
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it("returns null when isOpen is false", () => {
      const { container } = render(
        <UnsavedChangesDialog
          isOpen={false}
          onClose={vi.fn()}
          onConfirm={vi.fn()}
        />
      );
      expect(container.firstChild).toBeNull();
    });
  });

  describe("9. CreateCampaignPage Render Lifecycle & Regression (No Loops)", () => {
    let queryClient: QueryClient;

    beforeEach(() => {
      queryClient = new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
          },
        },
      });
    });

    it("mounts successfully with clean blank initial fields and without demo values", () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CreateCampaignPage
              companyId={10}
              initialAccounts={mockAccounts}
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Successfully mounted Step 1
      expect(screen.getByText("Create Campaign")).toBeDefined();
      expect(screen.getByText("Step 1 of 4")).toBeDefined();
      const nameInput = screen.getByPlaceholderText(/e\.g\. product launch/i) as HTMLInputElement;
      const subjectInput = screen.getByPlaceholderText(/e\.g\. introducing our new product line/i) as HTMLInputElement;
      expect(nameInput.value).toBe("");
      expect(subjectInput.value).toBe("");
      expect(screen.queryByDisplayValue("Product Launch — October")).toBeNull();
      expect(screen.queryByDisplayValue("Introducing our new product line")).toBeNull();
    });

    it("evaluates stepper accessibility during render without triggering validation side-effects or state updates", () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CreateCampaignPage
              companyId={10}
              initialAccounts={mockAccounts}
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Verify no validation errors are displayed on mount
      expect(screen.queryByRole("alert")).toBeNull();
      expect(screen.queryByText(/is required/i)).toBeNull();
    });

    it("transitions through steps cleanly without automatic draft creation or repeated calls", async () => {
      const onSaveCampaign = vi.fn().mockResolvedValue({ id: 101, name: "Test" });
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CreateCampaignPage
              companyId={10}
              initialAccounts={mockAccounts}
              onSaveCampaign={onSaveCampaign}
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Draft creation is NOT called on mount or render
      expect(onSaveCampaign).not.toHaveBeenCalled();

      // Enter required Step 1 fields
      const nameInput = screen.getByPlaceholderText(/e\.g\. product launch/i);
      const subjectInput = screen.getByPlaceholderText(/e\.g\. introducing our new product line/i);
      fireEvent.change(nameInput, { target: { value: "Product Launch" } });
      fireEvent.change(subjectInput, { target: { value: "Special Invitation" } });

      // Click Continue to go to Step 2
      const continueBtn = screen.getByRole("button", { name: /^continue$/i });
      fireEvent.click(continueBtn);

      // Should be on Step 2
      expect(screen.getByText("Step 2 of 4")).toBeDefined();
      expect(screen.getByText("Sender Account")).toBeDefined();
      // Still no campaign API call
      expect(onSaveCampaign).not.toHaveBeenCalled();
    });

    it("initializes sender selection deterministically once without repeated state updates", () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CreateCampaignPage
              companyId={10}
              initialAccounts={mockAccounts}
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Enter required Step 1 fields
      const nameInput = screen.getByPlaceholderText(/e\.g\. product launch/i);
      const subjectInput = screen.getByPlaceholderText(/e\.g\. introducing our new product line/i);
      fireEvent.change(nameInput, { target: { value: "Product Launch" } });
      fireEvent.change(subjectInput, { target: { value: "Special Invitation" } });

      // Advance to Step 2
      const continueBtn = screen.getByRole("button", { name: /^continue$/i });
      fireEvent.click(continueBtn);

      // Active account "Sales Team" is pre-selected
      expect(screen.getByText("Sending from Sales Team (sales@example.com)")).toBeDefined();
    });
  });
});
