import React from "react";
import { RotateCcw, X, Loader2 } from "lucide-react";
import { Button } from "../ui/Button";

interface RestoreConfirmModalProps {
  isOpen: boolean;
  count: number;
  isRestoring: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export const RestoreConfirmModal: React.FC<RestoreConfirmModalProps> = ({
  isOpen,
  count,
  isRestoring,
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
        aria-labelledby="restore-modal-title"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/80">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
              <RotateCcw className="h-4 w-4" />
            </div>
            <h3 id="restore-modal-title" className="text-sm font-bold text-slate-900">
              {count === 1 ? "Restore Email" : `Restore ${count} Emails`}
            </h3>
          </div>
          <button
            type="button"
            disabled={isRestoring}
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors disabled:opacity-50 cursor-pointer"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-3">
          <p className="text-xs text-slate-600 leading-relaxed">
            Are you sure you want to restore{" "}
            <strong className="text-slate-900 font-semibold">
              {count === 1 ? "this email" : `these ${count} emails`}
            </strong>{" "}
            from Trash?
          </p>
          <p className="text-xs text-slate-500 leading-relaxed">
            Restored messages will return to their original active mailbox (such as your Inbox) and become accessible across your connected accounts.
          </p>
        </div>

        {/* Footer Actions */}
        <div className="px-6 py-3.5 bg-slate-50/80 border-t border-slate-100 flex items-center justify-end gap-2.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isRestoring}
            onClick={onClose}
            className="text-xs"
          >
            Cancel
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={isRestoring}
            onClick={onConfirm}
            className="bg-indigo-600 hover:bg-indigo-700 text-white text-xs gap-1.5 shadow-xs"
          >
            {isRestoring ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Restoring...</span>
              </>
            ) : (
              <>
                <RotateCcw className="h-3.5 w-3.5" />
                <span>Restore {count > 1 ? `(${count})` : ""}</span>
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};
