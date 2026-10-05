import React, { useState } from "react";
import { createPortal } from "react-dom";
import { X, Loader2, AlertCircle, Plus } from "lucide-react";
import { Button } from "../ui/Button";
import { domainsApi } from "../../services/api";
import type { Domain } from "../../types/domains";

interface AddDomainDialogProps {
  isOpen: boolean;
  onClose: () => void;
  companyId: number;
  onSuccess: (newDomain: Domain) => void;
}

export const AddDomainDialog: React.FC<AddDomainDialogProps> = ({
  isOpen,
  onClose,
  companyId,
  onSuccess,
}) => {
  const [domainName, setDomainName] = useState("");
  const [dkimSelector, setDkimSelector] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleClose = () => {
    if (isSubmitting) return;
    setDomainName("");
    setDkimSelector("");
    setErrorMessage(null);
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const trimmedDomain = domainName.trim();
    if (!trimmedDomain) {
      setErrorMessage("Domain name is required.");
      return;
    }

    if (trimmedDomain.includes("@")) {
      setErrorMessage("Domain name must not contain '@' (enter a domain name, not an email address).");
      return;
    }

    if (trimmedDomain.toLowerCase().startsWith("http://") || trimmedDomain.toLowerCase().startsWith("https://")) {
      setErrorMessage("Do not include http:// or https:// in domain name.");
      return;
    }

    setIsSubmitting(true);
    try {
      const payload = {
        domain_name: trimmedDomain,
        dkim_selector: dkimSelector.trim() || undefined,
      };

      const result = await domainsApi.createDomain(companyId, payload);
      setDomainName("");
      setDkimSelector("");
      setErrorMessage(null);
      onSuccess(result);
    } catch (err: unknown) {
      const errorObj = err as { detail?: string; message?: string };
      setErrorMessage(
        errorObj.detail || errorObj.message || "Failed to add domain. Please check your input and try again."
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-in fade-in duration-150"
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-domain-title"
    >
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full overflow-hidden animate-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-start justify-between bg-slate-50/50">
          <div>
            <h3 id="add-domain-title" className="text-base font-bold text-slate-900">
              Add Domain
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Manage and verify DNS authentication for your company's email domains.
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

          {/* Domain Name */}
          <div className="space-y-1.5">
            <label
              htmlFor="add-domain-name"
              className="block text-xs font-semibold text-slate-800"
            >
              Domain Name <span className="text-rose-500">*</span>
            </label>
            <input
              id="add-domain-name"
              type="text"
              required
              disabled={isSubmitting}
              value={domainName}
              onChange={(e) => setDomainName(e.target.value)}
              placeholder="e.g. example.com or mail.example.com"
              className="w-full px-3.5 py-2 text-xs font-mono bg-white border border-slate-300 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all disabled:opacity-50"
            />
            <p className="text-[11px] text-slate-500">
              Enter a domain such as example.com. Do not include http://, https://, or trailing slashes.
            </p>
          </div>

          {/* DKIM Selector */}
          <div className="space-y-1.5">
            <label
              htmlFor="add-dkim-selector"
              className="block text-xs font-semibold text-slate-800"
            >
              DKIM Selector{" "}
              <span className="text-slate-400 font-normal">(Optional)</span>
            </label>
            <input
              id="add-dkim-selector"
              type="text"
              disabled={isSubmitting}
              value={dkimSelector}
              onChange={(e) => setDkimSelector(e.target.value)}
              placeholder="e.g. pm2024 or default"
              className="w-full px-3.5 py-2 text-xs font-mono bg-white border border-slate-300 rounded-xl text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-all disabled:opacity-50"
            />
            <p className="text-[11px] text-slate-500">
              Optional. You can configure or update the selector later.
            </p>
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
                  <span>Adding Domain...</span>
                </>
              ) : (
                <>
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Domain</span>
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
