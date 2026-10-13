import React from "react";
import type { CampaignStatus } from "../../types/campaign";
import { cn } from "../../lib/utils";

interface CampaignStatusBadgeProps {
  status: CampaignStatus;
  className?: string;
}

export const CampaignStatusBadge: React.FC<CampaignStatusBadgeProps> = ({
  status,
  className,
}) => {
  switch (status) {
    case "RUNNING":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200/60 shadow-2xs select-none",
            className
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-600 animate-pulse" />
          RUNNING
        </span>
      );

    case "SCHEDULED":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200 select-none",
            className
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
          SCHEDULED
        </span>
      );

    case "QUEUED":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-sky-50 text-sky-700 border border-sky-200 select-none",
            className
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-sky-500 animate-pulse" />
          QUEUED
        </span>
      );

    case "PAUSED":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-neutral-100 text-neutral-700 border border-neutral-200 select-none",
            className
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-neutral-500" />
          PAUSED
        </span>
      );

    case "COMPLETED":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 select-none",
            className
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          COMPLETED
        </span>
      );

    case "DRAFT":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-neutral-100 text-neutral-600 border border-neutral-200 select-none",
            className
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-neutral-400" />
          DRAFT
        </span>
      );

    case "CANCELLED":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-500 border border-slate-200 select-none",
            className
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
          CANCELLED
        </span>
      );

    case "FAILED":
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200 select-none",
            className
          )}
        >
          <span className="w-1.5 h-1.5 rounded-full bg-rose-600" />
          FAILED
        </span>
      );

    default:
      return (
        <span
          className={cn(
            "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200 select-none",
            className
          )}
        >
          {status}
        </span>
      );
  }
};
