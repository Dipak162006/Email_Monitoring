import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CampaignRecipientListSelector } from "../recipients/CampaignRecipientListSelector";
import { recipientListsApi, campaignsApi } from "../../../services/api";
import type { RecipientList } from "../../../types/recipientList";
import type { CampaignRecipientListImportResponse } from "../../../types/campaign";

const mockLists: RecipientList[] = [
  {
    id: 1,
    company_id: 1,
    name: "Keynote Enterprise Leads",
    description: "VP and Director leads",
    created_by_user_id: 1,
    recipient_count: 50,
    created_at: "2026-10-28T10:00:00Z",
    updated_at: "2026-10-28T10:00:00Z",
  },
  {
    id: 2,
    company_id: 1,
    name: "SaaS Founders Batch A",
    description: "Startup founders",
    created_by_user_id: 1,
    recipient_count: 30,
    created_at: "2026-10-24T10:00:00Z",
    updated_at: "2026-10-24T10:00:00Z",
  },
];

describe("CampaignRecipientListSelector (Milestone R4)", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });
    vi.clearAllMocks();
  });

  it("renders recipient lists and supports multi-selection and import", async () => {
    vi.spyOn(recipientListsApi, "listRecipientLists").mockResolvedValue({
      items: mockLists,
      total: 2,
      limit: 100,
      offset: 0,
    });

    const mockImportResponse: CampaignRecipientListImportResponse = {
      total_contacts_processed: 80,
      inserted_count: 70,
      skipped_existing_count: 6,
      skipped_list_duplicates_count: 4,
      recipients: [],
    };
    const importSpy = vi
      .spyOn(campaignsApi, "importRecipientsFromLists")
      .mockResolvedValue(mockImportResponse);

    const onImportSuccess = vi.fn();

    render(
      <QueryClientProvider client={queryClient}>
        <CampaignRecipientListSelector
          companyId={1}
          campaignId={10}
          onImportSuccess={onImportSuccess}
        />
      </QueryClientProvider>
    );

    // Verify lists are rendered
    await waitFor(() => {
      expect(screen.getByText("Keynote Enterprise Leads")).toBeDefined();
      expect(screen.getByText("SaaS Founders Batch A")).toBeDefined();
      expect(screen.getByText("50 contacts")).toBeDefined();
      expect(screen.getByText("30 contacts")).toBeDefined();
    });

    // Select the first list
    const listCard1 = screen.getByText("Keynote Enterprise Leads");
    fireEvent.click(listCard1);

    expect(screen.getByText(/1 list selected/i)).toBeDefined();
    expect(screen.getByText(/50 potential contacts/i)).toBeDefined();

    // Select the second list
    const listCard2 = screen.getByText("SaaS Founders Batch A");
    fireEvent.click(listCard2);

    expect(screen.getByText(/2 lists selected/i)).toBeDefined();
    expect(screen.getByText(/80 potential contacts/i)).toBeDefined();

    // Trigger Import
    const importBtn = screen.getByRole("button", { name: /import 2 lists/i });
    fireEvent.click(importBtn);

    await waitFor(() => {
      expect(importSpy).toHaveBeenCalledWith(1, 10, {
        list_ids: [1, 2],
      });
      expect(onImportSuccess).toHaveBeenCalledWith(mockImportResponse);
      expect(screen.getByText("Recipient Lists Imported Successfully")).toBeDefined();
      expect(screen.getByText("Added to Audience")).toBeDefined();
      expect(screen.getByText("70")).toBeDefined();
      expect(screen.getByText("Already in Campaign")).toBeDefined();
      expect(screen.getByText("6")).toBeDefined();
      expect(screen.getByText("Duplicates in Lists")).toBeDefined();
      expect(screen.getByText("4")).toBeDefined();
    });
  });

  it("filters recipient lists by search input", async () => {
    vi.spyOn(recipientListsApi, "listRecipientLists").mockResolvedValue({
      items: mockLists,
      total: 2,
      limit: 100,
      offset: 0,
    });

    render(
      <QueryClientProvider client={queryClient}>
        <CampaignRecipientListSelector companyId={1} campaignId={10} />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText("Keynote Enterprise Leads")).toBeDefined();
    });

    const searchInput = screen.getByPlaceholderText("Search lists...");
    fireEvent.change(searchInput, { target: { value: "Founders" } });

    expect(screen.queryByText("Keynote Enterprise Leads")).toBeNull();
    expect(screen.getByText("SaaS Founders Batch A")).toBeDefined();
  });
});
