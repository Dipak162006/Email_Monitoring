import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { X, Loader2, AlertCircle, Lock, Key, Check } from "lucide-react";
import { Button } from "../ui/Button";
import { domainsApi } from "../../services/api";
import type { Domain } from "../../types/domains";

interface EditDkimDialogProps {
  isOpen: boolean;
  onClose: () => void;
  domain: Domain | null;
  companyId: number;
  onSuccess: (updatedDomain: Domain) => void;
}

export const EditDkimDialog: React.FC<EditDkimDialogProps> = ({
  isOpen,
  onClose,
  domain,
  companyId,
  onSuccess,
}) => {
  const [dkimSelector, setDkimSelector] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (domain) {
      setDkimSelector(domain.dkim_selector || "");
      setErrorMessage(null);
    }
  }, [domain, isOpen]);

  if (!isOpen || !domain) return null;

  const handleClose = () => {
    if (isSubmitting) return;
    setErrorMessage(null);
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    setIsSubmitting(true);

    try {
      const trimmed = dkimSelector.trim();
      const payload = {
        dkim_selector: trimmed ? trimmed : null,
      };

      const result = await domainsApi.updateDomain(companyId, domain.id, payload);
      setErrorMessage(null);
      onSuccess(result);
    } catch (err: unknown) {
      const errorObj = err as { detail?: string; message?: string };
      setErrorMessage(
        errorObj.detail || errorObj.message || "Failed to update DKIM selector. Please try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const previewSelector = dkimSelector.trim() || "default";

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-in fade-in duration-150"
      role="dialog"
      aria-modal="true"
      aria-labelledby="edit-dkim-title"
    >
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full overflow-hidden animate-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-start justify-between bg-slate-50/50">
          <div>
            <h3 id="edit-dkim-title" className="text-base font-bold text-slate-900 flex items-center gap-2">
              <Key className="w-4 h-4 text-indigo-600" />
              <span>Edit DKIM Configuration</span>
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Update the DKIM selector prefix for DNS public key discovery.
            </p>
          </div>
          <button
            type="button"
            disabled={isSubmitting}
            onClick={handleClose}
            aria-label="Close dialog"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/60 transition-colors disabled:opacity-50 cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {errorMessage && (
            <div
              className="p-3.5 rounded-xl border border-rose-200 bg-rose-50/70 text-rose-800 text-xs flex items-start gap-2.5"
              role="alert"
            >
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              <span className="leading-relaxed">{errorMessage}</span>
            </div>
          )}

          {/* Domain Name (Strictly READ ONLY) */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label
                htmlFor="edit-domain-name"
                className="block text-xs font-semibold text-slate-800"
              >
                Domain Name
              </label>
              <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400">
                <Lock className="w-3 h-3 text-slate-400" />
                Read-only
              </span>
            </div>
            <input
              id="edit-domain-name"
              type="text"
              readOnly
              disabled
              value={domain.domain_name}
              className="w-full px-3.5 py-2 text-xs font-mono bg-slate-100/80 border border-slate-200 rounded-xl text-slate-600 cursor-not-allowed select-none outline-none"
            />
            <p className="text-[11px] text-slate-500">
              The domain name itself cannot be changed after creation.
            </p>
          </div>

          {/* DKIM Selector (Editable) */}
          <div className="space-y-1.5">
            <label
              htmlFor="edit-dkim-selector"
              className="block text-xs font-semibold text-slate-800"
            >
              DKIM Selector
            </label>
            <input
              id="edit-dkim-selector"
              type="text"
              disabled={isSubmitting}
              value={dkimSelector}
              onChange={(e) => setDkimSelector(e.target.value)}
              placeholder="e.g. pm2024 or default"
              className="w-full px-3.5 py-2 text-xs font-mono bg-white border border-slate-300 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all disabled:opacity-50"
            />
            <p className="text-[11px] text-slate-500">
              Host will resolve to:{" "}
              <code className="font-mono text-indigo-600 font-semibold">
                {previewSelector}._domainkey.{domain.domain_name}
              </code>
            </p>
          </div>

          {/* Warning note about status reset */}
          <div className="p-3 bg-amber-50/80 border border-amber-200/80 rounded-xl text-[11px] text-amber-900 leading-relaxed">
            Note: Changing the DKIM selector will reset its verification status to pending until the next verification check.
          </div>

          {/* Actions */}
          <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2.5">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isSubmitting}
              onClick={handleClose}
              className="cursor-pointer"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={isSubmitting}
              className="gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <>
                  <Check className="w-3.5 h-3.5" />
                  <span>Save Changes</span>
                </>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
};
