import React, { useState } from "react";
import { createPortal } from "react-dom";
import { AlertTriangle, X, Loader2, Trash2 } from "lucide-react";
import { Button } from "../ui/Button";
import { domainsApi } from "../../services/api";
import type { Domain } from "../../types/domains";

interface DeleteDomainDialogProps {
  isOpen: boolean;
  onClose: () => void;
  domain: Domain | null;
  companyId: number;
  onSuccess: (deletedDomain: Domain) => void;
}

export const DeleteDomainDialog: React.FC<DeleteDomainDialogProps> = ({
  isOpen,
  onClose,
  domain,
  companyId,
  onSuccess,
}) => {
  const [isDeleting, setIsDeleting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen || !domain) return null;

  const handleClose = () => {
    if (isDeleting) return;
    setErrorMessage(null);
    onClose();
  };

  const handleConfirm = async () => {
    setErrorMessage(null);
    setIsDeleting(true);

    try {
      await domainsApi.deleteDomain(companyId, domain.id);
      setIsDeleting(false);
      onSuccess(domain);
    } catch (err: unknown) {
      const errorObj = err as { detail?: string; message?: string };
      setErrorMessage(
        errorObj.detail || errorObj.message || "Failed to delete domain. Please try again."
      );
      setIsDeleting(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-in fade-in duration-150"
      role="dialog"
      aria-modal="true"
      aria-labelledby="delete-domain-title"
    >
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full overflow-hidden animate-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-rose-50/50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600 shrink-0">
              <AlertTriangle className="h-4 w-4" />
            </div>
            <h3 id="delete-domain-title" className="text-sm font-bold text-slate-900">
              Delete Domain
            </h3>
          </div>
          <button
            type="button"
            disabled={isDeleting}
            onClick={handleClose}
            aria-label="Close dialog"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="p-6 space-y-3">
          {errorMessage && (
            <div
              className="p-3 rounded-xl border border-rose-200 bg-rose-50 text-rose-800 text-xs"
              role="alert"
            >
              {errorMessage}
            </div>
          )}

          <p className="text-xs text-slate-700 leading-relaxed font-medium">
            Delete <strong className="font-mono text-slate-900 font-semibold">{domain.domain_name}</strong>?
          </p>
          <div className="p-3 bg-amber-50/80 border border-amber-200/80 rounded-xl text-[11px] text-amber-900 leading-relaxed">
            This action cannot be undone. Email sending and receiving for this domain will fail verification checks immediately.
          </div>
        </div>

        {/* Actions */}
        <div className="px-6 py-4 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isDeleting}
            onClick={handleClose}
            className="cursor-pointer"
          >
            Cancel
          </Button>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={isDeleting}
            onClick={handleConfirm}
            className="gap-1.5 bg-rose-600 hover:bg-rose-700 text-white cursor-pointer"
          >
            {isDeleting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span>Deleting...</span>
              </>
            ) : (
              <>
                <Trash2 className="h-3.5 w-3.5" />
                <span>Delete Domain</span>
              </>
            )}
          </Button>
        </div>
      </div>
    </div>,
    document.body
  );
};
