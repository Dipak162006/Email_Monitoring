import React, { useEffect } from "react";
import { StopCircle, Loader2 } from "lucide-react";
import type { CampaignRecipient } from "../../../types/campaign";

interface RecipientStopModalProps {
  isOpen: boolean;
  recipient: CampaignRecipient | null;
  onClose: () => void;
  onConfirm: () => void;
  isLoading?: boolean;
}

export const RecipientStopModal: React.FC<RecipientStopModalProps> = ({
  isOpen,
  recipient,
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

  if (!isOpen || !recipient) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="stop-recipient-modal-title"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 text-left animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto"
        style={{ width: "min(calc(100vw - 32px), 440px)" }}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200 text-amber-600 flex items-center justify-center shrink-0">
            <StopCircle className="h-5 w-5" />
          </div>
          <div className="flex flex-col min-w-0">
            <h3 id="stop-recipient-modal-title" className="text-sm font-bold text-slate-900 truncate">
              Stop Follow-Ups?
            </h3>
            <span className="text-xs text-slate-500 font-mono truncate">
              {recipient.email}
            </span>
          </div>
        </div>

        {/* Warning Body */}
        <p className="text-xs text-slate-600 mb-6 leading-relaxed">
          Are you sure you want to stop follow-up emails for <span className="font-semibold text-slate-900 font-mono break-all">{recipient.email}</span>? Future automated steps will not be sent and the pending schedule will be cleared.
        </p>

        {/* Action Buttons */}
        <div className="flex items-center justify-end gap-2.5">
          <button
            type="button"
            disabled={isLoading}
            onClick={onClose}
            className="px-3.5 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={isLoading}
            onClick={onConfirm}
            className="px-4 py-2 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-medium shadow-sm transition-colors flex items-center gap-1.5 disabled:opacity-50"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Stopping...</span>
              </>
            ) : (
              <span>Stop Follow-Ups</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

