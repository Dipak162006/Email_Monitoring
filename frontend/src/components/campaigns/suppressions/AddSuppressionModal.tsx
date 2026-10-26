import React, { useState, useEffect } from "react";
import { X, ShieldAlert, Loader2, Plus, Info } from "lucide-react";
import { Button } from "../../ui/Button";
import { suppressionsApi, RequestError } from "../../../services/api";
import type { SuppressionReason } from "../../../types/campaign";

interface AddSuppressionModalProps {
  isOpen: boolean;
  companyId: number;
  onClose: () => void;
  onSuccess: (message: string) => void;
}

export const AddSuppressionModal: React.FC<AddSuppressionModalProps> = ({
  isOpen,
  companyId,
  onClose,
  onSuccess,
}) => {
  const [emailsText, setEmailsText] = useState("");
  const [reason, setReason] = useState<SuppressionReason>("MANUAL");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setEmailsText("");
      setReason("MANUAL");
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

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    // Parse email list from text
    const parsedEmails = emailsText
      .split(/[\n,;]+/)
      .map((item) => item.trim())
      .filter((item) => item.length > 0);

    if (parsedEmails.length === 0) {
      setErrorMessage("Please enter at least one email address.");
      return;
    }

    // Basic email format check for the first invalid entry
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    const invalidEmail = parsedEmails.find((email) => !emailRegex.test(email));
    if (invalidEmail) {
      setErrorMessage(`Invalid email format: "${invalidEmail}"`);
      return;
    }

    setIsLoading(true);
    try {
      if (parsedEmails.length === 1) {
        // Single creation
        const singleEmail = parsedEmails[0];
        await suppressionsApi.createSuppression(companyId, {
          email: singleEmail,
          reason,
        });
        onSuccess(`Added ${singleEmail} to suppression list.`);
        onClose();
      } else {
        // Bulk creation
        const res = await suppressionsApi.bulkCreateSuppressions(companyId, {
          emails: parsedEmails,
          reason,
        });
        if (res.inserted_count > 0 && res.skipped_count > 0) {
          onSuccess(
            `Suppressed ${res.inserted_count} email(s). (${res.skipped_count} skipped as already suppressed)`
          );
        } else if (res.inserted_count > 0) {
          onSuccess(`Successfully added ${res.inserted_count} email(s) to suppression list.`);
        } else {
          onSuccess(
            `All ${res.skipped_count} email(s) were already present in the suppression list.`
          );
        }
        onClose();
      }
    } catch (err: unknown) {
      if (err instanceof RequestError) {
        if (err.status === 409) {
          setErrorMessage("This email is already in the company suppression list.");
        } else {
          setErrorMessage(err.message || "Failed to add email to suppression list.");
        }
      } else if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("An unexpected error occurred while saving suppression.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="add-suppression-modal-title"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 text-left animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto"
        style={{ width: "min(calc(100vw - 32px), 480px)" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center shrink-0">
              <ShieldAlert className="h-5 w-5" />
            </div>
            <div>
              <h3
                id="add-suppression-modal-title"
                className="text-base font-bold text-slate-900 leading-snug"
              >
                Add Suppressed Email
              </h3>
              <p className="text-xs text-slate-500">
                Block addresses from receiving any future campaigns
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isLoading}
            className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-50"
            aria-label="Close dialog"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
          {errorMessage && (
            <div
              role="alert"
              className="p-3 text-xs bg-rose-50 border border-rose-200 text-rose-700 rounded-lg"
            >
              {errorMessage}
            </div>
          )}

          <div>
            <label
              htmlFor="suppression-emails-input"
              className="block text-xs font-semibold text-slate-700 mb-1"
            >
              Email Address(es) <span className="text-rose-500">*</span>
            </label>
            <textarea
              id="suppression-emails-input"
              rows={4}
              required
              disabled={isLoading}
              value={emailsText}
              onChange={(e) => setEmailsText(e.target.value)}
              placeholder="user@example.com&#10;contact@domain.com, lead@partner.org"
              className="w-full text-xs font-mono p-3 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition placeholder:font-sans placeholder:text-slate-400 disabled:bg-slate-50 disabled:text-slate-500 resize-y"
            />
            <p className="text-[11px] text-slate-500 mt-1 flex items-center gap-1">
              <Info className="h-3.5 w-3.5 text-slate-400 shrink-0" />
              <span>Enter a single email or paste multiple separated by commas or lines.</span>
            </p>
          </div>

          <div>
            <label
              htmlFor="suppression-reason-select"
              className="block text-xs font-semibold text-slate-700 mb-1"
            >
              Suppression Reason
            </label>
            <select
              id="suppression-reason-select"
              value={reason}
              onChange={(e) => setReason(e.target.value as SuppressionReason)}
              disabled={isLoading}
              className="w-full text-xs py-2 px-3 rounded-lg border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent bg-white text-slate-800 disabled:bg-slate-50"
            >
              <option value="MANUAL">Manual Suppression (Default)</option>
              <option value="UNSUBSCRIBE">Unsubscribed</option>
              <option value="COMPLAINT">Spam / Abuse Complaint</option>
            </select>
          </div>

          <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/80 text-[11px] text-slate-600 leading-relaxed">
            Suppressed addresses are globally excluded from all current and future outreach campaigns
            under this company workspace.
          </div>

          {/* Action buttons */}
          <div className="flex items-center justify-end gap-2.5 pt-2">
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
              type="submit"
              variant="primary"
              size="sm"
              disabled={isLoading || emailsText.trim().length === 0}
              className="flex items-center gap-1.5"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Adding...</span>
                </>
              ) : (
                <>
                  <Plus className="h-3.5 w-3.5" />
                  <span>Add to Suppression List</span>
                </>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
