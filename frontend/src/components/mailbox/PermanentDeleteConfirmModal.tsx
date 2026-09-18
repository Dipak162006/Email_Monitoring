import React from "react";
import { AlertTriangle, X, Loader2, Trash2 } from "lucide-react";
import { Button } from "../ui/Button";

interface PermanentDeleteConfirmModalProps {
  isOpen: boolean;
  count: number;
  isDeleting: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export const PermanentDeleteConfirmModal: React.FC<PermanentDeleteConfirmModalProps> = ({
  isOpen,
  count,
  isDeleting,
  onClose,
  onConfirm,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div
        className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        role="dialog"
        aria-modal="true"
        aria-labelledby="perm-delete-modal-title"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-rose-50/50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600 shrink-0">
              <AlertTriangle className="h-4 w-4" />
            </div>
            <h3 id="perm-delete-modal-title" className="text-sm font-bold text-slate-900">
              {count === 1 ? "Permanently Delete Email" : `Permanently Delete ${count} Emails`}
            </h3>
          </div>
          <button
            type="button"
            disabled={isDeleting}
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors disabled:opacity-50 cursor-pointer"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-3">
          <p className="text-xs text-slate-700 leading-relaxed font-medium">
            Are you sure you want to permanently delete{" "}
            <strong className="text-rose-700 font-bold">
              {count === 1 ? "this email" : `these ${count} emails`}
            </strong>{" "}
            from Trash?
          </p>
          <div className="p-3 bg-amber-50/80 border border-amber-200/80 rounded-xl text-[11px] text-amber-900 leading-relaxed space-y-1">
            <p className="font-semibold text-amber-950">This action cannot be undone.</p>
            <p className="text-amber-800">
              The messages, raw headers, and stored attachments will be permanently removed from the database and storage.
            </p>
          </div>
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-3.5 bg-slate-50/80 border-t border-slate-100 flex items-center justify-end gap-2.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isDeleting}
            onClick={onClose}
            className="text-xs"
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={isDeleting}
            onClick={onConfirm}
            className="bg-rose-600 hover:bg-rose-700 text-white text-xs gap-1.5 shadow-xs"
          >
            {isDeleting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Deleting...</span>
              </>
            ) : (
              <>
                <Trash2 className="h-3.5 w-3.5" />
                <span>Delete Permanently {count > 1 ? `(${count})` : ""}</span>
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};
