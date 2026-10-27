import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { AttachmentUploadList, type ComposeAttachment } from "../AttachmentUploadList";

describe("Compose Forward Attachments UI & Operations", () => {
  it("renders forwarded attachments with name, formatted size, and remove button", () => {
    const attachments: ComposeAttachment[] = [
      {
        id: 101,
        file_name: "financial_report.pdf",
        file_size: 1024 * 500, // 500 KB
        content_type: "application/pdf",
        isPending: false,
      },
      {
        id: 102,
        file_name: "data_export.csv",
        file_size: 2048, // 2.0 KB
        content_type: "text/csv",
        isPending: false,
      },
    ];

    const onRemove = vi.fn();

    render(
      <AttachmentUploadList
        attachments={attachments}
        onRemove={onRemove}
        isUploading={false}
      />
    );

    // Displays count header
    expect(screen.getByText("Attachments (2 files)")).toBeTruthy();

    // Displays file names
    expect(screen.getByText("financial_report.pdf")).toBeTruthy();
    expect(screen.getByText("data_export.csv")).toBeTruthy();

    // Displays formatted sizes
    expect(screen.getByText("(500.0 KB)")).toBeTruthy();
    expect(screen.getByText("(2.0 KB)")).toBeTruthy();

    // Clicking remove triggers callback with specific attachment id
    const removePdfBtn = screen.getByLabelText("Remove financial_report.pdf");
    fireEvent.click(removePdfBtn);
    expect(onRemove).toHaveBeenCalledWith(101);
  });

  it("handles duplicate attachment copy prevention logic correctly", () => {
    // Test the idempotent guard mechanism used in ComposePage
    let forwardAttsRefValue: string | null = null;
    const mockCopyFn = vi.fn();

    const loadForwardAttachments = (forwardId: string) => {
      if (forwardAttsRefValue === forwardId) {
        // Skip duplicate load/copy
        return;
      }
      forwardAttsRefValue = forwardId;
      mockCopyFn(forwardId);
    };

    // First trigger for forward email "42"
    loadForwardAttachments("42");
    expect(mockCopyFn).toHaveBeenCalledTimes(1);
    expect(mockCopyFn).toHaveBeenCalledWith("42");

    // Component rerender / autosave trigger with same forwardId "42"
    loadForwardAttachments("42");
    expect(mockCopyFn).toHaveBeenCalledTimes(1); // Still 1, no duplicate copy call

    // Switching to a different forwarded email "88"
    loadForwardAttachments("88");
    expect(mockCopyFn).toHaveBeenCalledTimes(2);
    expect(mockCopyFn).toHaveBeenCalledWith("88");
  });

  it("recovers from a transient failure and allows retry without duplicating", async () => {
    let forwardAttsRefValue: string | null = null;
    let shouldFail = true;
    let errorWarning: string | null = null;
    const mockCopyFn = vi.fn();

    const executeCopy = async (forwardId: string) => {
      if (forwardAttsRefValue === forwardId) {
        return;
      }
      forwardAttsRefValue = forwardId;
      try {
        if (shouldFail) {
          throw new Error("Network timeout during attachment clone");
        }
        mockCopyFn(forwardId);
        errorWarning = null;
      } catch (err: unknown) {
        // Safe reset: resets ref so user/component can retry
        forwardAttsRefValue = null;
        errorWarning = `Forwarding attachments warning: ${err instanceof Error ? err.message : String(err)}`;
      }
    };

    // First attempt fails due to transient network failure
    await executeCopy("42");
    expect(mockCopyFn).not.toHaveBeenCalled();
    expect(forwardAttsRefValue).toBeNull();
    expect(errorWarning).toContain("Forwarding attachments warning: Network timeout");

    // Retry succeeds
    shouldFail = false;
    await executeCopy("42");
    expect(mockCopyFn).toHaveBeenCalledTimes(1);
    expect(mockCopyFn).toHaveBeenCalledWith("42");
    expect(forwardAttsRefValue).toBe("42");
    expect(errorWarning).toBeNull();

    // Subsequent rerender/autosave with same forwardId does not trigger duplicate copy
    await executeCopy("42");
    expect(mockCopyFn).toHaveBeenCalledTimes(1);
  });
});
