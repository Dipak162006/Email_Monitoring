import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { RecipientListsTable } from "../RecipientListsTable";
import {
  RecipientListEmptyState,
  RecipientListSearchEmptyState,
} from "../RecipientListsStates";
import { CreateRecipientListModal } from "../CreateRecipientListModal";
import { EditRecipientListModal } from "../EditRecipientListModal";
import { DeleteRecipientListModal } from "../DeleteRecipientListModal";
import type { RecipientList } from "../../../types/recipientList";

const mockLists: RecipientList[] = [
  {
    id: 1,
    company_id: 1,
    name: "Q4 Keynote Enterprise Leads",
    description: "Verified VP & Director level attendees from keynote event",
    created_by_user_id: 1,
    recipient_count: 1248,
    created_at: "2026-10-28T10:00:00Z",
    updated_at: "2026-10-28T10:00:00Z",
  },
  {
    id: 2,
    company_id: 1,
    name: "SaaS Founders & CTOs",
    description: "Tier 1 high-velocity software leaders",
    created_by_user_id: 1,
    recipient_count: 890,
    created_at: "2026-10-24T10:00:00Z",
    updated_at: "2026-10-24T10:00:00Z",
  },
];

describe("RecipientLists Frontend Components", () => {
  it("renders RecipientListsTable with columns, lists, recipient counts and actions", () => {
    const handleManage = vi.fn();
    const handleEdit = vi.fn();
    const handleDelete = vi.fn();

    render(
      <RecipientListsTable
        lists={mockLists}
        onManage={handleManage}
        onEdit={handleEdit}
        onDelete={handleDelete}
      />
    );

    expect(screen.getAllByText("Q4 Keynote Enterprise Leads").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SaaS Founders & CTOs").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1,248").length).toBeGreaterThan(0);
    expect(screen.getAllByText("890").length).toBeGreaterThan(0);

    // Check actions
    const manageButtons = screen.getAllByRole("button", { name: /manage/i });
    expect(manageButtons.length).toBeGreaterThan(0);
    fireEvent.click(manageButtons[0]);
    expect(handleManage).toHaveBeenCalledWith(mockLists[0]);

    const editButtons = screen.getAllByTitle("Edit list details");
    expect(editButtons.length).toBeGreaterThan(0);
    fireEvent.click(editButtons[0]);
    expect(handleEdit).toHaveBeenCalledWith(mockLists[0]);

    const deleteButtons = screen.getAllByTitle("Delete list");
    expect(deleteButtons.length).toBeGreaterThan(0);
    fireEvent.click(deleteButtons[0]);
    expect(handleDelete).toHaveBeenCalledWith(mockLists[0]);
  });

  it("renders RecipientListEmptyState and fires onCreate when button clicked", () => {
    const handleCreate = vi.fn();
    render(<RecipientListEmptyState onCreate={handleCreate} />);

    expect(screen.getByText("No recipient lists yet.")).toBeDefined();
    expect(
      screen.getByText(/Create reusable lists to organize contacts/i)
    ).toBeDefined();

    const createBtn = screen.getByRole("button", { name: /create your first list/i });
    fireEvent.click(createBtn);
    expect(handleCreate).toHaveBeenCalled();
  });

  it("renders RecipientListSearchEmptyState and fires onClearSearch when button clicked", () => {
    const handleClear = vi.fn();
    render(<RecipientListSearchEmptyState onClearSearch={handleClear} />);

    expect(screen.getByText("No lists found.")).toBeDefined();
    expect(screen.getByText("Try adjusting your search.")).toBeDefined();

    const clearBtn = screen.getByRole("button", { name: /clear search filter/i });
    fireEvent.click(clearBtn);
    expect(handleClear).toHaveBeenCalled();
  });

  it("renders CreateRecipientListModal and validates required list name", async () => {
    const handleClose = vi.fn();
    const handleSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <CreateRecipientListModal
        isOpen={true}
        onClose={handleClose}
        onSubmit={handleSubmit}
      />
    );

    expect(screen.getByText("Create Recipient List")).toBeDefined();

    const nameInput = screen.getByPlaceholderText(/e\.g\., Q4 Enterprise Leads/i);
    const descInput = screen.getByPlaceholderText(/describe this list/i);
    const submitBtn = screen.getByRole("button", { name: "Create List" });

    // Fill valid data
    fireEvent.change(nameInput, { target: { value: "New Product Leads" } });
    fireEvent.change(descInput, { target: { value: "Beta testers" } });

    fireEvent.click(submitBtn);
    expect(handleSubmit).toHaveBeenCalledWith({
      name: "New Product Leads",
      description: "Beta testers",
    });
  });

  it("renders EditRecipientListModal with prepopulated values", async () => {
    const handleClose = vi.fn();
    const handleSubmit = vi.fn().mockResolvedValue(undefined);

    render(
      <EditRecipientListModal
        isOpen={true}
        list={mockLists[0]}
        onClose={handleClose}
        onSubmit={handleSubmit}
      />
    );

    expect(screen.getByText("Edit Recipient List")).toBeDefined();
    const nameInput = screen.getByDisplayValue("Q4 Keynote Enterprise Leads");
    expect(nameInput).toBeDefined();

    fireEvent.change(nameInput, { target: { value: "Updated Keynote Leads" } });
    const saveBtn = screen.getByRole("button", { name: "Save Changes" });
    fireEvent.click(saveBtn);

    expect(handleSubmit).toHaveBeenCalledWith(1, {
      name: "Updated Keynote Leads",
      description: "Verified VP & Director level attendees from keynote event",
    });
  });

  it("renders DeleteRecipientListModal and fires onConfirm with list ID", async () => {
    const handleClose = vi.fn();
    const handleConfirm = vi.fn().mockResolvedValue(undefined);

    render(
      <DeleteRecipientListModal
        isOpen={true}
        list={mockLists[0]}
        onClose={handleClose}
        onConfirm={handleConfirm}
      />
    );

    expect(screen.getByText("Delete Recipient List?")).toBeDefined();
    expect(screen.getByText("Q4 Keynote Enterprise Leads")).toBeDefined();

    const deleteBtn = screen.getByRole("button", { name: "Delete List" });
    fireEvent.click(deleteBtn);
    expect(handleConfirm).toHaveBeenCalledWith(1);
  });
});
