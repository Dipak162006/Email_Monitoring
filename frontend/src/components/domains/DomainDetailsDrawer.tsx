import React, { useEffect } from "react";
import { createPortal } from "react-dom";
import {
  X,
  RefreshCw,
  AlertCircle,
  Key,
  Trash2,
  Calendar,
} from "lucide-react";
import { DomainStatusBadge } from "./DomainStatusBadge";
import type { Domain, DomainVerificationStatus } from "../../types/domains";
import { Button } from "../ui/Button";
import { cn } from "../../lib/utils";

interface DomainDetailsDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  domain: Domain | null;
  onVerify?: () => void;
  isVerifying?: boolean;
  canManage?: boolean;
  onEditDkim?: () => void;
  onDelete?: () => void;
}

export const DomainDetailsDrawer: React.FC<DomainDetailsDrawerProps> = ({
  isOpen,
  onClose,
  domain,
  onVerify,
  isVerifying = false,
  canManage = false,
  onEditDkim,
  onDelete,
}) => {
  // Handle Escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen || !domain) return null;

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "Never";
    try {
      const date = new Date(dateStr);
      return date.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateStr;
    }
  };

  const getDnsExplanation = (
    type: "MX" | "SPF" | "DKIM" | "DMARC",
    status: DomainVerificationStatus,
    selector?: string | null
  ): string => {
    if (type === "DKIM" && (!selector || !selector.trim())) {
      return "Configure a DKIM selector to verify DKIM.";
    }

    switch (status) {
      case "VERIFIED":
        switch (type) {
          case "MX":
            return "Valid Mail Exchange (MX) record detected and verified.";
          case "SPF":
            return "Sender Policy Framework (SPF) record verified.";
          case "DKIM":
            return `DKIM public key detected and verified for selector "${selector}".`;
          case "DMARC":
            return "DMARC policy detected and verified.";
        }
        break;
      case "WARNING":
        switch (type) {
          case "MX":
            return "MX record detected but may require configuration review.";
          case "SPF":
            return "SPF record detected with potential configuration warnings.";
          case "DKIM":
            return `DKIM configuration requires review for selector "${selector}".`;
          case "DMARC":
            return "The domain's DMARC policy requires attention (e.g. p=none).";
        }
        break;
      case "FAILED":
        switch (type) {
          case "MX":
            return "No valid MX records detected pointing to your mail setup.";
          case "SPF":
            return "No SPF record was detected or SPF authentication failed.";
          case "DKIM":
            return `DKIM verification failed for selector "${selector}".`;
          case "DMARC":
            return "No valid DMARC record was detected or alignment failed.";
        }
        break;
      case "PENDING":
      default:
        switch (type) {
          case "MX":
            return "MX verification pending. Run verification to validate.";
          case "SPF":
            return "SPF verification pending. Run verification to validate.";
          case "DKIM":
            return selector
              ? `DKIM verification pending for selector "${selector}".`
              : "Configure a DKIM selector to verify DKIM.";
          case "DMARC":
            return "DMARC verification pending. Run verification to validate.";
        }
    }
  };

  const hasDkimSelector = Boolean(domain.dkim_selector && domain.dkim_selector.trim());

  return createPortal(
    <div
      className="fixed inset-0 z-50 overflow-hidden"
      role="dialog"
      aria-modal="true"
      aria-labelledby="drawer-title"
    >
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity duration-300 animate-in fade-in"
        onClick={onClose}
        aria-hidden="true"
      />

      <div className="fixed inset-y-0 right-0 max-w-full flex pl-10 pointer-events-none">
        <div className="w-screen max-w-lg pointer-events-auto bg-white shadow-2xl flex flex-col justify-between border-l border-slate-200 animate-in slide-in-from-right duration-300">
          {/* Header */}
          <div className="px-6 py-5 border-b border-slate-200 flex items-start justify-between bg-slate-50/60">
            <div className="flex flex-col min-w-0 pr-4">
              <div className="flex items-center gap-2.5 mb-1.5 flex-wrap">
                <h2
                  id="drawer-title"
                  className="font-mono text-base font-bold text-slate-900 truncate"
                >
                  {domain.domain_name}
                </h2>
                <DomainStatusBadge status={domain.verification_status} size="sm" />
              </div>
              <p className="text-xs text-slate-500 flex items-center gap-1.5">
                <Calendar className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                <span>Added {formatDate(domain.created_at)}</span>
              </p>
            </div>
            <div className="flex items-center gap-1 shrink-0">
              {canManage && onVerify && (
                <button
                  type="button"
                  onClick={onVerify}
                  disabled={isVerifying}
                  title="Verify DNS Now"
                  aria-label="Verify DNS Now"
                  className="p-2 rounded-lg text-indigo-600 hover:bg-indigo-50 hover:text-indigo-700 transition-colors disabled:opacity-50 cursor-pointer"
                >
                  <RefreshCw
                    className={cn("w-4 h-4", isVerifying && "animate-spin text-indigo-600")}
                  />
                </button>
              )}
              <button
                type="button"
                onClick={onClose}
                title="Close sheet"
                aria-label="Close sheet"
                className="p-2 rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Drawer Scrollable Body */}
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
            {/* Global Verification Error Alert */}
            {domain.verification_error && (
              <div
                className="rounded-xl border border-rose-200 bg-rose-50/70 p-4 text-rose-900 space-y-1.5"
                role="alert"
              >
                <div className="flex items-center gap-2 text-xs font-bold text-rose-800">
                  <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
                  <span>DNS Verification Notice</span>
                </div>
                <p className="text-xs font-mono text-rose-700 leading-relaxed whitespace-pre-wrap break-words">
                  {domain.verification_error}
                </p>
              </div>
            )}

            {/* Diagnostic Breakdown Header */}
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
                DNS Diagnostic Breakdown
              </span>
              <span className="text-[11px] font-medium text-indigo-600">Persisted Records</span>
            </div>

            {/* Diagnostic Breakdown Cards */}
            <div className="space-y-3">
              {/* MX Card */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-slate-800">
                    Mail Exchange (MX)
                  </span>
                  <DomainStatusBadge status={domain.mx_status} size="sm" />
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">
                  {getDnsExplanation("MX", domain.mx_status)}
                </p>
              </div>

              {/* SPF Card */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-slate-800">
                    Sender Policy Framework (SPF)
                  </span>
                  <DomainStatusBadge status={domain.spf_status} size="sm" />
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">
                  {getDnsExplanation("SPF", domain.spf_status)}
                </p>
              </div>

              {/* DKIM Card */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-slate-800">
                    DomainKeys Identified Mail (DKIM)
                  </span>
                  <div className="flex items-center gap-1.5">
                    {hasDkimSelector && (
                      <span className="px-2 py-0.5 rounded font-mono text-[11px] bg-slate-200 text-slate-700 font-medium">
                        Selector: {domain.dkim_selector}
                      </span>
                    )}
                    <DomainStatusBadge status={domain.dkim_status} size="sm" />
                  </div>
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">
                  {getDnsExplanation("DKIM", domain.dkim_status, domain.dkim_selector)}
                </p>
                {hasDkimSelector && (
                  <div className="pt-1.5 mt-1 border-t border-slate-200/60 text-[11px] text-slate-500 font-mono">
                    Host:{" "}
                    <span className="text-slate-800 font-medium">
                      {domain.dkim_selector}._domainkey.{domain.domain_name}
                    </span>
                  </div>
                )}
              </div>

              {/* DMARC Card */}
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-bold text-slate-800">
                    DMARC Policy Enforcement
                  </span>
                  <DomainStatusBadge status={domain.dmarc_status} size="sm" />
                </div>
                <p className="text-xs text-slate-600 leading-relaxed">
                  {getDnsExplanation("DMARC", domain.dmarc_status)}
                </p>
              </div>
            </div>

            {/* Quick Actions (if canManage) */}
            {canManage && (
              <div className="pt-2 border-t border-slate-100 flex items-center gap-2">
                {onEditDkim && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={onEditDkim}
                    className="flex-1 gap-1.5 text-xs border-slate-200 text-slate-700 hover:bg-slate-50 cursor-pointer"
                  >
                    <Key className="w-3.5 h-3.5 text-slate-500" />
                    <span>Edit DKIM</span>
                  </Button>
                )}
                {onDelete && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={onDelete}
                    className="gap-1.5 text-xs border-rose-200 text-rose-700 hover:bg-rose-50 cursor-pointer"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-rose-600" />
                    <span>Delete</span>
                  </Button>
                )}
              </div>
            )}
          </div>

          {/* Drawer Fixed Footer */}
          <div className="px-6 py-4 border-t border-slate-200 bg-white flex items-center justify-between">
            <div className="flex flex-col">
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
                Last Checked
              </span>
              <span className="font-mono text-xs font-semibold text-slate-700">
                {formatDate(domain.last_checked_at)}
              </span>
            </div>
            <div className="flex items-center gap-2">
              {canManage && onVerify && (
                <Button
                  type="button"
                  size="sm"
                  onClick={onVerify}
                  disabled={isVerifying}
                  className="gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white cursor-pointer"
                >
                  <RefreshCw className={cn("w-3.5 h-3.5", isVerifying && "animate-spin")} />
                  <span>{isVerifying ? "Verifying..." : "Verify DNS"}</span>
                </Button>
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={onClose}
                className="cursor-pointer"
              >
                Close Sheet
              </Button>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body
  );
};
