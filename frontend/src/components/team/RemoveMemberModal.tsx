import React, { useEffect, useState } from "react";
import { UserMinus, X, Loader2, AlertTriangle, AlertCircle } from "lucide-react";
import { Button } from "../ui/Button";
import type { CompanyMember } from "../../types/auth";

interface RemoveMemberModalProps {
  isOpen: boolean;
  member: CompanyMember | null;
  isRemoving: boolean;
  onClose: () => void;
  onConfirm: (userId: number) => Promise<void>;
}

export const RemoveMemberModal: React.FC<RemoveMemberModalProps> = ({
  isOpen,
  member,
  isRemoving,
  onClose,
  onConfirm,
}) => {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setError(null);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isRemoving) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isRemoving, onClose]);

  if (!isOpen || !member) return null;

  const handleConfirm = async () => {
    setError(null);
    try {
      await onConfirm(member.user_id);
    } catch (err: unknown) {
      const errObj = err as { detail?: string; message?: string };
      setError(errObj.detail || errObj.message || "Failed to remove member. Please try again.");
    }
  };

  const displayName = member.full_name || member.email;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isRemoving) onClose();
      }}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-md w-full border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        role="dialog"
        aria-modal="true"
        aria-labelledby="remove-member-modal-title"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-rose-50 border border-rose-100 text-rose-600 flex items-center justify-center shrink-0">
              <UserMinus className="h-4 w-4" />
            </div>
            <h3 id="remove-member-modal-title" className="text-base font-semibold text-slate-900">
              Remove Member
            </h3>
          </div>
          <button
            type="button"
            disabled={isRemoving}
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-4">
          {error && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-start gap-2.5 text-xs text-rose-800">
              <AlertCircle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <p className="text-sm text-slate-600 leading-relaxed">
            Remove <strong className="font-semibold text-slate-900">{displayName}</strong> (
            <span className="text-slate-500 font-mono text-xs">{member.email}</span>) from the workspace?
            Their email-account access will also be removed.
          </p>

          <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg flex items-center gap-2.5 text-xs text-amber-800">
            <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
            <span>This action takes effect immediately across all active sessions.</span>
          </div>
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2.5">
          <button
            type="button"
            disabled={isRemoving}
            onClick={onClose}
            className="px-3.5 py-2 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
          <Button
            type="button"
            variant="destructive"
            disabled={isRemoving}
            onClick={handleConfirm}
            className="px-4 py-2 rounded-lg text-xs font-medium bg-rose-600 hover:bg-rose-700 text-white transition-colors shadow-xs gap-1.5 cursor-pointer disabled:opacity-50"
          >
            {isRemoving ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Removing...</span>
              </>
            ) : (
              <span>Remove Member</span>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};
