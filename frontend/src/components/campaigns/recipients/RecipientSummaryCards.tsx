import React from "react";
import { Users, Clock, CheckCircle2, ShieldAlert } from "lucide-react";
import type { Campaign, CampaignRecipient } from "../../../types/campaign";

interface RecipientSummaryCardsProps {
  campaign: Campaign | null;
  recipients: CampaignRecipient[];
  isLoading?: boolean;
}

export const RecipientSummaryCards: React.FC<RecipientSummaryCardsProps> = ({
  campaign,
  recipients,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 w-full min-w-0">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs animate-pulse space-y-3"
          >
            <div className="flex items-center justify-between">
              <div className="h-3.5 bg-slate-200 rounded w-24"></div>
              <div className="h-8 w-8 bg-slate-200 rounded-lg"></div>
            </div>
            <div className="h-7 bg-slate-200 rounded w-16"></div>
            <div className="h-3 bg-slate-100 rounded w-32"></div>
          </div>
        ))}
      </div>
    );
  }

  const totalCount = campaign?.recipient_count ?? recipients.length;
  const pendingCount = recipients.filter((r) => r.status === "PENDING").length;
  const sentCount = recipients.filter((r) => r.status === "SENT").length;
  const excludedCount = recipients.filter(
    (r) => r.status === "SUPPRESSED" || r.status === "BOUNCED" || r.status === "FAILED"
  ).length;

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 w-full min-w-0">
      {/* Card 1: Total Audience Target */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs flex flex-col justify-between min-w-0">
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="text-xs font-medium text-slate-500 truncate">Total Audience</span>
          <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
            <Users className="h-4 w-4" />
          </div>
        </div>
        <div>
          <div className="text-2xl font-semibold text-slate-900 tracking-tight" data-testid="metric-total">
            {totalCount.toLocaleString()}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 truncate">Audience records configured</p>
        </div>
      </div>

      {/* Card 2: Pending Dispatch */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs flex flex-col justify-between min-w-0">
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="text-xs font-medium text-slate-500 truncate">Pending Launch</span>
          <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 flex items-center justify-center shrink-0">
            <Clock className="h-4 w-4" />
          </div>
        </div>
        <div>
          <div className="text-2xl font-semibold text-slate-900 tracking-tight" data-testid="metric-pending">
            {pendingCount.toLocaleString()}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 truncate">Awaiting campaign launch</p>
        </div>
      </div>

      {/* Card 3: Dispatched / Sent */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs flex flex-col justify-between min-w-0">
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="text-xs font-medium text-slate-500 truncate">Dispatched</span>
          <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0">
            <CheckCircle2 className="h-4 w-4" />
          </div>
        </div>
        <div>
          <div className="text-2xl font-semibold text-slate-900 tracking-tight" data-testid="metric-sent">
            {sentCount.toLocaleString()}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 truncate">Confirmed deliveries</p>
        </div>
      </div>

      {/* Card 4: Suppressed / Excluded */}
      <div className="bg-white p-4 rounded-xl border border-slate-200/80 shadow-2xs flex flex-col justify-between min-w-0">
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="text-xs font-medium text-slate-500 truncate">Excluded</span>
          <div className="w-8 h-8 rounded-lg bg-slate-100 text-slate-600 flex items-center justify-center shrink-0">
            <ShieldAlert className="h-4 w-4" />
          </div>
        </div>
        <div>
          <div className="text-2xl font-semibold text-slate-900 tracking-tight" data-testid="metric-excluded">
            {excludedCount.toLocaleString()}
          </div>
          <p className="text-xs text-slate-500 mt-0.5 truncate">Suppressed or bounced</p>
        </div>
      </div>
    </div>
  );
};
