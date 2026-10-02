import React, { useState, useEffect } from "react";
import { UserPlus, Mail, X, Loader2, AlertCircle } from "lucide-react";
import { Button } from "../ui/Button";
import type { CompanyMemberAddPayload } from "../../types/auth";

interface AddMemberModalProps {
  isOpen: boolean;
  isSubmitting: boolean;
  onClose: () => void;
  onSubmit: (payload: CompanyMemberAddPayload) => Promise<void>;
  onInvite?: (payload: { email: string; role: "ADMIN" | "MEMBER" }) => Promise<void>;
}

export const AddMemberModal: React.FC<AddMemberModalProps> = ({
  isOpen,
  isSubmitting,
  onClose,
  onSubmit,
  onInvite,
}) => {
  const [mode, setMode] = useState<"INVITE" | "DIRECT">("INVITE");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"MEMBER" | "ADMIN">("MEMBER");
  const [error, setError] = useState<string | null>(null);
  const [showInviteFallback, setShowInviteFallback] = useState(false);

  useEffect(() => {
    if (isOpen) {
      setMode("INVITE");
      setEmail("");
      setRole("MEMBER");
      setError(null);
      setShowInviteFallback(false);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen && !isSubmitting) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) {
      setError("Please enter an email address.");
      return;
    }
    // Basic email format check
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setError("Please enter a valid email address.");
      return;
    }

    setError(null);
    setShowInviteFallback(false);

    try {
      if (mode === "INVITE" && onInvite) {
        await onInvite({ email: trimmed, role });
      } else {
        await onSubmit({ email: trimmed, role });
      }
    } catch (err: unknown) {
      const errObj = err as { detail?: string; message?: string; status?: number };
      const msg = errObj.detail || errObj.message || "Failed to process request. Please try again.";
      setError(msg);

      // If direct add failed because user does not have an account, suggest invitation
      if (mode === "DIRECT" && onInvite && (msg.toLowerCase().includes("not found") || errObj.status === 404)) {
        setShowInviteFallback(true);
      }
    }
  };

  const handleSwitchToInvite = () => {
    setMode("INVITE");
    setError(null);
    setShowInviteFallback(false);
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
        aria-labelledby="add-member-modal-title"
      >
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
              {mode === "INVITE" ? <Mail className="h-4 w-4" /> : <UserPlus className="h-4 w-4" />}
            </div>
            <h3 id="add-member-modal-title" className="text-base font-semibold text-slate-900">
              {mode === "INVITE" ? "Invite Team Member" : "Add Existing Member"}
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

        {/* Mode Selector Tabs */}
        {onInvite && (
          <div className="px-6 pt-4 pb-0">
            <div className="flex rounded-lg bg-slate-100 p-0.5 border border-slate-200 text-xs font-medium">
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => {
                  setMode("INVITE");
                  setError(null);
                  setShowInviteFallback(false);
                }}
                className={`flex-1 py-1.5 px-3 rounded-md transition-all cursor-pointer ${
                  mode === "INVITE"
                    ? "bg-white text-indigo-700 shadow-2xs font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Send Invitation
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={() => {
                  setMode("DIRECT");
                  setError(null);
                  setShowInviteFallback(false);
                }}
                className={`flex-1 py-1.5 px-3 rounded-md transition-all cursor-pointer ${
                  mode === "DIRECT"
                    ? "bg-white text-indigo-700 shadow-2xs font-semibold"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                Direct Add
              </button>
            </div>
          </div>
        )}

        {/* Form Body */}
        <form onSubmit={handleSubmit}>
          <div className="p-6 space-y-4">
            {error && (
              <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg flex flex-col gap-2 text-xs text-rose-800">
                <div className="flex items-start gap-2.5">
                  <AlertCircle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
                  <span>{error}</span>
                </div>
                {showInviteFallback && (
                  <div className="pl-6 pt-1">
                    <button
                      type="button"
                      onClick={handleSwitchToInvite}
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 underline cursor-pointer"
                    >
                      Switch to sending an invitation instead →
                    </button>
                  </div>
                )}
              </div>
            )}

            <div>
              <label htmlFor="member-email" className="block text-xs font-semibold text-slate-700 mb-1">
                Email Address
              </label>
              <input
                id="member-email"
                type="email"
                disabled={isSubmitting}
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  if (error) {
                    setError(null);
                    setShowInviteFallback(false);
                  }
                }}
                placeholder="user@example.com"
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-indigo-500 focus:bg-white transition-all disabled:opacity-50"
                autoFocus
              />
              <p className="text-[11px] text-slate-400 mt-1">
                {mode === "INVITE"
                  ? "An in-app workspace invitation will be issued for this email."
                  : "User must already have an existing registered account."}
              </p>
            </div>

            <div>
              <label htmlFor="member-role" className="block text-xs font-semibold text-slate-700 mb-1">
                Workspace Role
              </label>
              <select
                id="member-role"
                disabled={isSubmitting}
                value={role}
                onChange={(e) => setRole(e.target.value as "MEMBER" | "ADMIN")}
                className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 focus:outline-none focus:border-indigo-500 cursor-pointer disabled:opacity-50"
              >
                <option value="MEMBER">Member (Assigned email account access)</option>
                <option value="ADMIN">Admin (Full workspace and email access)</option>
              </select>
              <p className="text-[11px] text-slate-400 mt-1">
                Workspace Owner role cannot be assigned via invitation.
              </p>
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
              disabled={isSubmitting}
              className="px-4 py-2 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-700 text-white transition-colors shadow-xs gap-1.5 cursor-pointer"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>{mode === "INVITE" ? "Sending..." : "Adding..."}</span>
                </>
              ) : (
                <span>{mode === "INVITE" ? "Send Invitation" : "Add Member"}</span>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
};
