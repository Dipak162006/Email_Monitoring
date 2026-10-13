import React, { useEffect } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import type { Campaign } from "../../types/campaign";

export type CampaignModalMode = "cancel" | "delete";

interface CancelCampaignModalProps {
  isOpen: boolean;
  campaign: Campaign | null;
  mode: CampaignModalMode;
  onClose: () => void;
  onConfirm: () => void;
  isLoading?: boolean;
}

export const CancelCampaignModal: React.FC<CancelCampaignModalProps> = ({
  isOpen,
  campaign,
  mode,
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

  if (!isOpen || !campaign) return null;

  const isCancel = mode === "cancel";
  const title = isCancel
    ? `Cancel ${campaign.status === "SCHEDULED" ? "Scheduled " : ""}Campaign?`
    : `Delete ${campaign.status === "DRAFT" ? "Draft " : ""}Campaign?`;

  const description = isCancel
    ? `The campaign "${campaign.name}" will halt all pending deliveries and transition permanently to CANCELLED. This action cannot be undone.`
    : `Are you sure you want to delete "${campaign.name}"? This campaign and its associated records will be permanently removed. This action cannot be undone.`;

  const confirmButtonText = isCancel ? "Cancel Campaign" : "Delete Campaign";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="campaign-modal-title"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
    >
      <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 text-left animate-in zoom-in-95 duration-150">
        {/* Header with warning icon */}
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-rose-50 border border-rose-200 text-rose-600 flex items-center justify-center shrink-0">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="flex flex-col min-w-0">
            <h3 id="campaign-modal-title" className="text-sm font-bold text-slate-900 truncate">
              {title}
            </h3>
            <span className="text-xs text-slate-500 truncate">
              Ref: {campaign.name}
            </span>
          </div>
        </div>

        {/* Explanatory Consequence Text */}
        <p className="text-xs text-slate-600 mb-6 leading-relaxed">
          {description}
        </p>

        {/* Buttons */}
        <div className="flex items-center justify-end gap-2.5">
          <button
            type="button"
            disabled={isLoading}
            onClick={onClose}
            className="px-3.5 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium transition-colors disabled:opacity-50"
          >
            {isCancel ? "Keep Campaign" : "Cancel"}
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
                <span>Processing...</span>
              </>
            ) : (
              <span>{confirmButtonText}</span>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
