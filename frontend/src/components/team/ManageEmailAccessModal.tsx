import React, { useState, useEffect } from "react";
import {
  ShieldCheck,
  X,
  Loader2,
  Mail,
  Headphones,
  Receipt,
  Server,
  AlertCircle,
  CheckCircle2,
} from "lucide-react";
import { Button } from "../ui/Button";
import type { CompanyMember } from "../../types/auth";
import type { EmailAccountItem } from "../../types/emails";

interface ManageEmailAccessModalProps {
  isOpen: boolean;
  member: CompanyMember | null;
  accounts: EmailAccountItem[];
  currentAssignedAccountIds: number[];
  isSubmitting: boolean;
  onClose: () => void;
  onSave: (userId: number, accountIdsToGrant: number[], accountIdsToRevoke: number[]) => Promise<void>;
}

export const ManageEmailAccessModal: React.FC<ManageEmailAccessModalProps> = ({
  isOpen,
  member,
  accounts,
  currentAssignedAccountIds,
  isSubmitting,
  onClose,
  onSave,
}) => {
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && member) {
      setSelectedIds(currentAssignedAccountIds);
      setError(null);
    }
  }, [isOpen, member, currentAssignedAccountIds]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isSubmitting) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen || !member) return null;

  const isFullAccess = member.role === "OWNER" || member.role === "ADMIN";

  const getInitials = (name: string | null, email: string): string => {
    if (name) {
      const parts = name.trim().split(/\s+/);
      if (parts.length >= 2) {
        return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
      }
      return parts[0].substring(0, 2).toUpperCase();
    }
    return email.substring(0, 2).toUpperCase();
  };

  const getAccountIcon = (name: string) => {
    const lower = name.toLowerCase();
    if (lower.includes("support") || lower.includes("help") || lower.includes("desk")) {
      return Headphones;
    }
    if (lower.includes("bill") || lower.includes("invoice") || lower.includes("finance")) {
      return Receipt;
    }
    if (lower.includes("dev") || lower.includes("telemetry") || lower.includes("system")) {
      return Server;
    }
    return Mail;
  };

  const handleToggle = (accountId: number) => {
    setSelectedIds((prev) =>
      prev.includes(accountId) ? prev.filter((id) => id !== accountId) : [...prev, accountId]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isFullAccess) {
      onClose();
      return;
    }

    const accountIdsToGrant = selectedIds.filter((id) => !currentAssignedAccountIds.includes(id));
    const accountIdsToRevoke = currentAssignedAccountIds.filter((id) => !selectedIds.includes(id));

    if (accountIdsToGrant.length === 0 && accountIdsToRevoke.length === 0) {
      onClose();
      return;
    }

    setError(null);
    try {
      await onSave(member.user_id, accountIdsToGrant, accountIdsToRevoke);
    } catch (err: unknown) {
      const errObj = err as { detail?: string; message?: string };
      setError(errObj.detail || errObj.message || "Failed to update email access. Please try again.");
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs animate-in fade-in duration-150"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div
        className="bg-white rounded-xl shadow-xl max-w-lg w-full border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150 max-h-[90vh] flex flex-col"
        role="dialog"
        aria-modal="true"
        aria-labelledby="manage-access-modal-title"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
              <ShieldCheck className="h-4 w-4" />
            </div>
            <h3 id="manage-access-modal-title" className="text-base font-semibold text-slate-900">
              Manage Email Access
            </h3>
          </div>
          <button
            type="button"
            disabled={isSubmitting}
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 p-1 rounded-lg transition-colors cursor-pointer disabled:opacity-50"
            aria-label="Close dialog"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4">
          {error && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-start gap-2.5 text-xs text-rose-800">
              <AlertCircle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {/* Target Member Preview */}
          <div className="flex items-center gap-3 p-3 bg-slate-50 border border-slate-200 rounded-lg">
            <div className="w-9 h-9 rounded-full bg-slate-200 text-slate-700 font-semibold text-xs flex items-center justify-center shrink-0">
              {getInitials(member.full_name, member.email)}
            </div>
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-slate-900 truncate">
                {member.full_name || member.email}
              </h4>
              <p className="text-xs text-slate-500 truncate">{member.email}</p>
            </div>
            <span className="ml-auto inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-slate-200/80 text-slate-700">
              {member.role}
            </span>
          </div>

          {isFullAccess ? (
            <div className="p-4 bg-indigo-50/70 border border-indigo-100 rounded-lg flex items-center gap-3 text-xs text-indigo-900">
              <CheckCircle2 className="h-5 w-5 text-indigo-600 shrink-0" />
              <div>
                <p className="font-semibold text-indigo-950">Full access to all company email accounts</p>
                <p className="text-indigo-700 mt-0.5">
                  As an {member.role === "OWNER" ? "Owner" : "Admin"}, this user automatically has permission to view, compose, and send from all connected mailboxes.
                </p>
              </div>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-xs font-semibold text-slate-700">
                  Connected Accounts Access
                </label>
                <span className="text-[11px] text-slate-400">
                  {selectedIds.length} of {accounts.length} granted
                </span>
              </div>

              {accounts.length === 0 ? (
                <div className="p-4 text-center border border-dashed border-slate-200 rounded-lg text-xs text-slate-500">
                  No email accounts connected to this workspace yet.
                </div>
              ) : (
                <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                  {accounts.map((acc) => {
                    const Icon = getAccountIcon(acc.name);
                    const isChecked = selectedIds.includes(acc.id);
                    return (
                      <label
                        key={acc.id}
                        className={`flex items-center justify-between p-3 rounded-lg border transition-colors cursor-pointer select-none ${
                          isChecked
                            ? "border-indigo-200 bg-indigo-50/30 hover:bg-indigo-50/50"
                            : "border-slate-200 hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center gap-3 min-w-0 pr-2">
                          <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
                            <Icon className="h-4 w-4" />
                          </div>
                          <div className="min-w-0">
                            <span className="text-sm font-medium text-slate-900 block truncate">
                              {acc.name}
                            </span>
                            <span className="text-xs text-slate-500 block truncate">
                              {acc.email_address}
                            </span>
                          </div>
                        </div>
                        <input
                          type="checkbox"
                          disabled={isSubmitting}
                          checked={isChecked}
                          onChange={() => handleToggle(acc.id)}
                          className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-slate-300 cursor-pointer disabled:opacity-50"
                        />
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </form>

        {/* Footer */}
        <div className="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2.5 shrink-0">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={onClose}
            className="px-3.5 py-2 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 transition-colors cursor-pointer disabled:opacity-50"
          >
            {isFullAccess ? "Close" : "Cancel"}
          </button>
          {!isFullAccess && (
            <Button
              type="button"
              disabled={isSubmitting}
              onClick={handleSubmit}
              className="px-4 py-2 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-700 text-white transition-colors shadow-xs gap-1.5 cursor-pointer disabled:opacity-50"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <span>Save Changes</span>
              )}
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};
