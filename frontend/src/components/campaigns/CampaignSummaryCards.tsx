import React from "react";
import { Zap, Clock, FileEdit, CheckCircle2 } from "lucide-react";
import type { Campaign } from "../../types/campaign";

interface CampaignSummaryCardsProps {
  campaigns: Campaign[];
  isLoading?: boolean;
}

export const CampaignSummaryCards: React.FC<CampaignSummaryCardsProps> = ({
  campaigns,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs flex items-center justify-between animate-pulse"
          >
            <div className="flex flex-col gap-2">
              <div className="h-3 w-24 bg-slate-200 rounded" />
              <div className="h-6 w-12 bg-slate-300 rounded" />
              <div className="h-2.5 w-20 bg-slate-100 rounded" />
            </div>
            <div className="w-10 h-10 rounded-lg bg-slate-100" />
          </div>
        ))}
      </div>
    );
  }

  const activeCount = campaigns.filter(
    (c) => c.status === "RUNNING" || c.status === "QUEUED"
  ).length;

  const scheduledCount = campaigns.filter(
    (c) => c.status === "SCHEDULED"
  ).length;

  const draftCount = campaigns.filter(
    (c) => c.status === "DRAFT"
  ).length;

  const completedCount = campaigns.filter(
    (c) => c.status === "COMPLETED"
  ).length;

  const cards = [
    {
      title: "Active Campaigns",
      value: activeCount,
      subtext: activeCount > 0 ? `${activeCount} in delivery` : "No active runs",
      icon: Zap,
      iconBg: "bg-indigo-50 border-indigo-100 text-indigo-600",
      accent: activeCount > 0 ? "text-indigo-600 font-semibold" : "text-slate-400",
    },
    {
      title: "Scheduled",
      value: scheduledCount,
      subtext: scheduledCount > 0 ? "Upcoming dispatches" : "None scheduled",
      icon: Clock,
      iconBg: "bg-amber-50 border-amber-100 text-amber-600",
      accent: scheduledCount > 0 ? "text-amber-600 font-semibold" : "text-slate-400",
    },
    {
      title: "Draft Pipelines",
      value: draftCount,
      subtext: draftCount > 0 ? "Ready to configure" : "No pending drafts",
      icon: FileEdit,
      iconBg: "bg-slate-100 border-slate-200 text-slate-600",
      accent: "text-slate-500",
    },
    {
      title: "Completed",
      value: completedCount,
      subtext: completedCount > 0 ? "Archived pipelines" : "None completed",
      icon: CheckCircle2,
      iconBg: "bg-emerald-50 border-emerald-100 text-emerald-600",
      accent: completedCount > 0 ? "text-emerald-600 font-semibold" : "text-slate-400",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <div
            key={card.title}
            className="bg-white p-4 rounded-xl border border-slate-200 shadow-2xs flex items-center justify-between transition-all hover:border-slate-300"
          >
            <div className="flex flex-col min-w-0">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider truncate">
                {card.title}
              </span>
              <span className="text-2xl font-bold text-slate-900 mt-1 tracking-tight">
                {card.value.toLocaleString()}
              </span>
              <span className={`text-xs mt-1 truncate ${card.accent}`}>
                {card.subtext}
              </span>
            </div>
            <div
              className={`w-10 h-10 rounded-lg border flex items-center justify-center shrink-0 ${card.iconBg}`}
            >
              <Icon className="h-5 w-5" />
            </div>
          </div>
        );
      })}
    </div>
  );
};
