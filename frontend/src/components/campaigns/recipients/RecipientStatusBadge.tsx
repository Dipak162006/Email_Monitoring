import React from "react";
import {
  Clock,
  CheckCircle2,
  AlertCircle,
  Ban,
  ShieldAlert,
  StopCircle,
  CheckCheck,
  MessageSquare,
  UserX,
} from "lucide-react";
import type { CampaignRecipientStatus } from "../../../types/campaign";

interface RecipientStatusBadgeProps {
  status: CampaignRecipientStatus;
  stoppedReason?: string | null;
  currentStepNumber?: number;
  nextStepDueAt?: string | null;
  className?: string;
}

export const RecipientStatusBadge: React.FC<RecipientStatusBadgeProps> = ({
  status,
  stoppedReason,
  currentStepNumber,
  nextStepDueAt,
  className = "",
}) => {
  // 1. Stopped states
  if (status === "STOPPED") {
    switch (stoppedReason) {
      case "REPLIED":
        return (
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-indigo-50 text-indigo-700 border border-indigo-200/80 ${className}`}
          >
            <MessageSquare className="h-3 w-3 text-indigo-600" />
            <span>Stopped — replied</span>
          </span>
        );
      case "BOUNCED":
        return (
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-purple-50 text-purple-700 border border-purple-200/80 ${className}`}
          >
            <Ban className="h-3 w-3 text-purple-600" />
            <span>Stopped — bounced</span>
          </span>
        );
      case "UNSUBSCRIBED":
        return (
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-amber-50 text-amber-700 border border-amber-200/80 ${className}`}
          >
            <UserX className="h-3 w-3 text-amber-600" />
            <span>Stopped — unsubscribed</span>
          </span>
        );
      case "CAMPAIGN_CANCELLED":
        return (
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-slate-100 text-slate-600 border border-slate-200 ${className}`}
          >
            <Ban className="h-3 w-3 text-slate-500" />
            <span>Stopped — cancelled</span>
          </span>
        );
      case "MANUAL":
        return (
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-rose-50 text-rose-700 border border-rose-200/80 ${className}`}
          >
            <StopCircle className="h-3 w-3 text-rose-600" />
            <span>Stopped manually</span>
          </span>
        );
      default:
        return (
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-slate-100 text-slate-700 border border-slate-200 ${className}`}
          >
            <StopCircle className="h-3 w-3 text-slate-600" />
            <span>Stopped</span>
          </span>
        );
    }
  }

  // 2. Sequence Completed
  if (status === "COMPLETED") {
    return (
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-emerald-50 text-emerald-700 border border-emerald-200/80 ${className}`}
      >
        <CheckCheck className="h-3 w-3 text-emerald-600" />
        <span>Sequence completed</span>
      </span>
    );
  }

  // 3. Active / Sent with scheduled next step
  if (nextStepDueAt && (status === "SENT" || status === "ACTIVE")) {
    const nextStepNum = (currentStepNumber || 1) + 1;
    return (
      <span
        className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-blue-50 text-blue-700 border border-blue-200/80 ${className}`}
      >
        <Clock className="h-3 w-3 text-blue-600" />
        <span>Step {nextStepNum} scheduled</span>
      </span>
    );
  }

  // 4. Standard lifecycle statuses
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
    case "ACTIVE":
      return (
        <span
          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full font-medium text-xs bg-blue-50 text-blue-700 border border-blue-200/80 ${className}`}
        >
          <Clock className="h-3 w-3 text-blue-600" />
          <span>ACTIVE</span>
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
