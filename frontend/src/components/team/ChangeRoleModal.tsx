import React, { useState, useEffect } from "react";
import { ShieldCheck, X, Loader2, AlertCircle } from "lucide-react";
import { Button } from "../ui/Button";
import type { CompanyMember } from "../../types/auth";

interface ChangeRoleModalProps {
  isOpen: boolean;
  member: CompanyMember | null;
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (userId: number, role: "ADMIN" | "MEMBER") => Promise<void>;
}

export const ChangeRoleModal: React.FC<ChangeRoleModalProps> = ({
  isOpen,
  member,
  isSubmitting,
  onClose,
  onSubmit,
}) => {
  const [selectedRole, setSelectedRole] = useState<"ADMIN" | "MEMBER">("MEMBER");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (member) {
      setSelectedRole(member.role === "ADMIN" ? "ADMIN" : "MEMBER");
      setError(null);
    }
  }, [member, isOpen]);

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

  const isUnchanged = selectedRole === member.role;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isUnchanged) {
      onClose();
      return;
    }

    setError(null);
    try {
      await onSubmit(member.user_id, selectedRole);
    } catch (err: unknown) {
      const errObj = err as { detail?: string; message?: string };
      setError(errObj.detail || errObj.message || "Failed to update role. Please try again.");
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
        className="bg-white rounded-xl shadow-xl max-w-md w-full border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150"
        role="dialog"
        aria-modal="true"
        aria-labelledby="change-role-modal-title"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
              <ShieldCheck className="h-4 w-4" />
            </div>
            <h3 id="change-role-modal-title" className="text-base font-semibold text-slate-900">
              Change Role
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

        {/* Form Body */}
        <form onSubmit={handleSubmit}>
          <div className="p-6 space-y-4">
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
            </div>

            <div>
              <label htmlFor="select-role" className="block text-xs font-semibold text-slate-700 mb-1">
                Select New Role
              </label>
              <select
                id="select-role"
                disabled={isSubmitting}
                value={selectedRole}
                onChange={(e) => setSelectedRole(e.target.value as "ADMIN" | "MEMBER")}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-indigo-500 cursor-pointer disabled:opacity-50"
              >
                <option value="ADMIN">Admin (Full Access to all inboxes and settings)</option>
                <option value="MEMBER">Member (Limited to explicitly granted email accounts)</option>
              </select>
            </div>
          </div>

          {/* Footer */}
          <div className="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex items-center justify-end gap-2.5">
            <button
              type="button"
              disabled={isSubmitting}
              onClick={onClose}
              className="px-3.5 py-2 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-200/60 transition-colors cursor-pointer disabled:opacity-50"
            >
              Cancel
            </button>
            <Button
              type="submit"
              disabled={isSubmitting || isUnchanged}
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
        </form>
      </div>
    </div>
  );
};
