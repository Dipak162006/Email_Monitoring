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
  Users,
} from "lucide-react";
import { Button } from "../ui/Button";
import type { CompanyMember } from "../../types/auth";
import type { EmailAccountItem } from "../../types/emails";

interface ManageAccountAccessModalProps {
  isOpen: boolean;
  account: EmailAccountItem | null;
  members: CompanyMember[];
  currentAssignedUserIds: number[];
  isSubmitting: boolean;
  onClose: () => void;
  onSave: (accountId: number, userIdsToGrant: number[], userIdsToRevoke: number[]) => Promise<void>;
}

export const ManageAccountAccessModal: React.FC<ManageAccountAccessModalProps> = ({
  isOpen,
  account,
  members,
  currentAssignedUserIds,
  isSubmitting,
  onClose,
  onSave,
}) => {
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);

  // Filter only regular MEMBER users (Owners & Admins already have automatic full access)
  const regularMembers = members.filter((m) => m.role === "MEMBER");

  useEffect(() => {
    if (isOpen && account) {
      setSelectedUserIds(currentAssignedUserIds);
      setError(null);
    }
  }, [isOpen, account, currentAssignedUserIds]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isSubmitting) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen || !account) return null;

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

  const Icon = getAccountIcon(account.name);

  const handleToggle = (userId: number) => {
    setSelectedUserIds((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const userIdsToGrant = selectedUserIds.filter((id) => !currentAssignedUserIds.includes(id));
    const userIdsToRevoke = currentAssignedUserIds.filter((id) => !selectedUserIds.includes(id));

    if (userIdsToGrant.length === 0 && userIdsToRevoke.length === 0) {
      onClose();
      return;
    }

    setError(null);
    try {
      await onSave(account.id, userIdsToGrant, userIdsToRevoke);
    } catch (err: unknown) {
      const errObj = err as { detail?: string; message?: string };
      setError(errObj.detail || errObj.message || "Failed to update account permissions. Please try again.");
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
        aria-labelledby="manage-account-access-modal-title"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
              <ShieldCheck className="h-4 w-4" />
            </div>
            <h3 id="manage-account-access-modal-title" className="text-base font-semibold text-slate-900">
              Manage Shared Inbox Access
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

          {/* Target Account Preview */}
          <div className="flex items-center gap-3 p-3 bg-slate-50 border border-slate-200 rounded-lg">
            <div className="w-9 h-9 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
              <Icon className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <h4 className="text-sm font-semibold text-slate-900 truncate">{account.name}</h4>
              <p className="text-xs text-slate-500 truncate">{account.email_address}</p>
            </div>
            <span
              className={`ml-auto inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${
                account.is_active
                  ? "bg-emerald-50 text-emerald-700 border-emerald-200/80"
                  : "bg-slate-100 text-slate-600 border-slate-200"
              }`}
            >
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  account.is_active ? "bg-emerald-500" : "bg-slate-400"
                }`}
              />
              {account.is_active ? "Connected" : "Inactive"}
            </span>
          </div>

          <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 text-xs text-slate-600 flex items-start gap-2">
            <Users className="h-4 w-4 text-indigo-600 shrink-0 mt-0.5" />
            <span>
              Assign which team members can send and read emails from this inbox. Owners and Admins
              automatically have access.
            </span>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-xs font-semibold text-slate-700">
                Assigned Team Members
              </label>
              <span className="text-[11px] text-slate-400">
                {selectedUserIds.length} of {regularMembers.length} assigned
              </span>
            </div>

            {regularMembers.length === 0 ? (
              <div className="p-4 text-center border border-dashed border-slate-200 rounded-lg text-xs text-slate-500">
                No regular workspace members found. Workspace Owners and Admins already have automatic access.
              </div>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {regularMembers.map((member) => {
                  const isChecked = selectedUserIds.includes(member.user_id);
                  return (
                    <label
                      key={member.user_id}
                      className={`flex items-center justify-between p-3 rounded-lg border transition-colors cursor-pointer select-none ${
                        isChecked
                          ? "border-indigo-200 bg-indigo-50/30 hover:bg-indigo-50/50"
                          : "border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0 pr-2">
                        <div className="w-8 h-8 rounded-full bg-slate-100 border border-slate-200 text-slate-700 font-semibold text-xs flex items-center justify-center shrink-0">
                          {getInitials(member.full_name, member.email)}
                        </div>
                        <div className="min-w-0">
                          <span className="text-sm font-medium text-slate-900 block truncate">
                            {member.full_name || member.email}
                          </span>
                          <span className="text-xs text-slate-500 block truncate">
                            {member.email}
                          </span>
                        </div>
                      </div>
                      <input
                        type="checkbox"
                        disabled={isSubmitting}
                        checked={isChecked}
                        onChange={() => handleToggle(member.user_id)}
                        className="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-slate-300 cursor-pointer disabled:opacity-50"
                      />
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        </form>

        {/* Footer */}
        <div className="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2.5 shrink-0">
          <button
            type="button"
            disabled={isSubmitting}
            onClick={onClose}
            className="px-3.5 py-2 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 transition-colors cursor-pointer disabled:opacity-50"
          >
            Cancel
          </button>
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
        </div>
      </div>
    </div>
  );
};
