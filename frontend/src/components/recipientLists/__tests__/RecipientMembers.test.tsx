import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { RecipientMembersTable } from "../RecipientMembersTable";
import { AddRecipientMemberModal } from "../AddRecipientMemberModal";
import { EditRecipientMemberModal } from "../EditRecipientMemberModal";
import { DeleteRecipientMemberModal } from "../DeleteRecipientMemberModal";
import { ImportRecipientCsvModal } from "../ImportRecipientCsvModal";
import {
  RecipientMemberEmptyState,
  RecipientMemberSearchEmptyState,
  RecipientMemberErrorState,
} from "../RecipientMemberStates";
import type { RecipientListMember, RecipientListMemberImportResponse } from "../../../types/recipientList";

const mockMembers: RecipientListMember[] = [
  {
    id: 101,
    list_id: 1,
    email: "sarah.jenkins@acme.corp",
    first_name: "Sarah",
    last_name: "Jenkins",
    created_at: "2026-10-28T10:00:00Z",
    updated_at: "2026-10-28T10:00:00Z",
  },
  {
    id: 102,
    list_id: 1,
    email: "michael.chang@cloudscale.io",
    first_name: "Michael",
    last_name: "Chang",
    created_at: "2026-10-24T10:00:00Z",
    updated_at: "2026-10-24T10:00:00Z",
  },
];

describe("RecipientList Member Management Frontend Components (R3)", () => {
  it("renders RecipientMembersTable with email, names, date and action triggers", () => {
    const handleEdit = vi.fn();
    const handleDelete = vi.fn();

    render(
      <RecipientMembersTable
        members={mockMembers}
        onEdit={handleEdit}
        onDelete={handleDelete}
      />
    );

    expect(screen.getByText("sarah.jenkins@acme.corp")).toBeDefined();
    expect(screen.getByText("Sarah")).toBeDefined();
    expect(screen.getByText("Jenkins")).toBeDefined();
    expect(screen.getByText("michael.chang@cloudscale.io")).toBeDefined();

    const editButtons = screen.getAllByTitle("Edit contact");
    fireEvent.click(editButtons[0]);
    expect(handleEdit).toHaveBeenCalledWith(mockMembers[0]);

    const deleteButtons = screen.getAllByTitle("Remove contact");
    fireEvent.click(deleteButtons[1]);
    expect(handleDelete).toHaveBeenCalledWith(mockMembers[1]);
  });

  it("renders AddRecipientMemberModal and validates required email", async () => {
    const handleClose = vi.fn();
    const handleAdd = vi.fn().mockResolvedValue(undefined);

    render(
      <AddRecipientMemberModal
        isOpen={true}
        onClose={handleClose}
        onAdd={handleAdd}
      />
    );

    expect(screen.getByText("Add Recipient Contact")).toBeDefined();

    const submitBtn = screen.getByRole("button", { name: /add contact/i });
    fireEvent.click(submitBtn);

    // Validation error shown
    expect(screen.getByText(/email address is required/i)).toBeDefined();
    expect(handleAdd).not.toHaveBeenCalled();

    // Invalid format
    const emailInput = screen.getByLabelText(/email address/i);
    fireEvent.change(emailInput, { target: { value: "not-an-email" } });
    fireEvent.click(submitBtn);
    expect(screen.getByText(/valid email address/i)).toBeDefined();

    // Valid email and names
    fireEvent.change(emailInput, { target: { value: "alex@venture.com" } });
    const fnInput = screen.getByLabelText(/first name/i);
    fireEvent.change(fnInput, { target: { value: "Alex" } });
    const lnInput = screen.getByLabelText(/last name/i);
    fireEvent.change(lnInput, { target: { value: "Vance" } });

    fireEvent.click(submitBtn);
    await waitFor(() => {
      expect(handleAdd).toHaveBeenCalledWith({
        email: "alex@venture.com",
        first_name: "Alex",
        last_name: "Vance",
      });
      expect(handleClose).toHaveBeenCalled();
    });
  });

  it("renders EditRecipientMemberModal with member values and submits updates", async () => {
    const handleClose = vi.fn();
    const handleSave = vi.fn().mockResolvedValue(undefined);

    render(
      <EditRecipientMemberModal
        isOpen={true}
        member={mockMembers[0]}
        onClose={handleClose}
        onSave={handleSave}
      />
    );

    expect(screen.getByText("Edit Contact")).toBeDefined();
    const emailInput = screen.getByLabelText(/email address/i) as HTMLInputElement;
    expect(emailInput.value).toBe("sarah.jenkins@acme.corp");

    fireEvent.change(emailInput, { target: { value: "sarah.new@acme.corp" } });
    const submitBtn = screen.getByRole("button", { name: /save changes/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(handleSave).toHaveBeenCalledWith(101, {
        email: "sarah.new@acme.corp",
        first_name: "Sarah",
        last_name: "Jenkins",
      });
      expect(handleClose).toHaveBeenCalled();
    });
  });

  it("renders DeleteRecipientMemberModal with confirmation and isolation note", () => {
    const handleClose = vi.fn();
    const handleConfirm = vi.fn().mockResolvedValue(undefined);

    render(
      <DeleteRecipientMemberModal
        isOpen={true}
        member={mockMembers[0]}
        onClose={handleClose}
        onConfirm={handleConfirm}
      />
    );

    expect(screen.getByText("Remove Contact from List?")).toBeDefined();
    expect(screen.getAllByText(/sarah.jenkins@acme.corp/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/does not affect any existing campaign recipients/i)).toBeDefined();

    const removeBtn = screen.getByRole("button", { name: /remove contact/i });
    fireEvent.click(removeBtn);
    expect(handleConfirm).toHaveBeenCalled();
  });

  it("renders ImportRecipientCsvModal and handles CSV preview and summary display", async () => {
    const handleClose = vi.fn();
    const mockSummary: RecipientListMemberImportResponse = {
      total_rows: 5,
      imported_count: 3,
      file_duplicates_count: 1,
      existing_duplicates_count: 1,
      invalid_rows_count: 0,
      invalid_rows: [],
    };
    const handleImport = vi.fn().mockResolvedValue(mockSummary);

    const { container } = render(
      <ImportRecipientCsvModal
        isOpen={true}
        onClose={handleClose}
        onImport={handleImport}
      />
    );

    expect(screen.getByText("Import Contacts from CSV")).toBeDefined();

    // Rejects non-csv file
    const fileInput = container.querySelector("#recipient-csv-file-picker") as HTMLInputElement;
    const badFile = new File(["not a csv"], "doc.pdf", { type: "application/pdf" });
    fireEvent.change(fileInput, { target: { files: [badFile] } });
    expect(screen.getByText(/only csv files/i)).toBeDefined();

    // Select valid csv file
    const validCsv = new File(
      ["email,first_name,last_name\nalice@ex.com,Alice,A\n"],
      "audience.csv",
      { type: "text/csv" }
    );
    fireEvent.change(fileInput, { target: { files: [validCsv] } });

    // File selected badge appears
    await waitFor(() => {
      expect(screen.getByText("audience.csv")).toBeDefined();
    });

    // Trigger import
    const importBtn = screen.getByRole("button", { name: /confirm & import/i });
    fireEvent.click(importBtn);

    // Verify 5-metric breakdown is rendered
    await waitFor(() => {
      expect(screen.getByText("CSV Import Completed")).toBeDefined();
      expect(screen.getByText("Successfully Imported")).toBeDefined();
      expect(screen.getByText("In-File Duplicates")).toBeDefined();
      expect(screen.getByText("Already in List")).toBeDefined();
    });
  });

  it("renders RecipientMemberStates (empty, search-empty, and error states)", () => {
    const handleAdd = vi.fn();
    const handleImport = vi.fn();
    const handleClear = vi.fn();
    const handleRetry = vi.fn();

    const { rerender } = render(
      <RecipientMemberEmptyState onAddRecipient={handleAdd} onImportCsv={handleImport} />
    );
    expect(screen.getByText("No contacts in this list yet")).toBeDefined();

    rerender(
      <RecipientMemberSearchEmptyState searchTerm="test@foo.com" onClearSearch={handleClear} />
    );
    expect(screen.getByText("No contacts found")).toBeDefined();

    rerender(
      <RecipientMemberErrorState error="Network error" onRetry={handleRetry} />
    );
    expect(screen.getByText("Failed to load contacts")).toBeDefined();
  });
});
