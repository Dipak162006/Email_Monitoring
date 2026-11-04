import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { AuthorizedEmailAccount, EmailSignatureItem } from "../../../types/emails";
import { signaturesApi } from "../../../services/api";
import { CampaignContentStep } from "../CampaignContentStep";
import { CreateCampaignPage } from "../../../pages/CreateCampaignPage";

const mockAccounts: AuthorizedEmailAccount[] = [
  {
    id: 1,
    company_id: 10,
    email_address: "sender@example.com",
    name: "Sender Account",
    provider: "GMAIL",
    is_active: true,
    is_sync_enabled: true,
    is_verified: true,
  },
];

const mockSignature: EmailSignatureItem = {
  id: 401,
  company_id: 10,
  email_account_id: 1,
  name: "Official Signoff",
  body_html: "<p><b>Jane Doe</b><br/>VP Marketing</p>",
  body_text: "Jane Doe\nVP Marketing",
  is_default: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

describe("Campaign Signature Insertion & Deduplication", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    vi.clearAllMocks();
    vi.spyOn(signaturesApi, "listSignatures").mockResolvedValue([mockSignature]);
  });

  it("appends signature exactly once when selecting signature in CampaignContentStep", async () => {
    const onBodyChange = vi.fn();
    const onSelectSig = vi.fn();

    render(
      <QueryClientProvider client={queryClient}>
        <CampaignContentStep
          subject="Exclusive Announcement"
          bodyHtml="<p>Please check the attached report.</p>"
          bodyText="Please check the attached report."
          onBodyHtmlChange={onBodyChange}
          onSelectSignature={onSelectSig}
          selectedAccountId={1}
          companyId={10}
        />
      </QueryClientProvider>
    );

    // Open signature modal
    const insertBtn = screen.getByRole("button", { name: /insert signature/i });
    fireEvent.click(insertBtn);

    await waitFor(() => {
      expect(screen.getByText("Official Signoff")).toBeDefined();
    });

    const sigCard = screen.getByText("Official Signoff").closest("div");
    if (sigCard) fireEvent.click(sigCard);

    // onBodyChange must have been called exactly once with signature appended
    expect(onBodyChange).toHaveBeenCalledTimes(1);
    const [htmlArg, textArg] = onBodyChange.mock.calls[0];

    // Preserves original content
    expect(htmlArg).toContain("<p>Please check the attached report.</p>");
    // Contains signature
    expect(htmlArg).toContain("Jane Doe");
    expect(htmlArg).toContain("VP Marketing");

    // Signature only appears once (count occurrences of "VP Marketing")
    const occurrencesHtml = (htmlArg.match(/VP Marketing/g) || []).length;
    expect(occurrencesHtml).toBe(1);

    if (textArg) {
      expect(textArg).toContain("Please check the attached report.");
      const occurrencesText = (textArg.match(/VP Marketing/g) || []).length;
      expect(occurrencesText).toBe(1);
    }

    // onSelectSig was also notified
    expect(onSelectSig).toHaveBeenCalledWith(mockSignature);
  });

  it("repeated callback execution or re-selecting existing signature does NOT duplicate signature", async () => {
    const onBodyChange = vi.fn();

    // Already has signature in body
    const initialHtml = "<p>Existing draft body</p><br/><br/><p><b>Jane Doe</b><br/>VP Marketing</p>";
    const initialText = "Existing draft body\n\nJane Doe\nVP Marketing";

    render(
      <QueryClientProvider client={queryClient}>
        <CampaignContentStep
          subject="Follow-up note"
          bodyHtml={initialHtml}
          bodyText={initialText}
          onBodyHtmlChange={onBodyChange}
          selectedAccountId={1}
          companyId={10}
        />
      </QueryClientProvider>
    );

    const insertBtn = screen.getByRole("button", { name: /insert signature/i });
    fireEvent.click(insertBtn);

    await waitFor(() => {
      expect(screen.getByText("Official Signoff")).toBeDefined();
    });

    const sigCard = screen.getByText("Official Signoff").closest("div");
    if (sigCard) fireEvent.click(sigCard);

    // Signature was already present; onBodyChange should not be called to append duplicate
    expect(onBodyChange).not.toHaveBeenCalled();
  });

  it("end-to-end CreateCampaignPage appends signature only once without duplicate callback execution", async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CreateCampaignPage companyId={10} initialAccounts={mockAccounts} />
        </MemoryRouter>
      </QueryClientProvider>
    );

    // Step 1: Details
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. product launch/i), {
      target: { value: "Q4 Campaign" },
    });
    fireEvent.change(screen.getByPlaceholderText(/e\.g\. introducing our new product line/i), {
      target: { value: "Special Invitation" },
    });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    // Step 2: Select sender
    await waitFor(() => {
      expect(screen.getByText("sender@example.com")).toBeDefined();
    });
    const senderCard = screen.getByText("sender@example.com").closest("div");
    if (senderCard) fireEvent.click(senderCard);
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    // Step 3: Content Step
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /insert signature/i })).toBeDefined();
    });

    // Insert signature
    fireEvent.click(screen.getByRole("button", { name: /insert signature/i }));
    await waitFor(() => {
      expect(screen.getByText("Official Signoff")).toBeDefined();
    });

    const sigCard = screen.getByText("Official Signoff").closest("div");
    if (sigCard) fireEvent.click(sigCard);

    // Toast appears
    await waitFor(() => {
      expect(screen.getByText("Signature inserted.")).toBeDefined();
    });

    // Step 4: Continue to review page to verify the final body content
    const step3Continue = screen.getByRole("button", { name: /continue/i });
    fireEvent.click(step3Continue);

    await waitFor(() => {
      expect(screen.getByText("Review Campaign")).toBeDefined();
    });

    // Check occurrences in preview text
    const previewContainer = document.body;
    const bodyContent = previewContainer.textContent || "";
    const occurrences = (bodyContent.match(/VP Marketing/g) || []).length;
    // In preview, "VP Marketing" should appear at most once (or once in the preview panel)
    expect(occurrences).toBe(1);
  });
});
