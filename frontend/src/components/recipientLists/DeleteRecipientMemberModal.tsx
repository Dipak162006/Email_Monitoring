import React, { useEffect } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "../ui/Button";
import type { RecipientListMember } from "../../types/recipientList";

interface DeleteRecipientMemberModalProps {
  isOpen: boolean;
  member: RecipientListMember | null;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  isLoading?: boolean;
}

export const DeleteRecipientMemberModal: React.FC<DeleteRecipientMemberModalProps> = ({
  isOpen,
  member,
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

  if (!isOpen || !member) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-recipient-member-title"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 text-left animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto"
        style={{ width: "min(calc(100vw - 32px), 440px)" }}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center shrink-0">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="flex flex-col min-w-0">
            <h3 id="delete-recipient-member-title" className="text-sm font-bold text-slate-900 truncate">
              Remove Contact from List?
            </h3>
            <span className="text-xs text-slate-500 font-mono truncate">
              {member.email}
            </span>
          </div>
        </div>

        {/* Warning Body */}
        <div className="space-y-2 mb-6 text-xs text-slate-600 leading-relaxed">
          <p>
            Are you sure you want to remove <span className="font-semibold text-slate-900 font-mono break-all">{member.email}</span> from this recipient list?
          </p>
          <div className="p-2.5 rounded-lg bg-amber-50 border border-amber-200/80 text-[11px] text-amber-800">
            <strong>Note:</strong> This only removes the contact from this recipient list. It does not affect any existing campaign recipients or outreach history.
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-2.5">
          <Button
            type="button"
            variant="outline"
            disabled={isLoading}
            onClick={onClose}
            className="px-3.5 py-2 text-xs font-medium rounded-xl"
          >
            Cancel
          </Button>
          <button
            type="button"
            disabled={isLoading}
            onClick={onConfirm}
            className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-medium shadow-sm transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Removing...</span>
              </>
            ) : (
              <span>Remove Contact</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
