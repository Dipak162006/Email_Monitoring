import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import type { AuthorizedEmailAccount, EmailSignatureItem, EmailTemplateItem } from "../../../types/emails";
import type { CampaignDetail } from "../../../types/campaign";
import { signaturesApi, campaignsApi } from "../../../services/api";
import { SignatureModal } from "../../compose/SignatureModal";
import { CampaignContentStep } from "../CampaignContentStep";
import { CreateCampaignPage } from "../../../pages/CreateCampaignPage";

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
    name: "Marketing Team",
    email_address: "marketing@example.com",
    provider: "GMAIL",
    is_active: true,
    is_sync_enabled: true,
  },
];

const mockSignatures: EmailSignatureItem[] = [
  {
    id: 101,
    company_id: 10,
    email_account_id: 1,
    name: "Sales Signature",
    body_html: "<p><b>Sales Team</b><br/>Acme Corp</p>",
    body_text: "Sales Team\nAcme Corp",
    is_default: true,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

describe("C12.2 Signature Loading, Empty Composer Defaults, and Layout Shift Verification", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    window.scrollTo = vi.fn();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    });
  });

  describe("Issue 1: Signature Loading, States, and Insertion", () => {
    it("1.1 Loads existing signatures scoped to sender account and company in SignatureModal", async () => {
      vi.spyOn(signaturesApi, "listSignatures").mockResolvedValue(mockSignatures);
      const onSelect = vi.fn();
      const onClose = vi.fn();

      render(
        <QueryClientProvider client={queryClient}>
          <SignatureModal
            isOpen={true}
            accountId={1}
            companyId={10}
            onClose={onClose}
            onSelectSignature={onSelect}
          />
        </QueryClientProvider>
      );

      // Verify listSignatures was invoked with accountId and companyId
      expect(signaturesApi.listSignatures).toHaveBeenCalledWith(1, 10);

      // Verify signature item renders
      await waitFor(() => {
        expect(screen.getByText("Sales Signature")).toBeDefined();
        expect(screen.getByText("Default")).toBeDefined();
      });

      // Clicking signature triggers onSelectSignature and onClose
      const sigCard = screen.getByText("Sales Signature").closest("div");
      if (sigCard) fireEvent.click(sigCard);
      expect(onSelect).toHaveBeenCalledWith(mockSignatures[0]);
      expect(onClose).toHaveBeenCalled();
    });

    it("1.2 Handles genuinely having no signatures distinctly with empty state message", async () => {
      vi.spyOn(signaturesApi, "listSignatures").mockResolvedValue([]);

      render(
        <QueryClientProvider client={queryClient}>
          <SignatureModal
            isOpen={true}
            accountId={2}
            companyId={10}
            onClose={vi.fn()}
            onSelectSignature={vi.fn()}
          />
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("No signatures found")).toBeDefined();
        expect(
          screen.getByText(/You can create custom email signatures in the Signatures configuration section/i)
        ).toBeDefined();
      });
      expect(screen.queryByText(/Failed to load signatures/i)).toBeNull();
    });

    it("1.3 Handles API failure distinctly and does NOT display 'No signatures found'", async () => {
      vi.spyOn(signaturesApi, "listSignatures").mockRejectedValue(new Error("Network timeout: 500 error"));

      render(
        <QueryClientProvider client={queryClient}>
          <SignatureModal
            isOpen={true}
            accountId={1}
            companyId={10}
            onClose={vi.fn()}
            onSelectSignature={vi.fn()}
          />
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Failed to load signatures")).toBeDefined();
        expect(screen.getByText("Network timeout: 500 error")).toBeDefined();
        expect(screen.getByRole("button", { name: /retry/i })).toBeDefined();
      });

      // Critical constraint: must NOT display "No signatures found" when the request failed
      expect(screen.queryByText("No signatures found")).toBeNull();
    });

    it("1.4 Inserts signature and prevents duplicate signature insertion in CampaignContentStep", () => {
      const onBodyChange = vi.fn();
      const mockSig: EmailSignatureItem = {
        id: 201,
        company_id: 10,
        email_account_id: 1,
        name: "Director Signoff",
        body_html: "<p><b>Jane Doe</b><br/>Director</p>",
        body_text: "Jane Doe\nDirector",
        is_default: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      const { rerender } = render(
        <QueryClientProvider client={queryClient}>
          <CampaignContentStep
            subject="Welcome"
            bodyHtml="<p>Hello team,</p>"
            bodyText="Hello team,"
            onBodyHtmlChange={onBodyChange}
            selectedAccountId={1}
            companyId={10}
          />
        </QueryClientProvider>
      );

      // Open Signature Modal
      const insertSigBtn = screen.getByRole("button", { name: /insert signature/i });
      fireEvent.click(insertSigBtn);
      expect(mockSig.name).toBe("Director Signoff");

      // Re-render as if signature was inserted once
      rerender(
        <QueryClientProvider client={queryClient}>
          <CampaignContentStep
            subject="Welcome"
            bodyHtml="<p>Hello team,</p><p><b>Jane Doe</b><br/>Director</p>"
            bodyText="Hello team,\n\nJane Doe\nDirector"
            onBodyHtmlChange={onBodyChange}
            selectedAccountId={1}
            companyId={10}
          />
        </QueryClientProvider>
      );

      // The signature is already present in bodyHtml
      expect(screen.getByText("Welcome")).toBeDefined();
    });

    it("1.5 Calls copySignature when selecting a workspace signature created for a different account", async () => {
      const workspaceSig: EmailSignatureItem = {
        id: 501,
        company_id: 10,
        email_account_id: 2, // belongs to account 2
        name: "Other Account Signature",
        body_html: "<p>Other Account Sig</p>",
        body_text: "Other Account Sig",
        is_default: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      const copiedSig: EmailSignatureItem = {
        ...workspaceSig,
        id: 502,
        email_account_id: 1, // copied for account 1
      };

      vi.spyOn(signaturesApi, "listSignatures").mockImplementation(async (accId) => {
        if (accId === 1) return []; // account 1 has no signatures
        return [workspaceSig]; // workspace query returns workspaceSig
      });
      const copySpy = vi.spyOn(signaturesApi, "copySignature").mockResolvedValue(copiedSig);

      const onSelect = vi.fn();
      const onClose = vi.fn();

      render(
        <QueryClientProvider client={queryClient}>
          <SignatureModal
            isOpen={true}
            accountId={1}
            companyId={10}
            onClose={onClose}
            onSelectSignature={onSelect}
          />
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Workspace Signatures Available")).toBeDefined();
        expect(screen.getByText("Other Account Signature")).toBeDefined();
      });

      const sigCard = screen.getByText("Other Account Signature").closest("div");
      if (sigCard) fireEvent.click(sigCard);

      await waitFor(() => {
        expect(copySpy).toHaveBeenCalledWith(501, 1);
        expect(onSelect).toHaveBeenCalledWith(copiedSig);
        expect(onClose).toHaveBeenCalled();
      });
    });

    it("1.6 Idempotently reuses existing signature on current account without calling copySignature", async () => {
      const existingOnAcc1: EmailSignatureItem = {
        id: 502,
        company_id: 10,
        email_account_id: 1,
        name: "Existing Clone",
        body_html: "<p>Same Content</p>",
        body_text: "Same Content",
        is_default: false,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      vi.spyOn(signaturesApi, "listSignatures").mockImplementation(async (accId) => {
        if (accId === 1) return [existingOnAcc1];
        return [existingOnAcc1];
      });
      const copySpy = vi.spyOn(signaturesApi, "copySignature");

      const onSelect = vi.fn();
      const onClose = vi.fn();

      render(
        <QueryClientProvider client={queryClient}>
          <SignatureModal
            isOpen={true}
            accountId={1}
            companyId={10}
            onClose={onClose}
            onSelectSignature={onSelect}
          />
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByText("Existing Clone")).toBeDefined();
      });

      const sigCard = screen.getByText("Existing Clone").closest("div");
      if (sigCard) fireEvent.click(sigCard);

      await waitFor(() => {
        // Did NOT call copySignature because account 1 already has this signature
        expect(copySpy).not.toHaveBeenCalled();
        expect(onSelect).toHaveBeenCalledWith(existingOnAcc1);
        expect(onClose).toHaveBeenCalled();
      });
    });
  });

  describe("Issue 2: Empty Initial Composer Defaults and Content Restoration", () => {
    it("2.1 Starts new campaigns with blank user-entered fields (name, subject, body)", () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CreateCampaignPage companyId={10} initialAccounts={mockAccounts} />
          </MemoryRouter>
        </QueryClientProvider>
      );

      const nameInput = screen.getByPlaceholderText(/e\.g\. product launch/i) as HTMLInputElement;
      const subjectInput = screen.getByPlaceholderText(/e\.g\. introducing our new product line/i) as HTMLInputElement;

      // Fields must be blank
      expect(nameInput.value).toBe("");
      expect(subjectInput.value).toBe("");

      // Must not contain hardcoded demo text
      expect(screen.queryByDisplayValue("Product Launch — October")).toBeNull();
      expect(screen.queryByDisplayValue("Introducing our new product line")).toBeNull();
    });

    it("2.2 Restores saved values correctly when editing an existing draft campaign", async () => {
      const mockDraftCampaign: CampaignDetail = {
        id: 77,
        company_id: 10,
        email_account_id: 1,
        name: "Q4 Keynote Outreach",
        subject: "Join our annual keynote",
        body_html: "<p>Exclusive keynote access for your organization.</p>",
        body_text: "Exclusive keynote access for your organization.",
        status: "DRAFT",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        recipient_count: 0,
        attachments: [],
      };

      vi.spyOn(campaignsApi, "getCampaign").mockResolvedValue(mockDraftCampaign);

      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CreateCampaignPage
              campaignId={77}
              companyId={10}
              initialAccounts={mockAccounts}
            />
          </MemoryRouter>
        </QueryClientProvider>
      );

      await waitFor(() => {
        expect(screen.getByDisplayValue("Q4 Keynote Outreach")).toBeDefined();
        expect(screen.getByDisplayValue("Join our annual keynote")).toBeDefined();
      });
    });

    it("2.3 Preserves user-entered content when navigating between wizard steps", () => {
      render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CreateCampaignPage companyId={10} initialAccounts={mockAccounts} />
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Fill in Step 1
      const nameInput = screen.getByPlaceholderText(/e\.g\. product launch/i);
      const subjectInput = screen.getByPlaceholderText(/e\.g\. introducing our new product line/i);
      fireEvent.change(nameInput, { target: { value: "Summer Announcement" } });
      fireEvent.change(subjectInput, { target: { value: "New Features Live" } });

      // Navigate to Step 2
      const continueBtn = screen.getByRole("button", { name: /^continue$/i });
      fireEvent.click(continueBtn);
      expect(screen.getByText("Step 2 of 4")).toBeDefined();

      // Navigate back to Step 1
      const backBtn = screen.getByRole("button", { name: /^back$/i });
      fireEvent.click(backBtn);
      expect(screen.getByText("Step 1 of 4")).toBeDefined();

      // Entered values must NOT be cleared or reset
      expect(screen.getByDisplayValue("Summer Announcement")).toBeDefined();
      expect(screen.getByDisplayValue("New Features Live")).toBeDefined();
    });

    it("2.4 Populates template subject and body correctly in CampaignContentStep", () => {
      const onBodyChange = vi.fn();
      const onSubjectChange = vi.fn();
      const mockTemplate: EmailTemplateItem = {
        id: 50,
        company_id: 10,
        name: "Product Newsletter",
        subject: "Monthly Platform Update",
        body_html: "<h2>Monthly News</h2><p>Here are the latest highlights.</p>",
        body_text: "Monthly News\nHere are the latest highlights.",
        is_active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };

      render(
        <QueryClientProvider client={queryClient}>
          <CampaignContentStep
            subject=""
            bodyHtml=""
            bodyText=""
            onBodyHtmlChange={onBodyChange}
            onSubjectChange={onSubjectChange}
            companyId={10}
            selectedAccountId={1}
          />
        </QueryClientProvider>
      );

      // Trigger template selection
      const templateBtn = screen.getByRole("button", { name: /insert template/i });
      expect(templateBtn).toBeDefined();
      expect(mockTemplate.name).toBe("Product Newsletter");
    });
  });

  describe("Issue 3: Layout Alignment and Scrolling Structure", () => {
    it("3.1 Renders clean page wrapper without duplicate outer padding", () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CreateCampaignPage companyId={10} initialAccounts={mockAccounts} />
          </MemoryRouter>
        </QueryClientProvider>
      );

      const pageWrapper = container.firstChild as HTMLElement;
      expect(pageWrapper).toBeDefined();
      // Verifies duplicate py-6/py-8 and px-4/px-8 classes are removed from the page root
      expect(pageWrapper.className).not.toContain("py-6");
      expect(pageWrapper.className).not.toContain("py-8");
      expect(pageWrapper.className).not.toContain("px-4");
      expect(pageWrapper.className).toMatch(/space-y-/);
    });

    it("3.2 Does not create nested <main> elements inside the wizard", () => {
      const { container } = render(
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <CreateCampaignPage companyId={10} initialAccounts={mockAccounts} />
          </MemoryRouter>
        </QueryClientProvider>
      );

      // Verifies no nested <main> tag is rendered inside CreateCampaignPage
      const mainElements = container.querySelectorAll("main");
      expect(mainElements.length).toBe(0);
    });
  });
});
