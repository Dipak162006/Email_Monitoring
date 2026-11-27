import React, { useEffect } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import type { RecipientList } from "../../types/recipientList";
import { Button } from "../ui/Button";

interface DeleteRecipientListModalProps {
  isOpen: boolean;
  list: RecipientList | null;
  onClose: () => void;
  onConfirm: (listId: number) => Promise<void>;
  isLoading?: boolean;
}

export const DeleteRecipientListModal: React.FC<DeleteRecipientListModalProps> = ({
  isOpen,
  list,
  onClose,
  onConfirm,
  isLoading = false,
}) => {
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isLoading, onClose]);

  if (!isOpen || !list) return null;

  const handleConfirm = async () => {
    await onConfirm(list.id);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-recipient-list-title"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 text-left animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto w-full"
        style={{ maxWidth: "460px" }}
      >
        {/* Header */}
        <div className="flex items-start gap-3.5 mb-4">
          <div className="w-10 h-10 rounded-full bg-rose-50 border border-rose-100 text-rose-600 flex items-center justify-center shrink-0">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="flex flex-col min-w-0">
            <h3
              id="delete-recipient-list-title"
              className="text-base font-bold text-slate-900 leading-tight"
            >
              Delete Recipient List?
            </h3>
            <span className="text-xs font-semibold text-rose-600 mt-1 truncate">
              {list.name}
            </span>
          </div>
        </div>

        {/* Description */}
        <p className="text-xs text-slate-600 mb-6 leading-relaxed">
          Are you sure you want to delete this recipient list? Deleting the list will remove
          the reusable list and its contacts. Existing campaign recipient records and
          campaign history will <strong className="text-slate-900 font-semibold">not</strong> be affected.
        </p>

        {/* Actions */}
        <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={isLoading}
            className="text-xs font-semibold px-4 py-2 rounded-xl"
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={handleConfirm}
            disabled={isLoading}
            className="bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold px-4 py-2 rounded-xl shadow-xs"
          >
            {isLoading ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                Deleting...
              </>
            ) : (
              "Delete List"
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};
