import React from "react";
import { Clock, CheckCircle2, AlertCircle, Ban, ShieldAlert } from "lucide-react";
import type { CampaignRecipientStatus } from "../../../types/campaign";

interface RecipientStatusBadgeProps {
  status: CampaignRecipientStatus;
  className?: string;
}

export const RecipientStatusBadge: React.FC<RecipientStatusBadgeProps> = ({
  status,
  className = "",
}) => {
  switch (status) {
    case "PENDING":
      return (
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-amber-50 text-amber-700 border border-amber-200/80 ${className}`}
        >
          <Clock className="h-3 w-3 text-amber-600" />
          <span>PENDING</span>
        </span>
      );
    case "SENT":
      return (
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-emerald-50 text-emerald-700 border border-emerald-200/80 ${className}`}
        >
          <CheckCircle2 className="h-3 w-3 text-emerald-600" />
          <span>SENT</span>
        </span>
      );
    case "FAILED":
      return (
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-rose-50 text-rose-700 border border-rose-200/80 ${className}`}
        >
          <AlertCircle className="h-3 w-3 text-rose-600" />
          <span>FAILED</span>
        </span>
      );
    case "BOUNCED":
      return (
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-purple-50 text-purple-700 border border-purple-200/80 ${className}`}
        >
          <Ban className="h-3 w-3 text-purple-600" />
          <span>BOUNCED</span>
        </span>
      );
    case "SUPPRESSED":
      return (
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-slate-100 text-slate-700 border border-slate-200 ${className}`}
        >
          <ShieldAlert className="h-3 w-3 text-slate-600" />
          <span>SUPPRESSED</span>
        </span>
      );
    default:
      return (
        <span
          className={`inline-flex items-center px-2 py-0.5 rounded-full font-medium text-xs bg-slate-100 text-slate-700 ${className}`}
        >
          {status}
        </span>
      );
  }
};
