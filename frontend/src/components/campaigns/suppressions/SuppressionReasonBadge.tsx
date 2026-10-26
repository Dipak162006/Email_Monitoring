import React from "react";
import { AlertCircle, Ban, ShieldAlert, UserX } from "lucide-react";
import type { SuppressionReason } from "../../../types/campaign";

interface SuppressionReasonBadgeProps {
  reason: SuppressionReason | string;
  className?: string;
}

export const SuppressionReasonBadge: React.FC<SuppressionReasonBadgeProps> = ({
  reason,
  className = "",
}) => {
  const normalized = (reason || "").toUpperCase();

  switch (normalized) {
    case "BOUNCE":
      return (
        <span
          data-testid="suppression-reason-bounce"
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200 shadow-2xs ${className}`}
        >
          <AlertCircle className="w-3 h-3 text-rose-500" />
          <span>Bounced</span>
        </span>
      );
    case "UNSUBSCRIBE":
      return (
        <span
          data-testid="suppression-reason-unsubscribe"
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200 shadow-2xs ${className}`}
        >
          <UserX className="w-3 h-3 text-amber-500" />
          <span>Unsubscribed</span>
        </span>
      );
    case "COMPLAINT":
      return (
        <span
          data-testid="suppression-reason-complaint"
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200 shadow-2xs ${className}`}
        >
          <ShieldAlert className="w-3 h-3 text-purple-500" />
          <span>Complaint</span>
        </span>
      );
    case "MANUAL":
    default:
      return (
        <span
          data-testid="suppression-reason-manual"
          className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200 shadow-2xs ${className}`}
        >
          <Ban className="w-3 h-3 text-slate-500" />
          <span>Manual</span>
        </span>
      );
  }
};
