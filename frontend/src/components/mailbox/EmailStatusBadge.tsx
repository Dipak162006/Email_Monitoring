import React from "react";
import { CornerDownLeft } from "lucide-react";
import { cn } from "../../lib/utils";

export type BadgeStatusType =
  | "Hard Bounce"
  | "Delivered"
  | "Response"
  | "Sent"
  | "Unread"
  | "Draft"
  | "Failed";

interface EmailStatusBadgeProps {
  status: BadgeStatusType | string;
  className?: string;
}

export const EmailStatusBadge: React.FC<EmailStatusBadgeProps> = ({ status, className }) => {
  switch (status) {
    case "Hard Bounce":
    case "BOUNCED":
      return (
        <span
          className={cn(
            "px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 text-xs font-medium inline-flex items-center",
            className
          )}
        >
          Hard Bounce
        </span>
      );
    case "Delivered":
      return (
        <span
          className={cn(
            "px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-medium inline-flex items-center",
            className
          )}
        >
          Delivered
        </span>
      );
    case "Response":
      return (
        <span
          className={cn(
            "px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200 text-xs font-medium inline-flex items-center gap-1",
            className
          )}
        >
          <CornerDownLeft className="h-3 w-3" />
          Response
        </span>
      );
    case "Sent":
    case "SENT":
      return (
        <span
          className={cn(
            "px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-xs font-medium inline-flex items-center",
            className
          )}
        >
          Sent
        </span>
      );
    case "Unread":
      return (
        <span
          className={cn(
            "px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 text-xs font-medium inline-flex items-center",
            className
          )}
        >
          Unread
        </span>
      );
    case "Draft":
    case "DRAFT":
      return (
        <span
          className={cn(
            "px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 text-xs font-medium inline-flex items-center",
            className
          )}
        >
          Draft
        </span>
      );
    case "Failed":
    case "FAILED":
      return (
        <span
          className={cn(
            "px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200 text-xs font-medium inline-flex items-center",
            className
          )}
        >
          Failed
        </span>
      );
    default:
      return (
        <span
          className={cn(
            "px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-xs font-medium inline-flex items-center",
            className
          )}
        >
          {status}
        </span>
      );
  }
};
