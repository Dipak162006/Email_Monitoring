import React, { useEffect, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { Button } from "../../ui/Button";
import { suppressionsApi } from "../../../services/api";
import type { SuppressionEntry } from "../../../types/campaign";

interface DeleteSuppressionModalProps {
  isOpen: boolean;
  entry: SuppressionEntry | null;
  companyId: number;
  onClose: () => void;
  onSuccess: (email: string) => void;
}

export const DeleteSuppressionModal: React.FC<DeleteSuppressionModalProps> = ({
  isOpen,
  entry,
  companyId,
  onClose,
  onSuccess,
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setErrorMessage(null);
      setIsLoading(false);
    }
  }, [isOpen]);

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

  if (!isOpen || !entry) return null;

  const handleConfirm = async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      await suppressionsApi.deleteSuppression(companyId, entry.id);
      onSuccess(entry.email);
      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Failed to remove email from suppression list.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="unsuppress-email-modal-title"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 text-left animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto"
        style={{ width: "min(calc(100vw - 32px), 440px)" }}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200 text-amber-600 flex items-center justify-center shrink-0">
            <AlertTriangle className="h-5 w-5" />
          </div>
          <div className="flex flex-col min-w-0">
            <h3
              id="unsuppress-email-modal-title"
              className="text-sm font-bold text-slate-900 truncate"
            >
              Unsuppress Email Address?
            </h3>
            <span className="text-xs text-slate-500 font-mono truncate">
              {entry.email}
            </span>
          </div>
        </div>

        {/* Warning Body */}
        <p className="text-xs text-slate-600 mb-4 leading-relaxed">
          Removing <strong className="text-slate-900 font-mono">{entry.email}</strong> from the
          company suppression list will allow campaigns to send emails to this recipient again.
          Ensure the recipient has re-opted in to avoid spam complaints.
        </p>

        {errorMessage && (
          <div
            role="alert"
            className="mb-4 p-3 text-xs bg-rose-50 border border-rose-200 text-rose-700 rounded-lg"
          >
            {errorMessage}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-end gap-2.5 pt-2 border-t border-slate-100">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onClose}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            onClick={handleConfirm}
            disabled={isLoading}
            className="flex items-center gap-1.5"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Removing...</span>
              </>
            ) : (
              <span>Unsuppress Email</span>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
};
