import React from "react";
import {
  TrendingUp,
  Send,
  Reply,
  AlertTriangle,
  Clock,
  SkipForward,
  Users,
  Tag,
  Info,
} from "lucide-react";
import type { CampaignAnalyticsResponse, CampaignStepAnalytics } from "../../types/campaign";

interface CampaignStepAnalyticsFunnelProps {
  analytics?: CampaignAnalyticsResponse | null;
  isLoading?: boolean;
}

export const CampaignStepAnalyticsFunnel: React.FC<CampaignStepAnalyticsFunnelProps> = ({
  analytics,
  isLoading = false,
}) => {
  if (isLoading) {
    return (
      <div
        className="bg-white rounded-xl p-6 border border-slate-200/80 shadow-2xs space-y-4 animate-pulse"
        data-testid="step-analytics-loading"
      >
        <div className="h-6 bg-slate-200 rounded w-1/3"></div>
        <div className="h-4 bg-slate-100 rounded w-1/2"></div>
        <div className="h-32 bg-slate-50 rounded-lg"></div>
      </div>
    );
  }

  if (!analytics || !analytics.steps || analytics.steps.length === 0) {
    return (
      <div
        className="bg-white rounded-xl p-6 border border-slate-200/80 shadow-2xs text-center py-10"
        data-testid="step-analytics-empty"
      >
        <div className="w-12 h-12 rounded-full bg-slate-50 text-slate-400 flex items-center justify-center mx-auto mb-3">
          <TrendingUp className="h-6 w-6" />
        </div>
        <h3 className="text-sm font-semibold text-slate-800">No Step Analytics Available</h3>
        <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
          Step funnel metrics will appear once steps and recipients are configured for this campaign.
        </p>
      </div>
    );
  }

  return (
    <div
      className="bg-white rounded-xl p-5 md:p-6 border border-slate-200/80 shadow-2xs space-y-6"
      data-testid="campaign-step-analytics-funnel"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
            <TrendingUp className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base sm:text-lg font-bold text-slate-900">
                Step-Level Analytics Funnel
              </h2>
              <span className="px-2 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200/60">
                M7 Funnel
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Per-step conversion rates and delivery outcomes derived from persisted records.
            </p>
          </div>
        </div>

        {analytics.omitted_metrics_notice && (
          <div
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-50/80 border border-amber-200/70 text-amber-800 text-xs self-start sm:self-auto max-w-md"
            title={analytics.omitted_metrics_notice}
            data-testid="omitted-metrics-notice"
          >
            <Info className="h-3.5 w-3.5 shrink-0 text-amber-600" />
            <span className="truncate">Open & click tracking omitted (no tracking pixels used)</span>
          </div>
        )}
      </div>

      {/* Steps List */}
      <div className="space-y-4">
        {analytics.steps.map((step: CampaignStepAnalytics) => {
          const isInitial = step.step_number === 1;
          const hasTags = step.target_tags && step.target_tags.length > 0;

          // Proportional bar calculation
          const totalT = step.targeted_count || 0;
          const sentP = totalT > 0 ? (step.sent_count / totalT) * 100 : 0;
          const bounceP = totalT > 0 ? (step.bounced_count / totalT) * 100 : 0;
          const skipP = totalT > 0 ? (step.skipped_count / totalT) * 100 : 0;
          const pendingP = totalT > 0 ? (step.pending_count / totalT) * 100 : 0;

          return (
            <div
              key={step.step_id}
              className="p-4 sm:p-5 rounded-xl border border-slate-200/90 bg-slate-50/40 hover:bg-slate-50/80 transition-colors space-y-4"
              data-testid={`step-funnel-card-${step.step_number}`}
            >
              {/* Step Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                <div className="flex items-center gap-2.5 flex-wrap">
                  <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-slate-900 text-white shadow-2xs">
                    Step {step.step_number}
                  </span>
                  <span className="text-xs font-semibold text-slate-700">
                    {isInitial ? "Initial Dispatch" : `Follow-Up (+${step.delay_hours}h delay)`}
                  </span>
                  <span className="text-xs text-slate-400 font-normal truncate max-w-xs sm:max-w-md" title={step.subject}>
                    "{step.subject}"
                  </span>
                </div>

                {/* Target Tags / Audience Filter */}
                <div className="flex items-center gap-1.5 self-start sm:self-auto flex-wrap">
                  {hasTags ? (
                    <div className="flex items-center gap-1">
                      <Tag className="h-3 w-3 text-indigo-500" />
                      <span className="text-[11px] font-medium text-slate-500">Targeting:</span>
                      {step.target_tags.map((tag) => (
                        <span
                          key={tag}
                          className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200"
                        >
                          {tag}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
                      All Recipients
                    </span>
                  )}
                </div>
              </div>

              {/* Conversion Rate Badges */}
              <div className="flex flex-wrap items-center gap-3 pt-1">
                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200/70 text-emerald-800 text-xs">
                  <span className="font-semibold text-emerald-900">Delivery Rate:</span>
                  <span className="font-bold" data-testid={`delivery-rate-${step.step_number}`}>
                    {step.delivery_rate}%
                  </span>
                </div>

                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-50 border border-indigo-200/70 text-indigo-800 text-xs">
                  <span className="font-semibold text-indigo-900">Reply Rate:</span>
                  <span className="font-bold" data-testid={`reply-rate-${step.step_number}`}>
                    {step.reply_rate}%
                  </span>
                </div>

                <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-50 border border-rose-200/70 text-rose-800 text-xs">
                  <span className="font-semibold text-rose-900">Bounce Rate:</span>
                  <span className="font-bold" data-testid={`bounce-rate-${step.step_number}`}>
                    {step.bounce_rate}%
                  </span>
                </div>
              </div>

              {/* Metric Breakdown Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5 pt-1">
                <div className="bg-white p-3 rounded-lg border border-slate-200/70">
                  <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                    <Users className="h-3.5 w-3.5 text-slate-400" />
                    <span className="text-[11px] font-medium uppercase tracking-wider">Targeted</span>
                  </div>
                  <span className="text-lg font-bold text-slate-900" data-testid={`metric-targeted-${step.step_number}`}>
                    {step.targeted_count.toLocaleString()}
                  </span>
                </div>

                <div className="bg-white p-3 rounded-lg border border-slate-200/70">
                  <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                    <Send className="h-3.5 w-3.5 text-emerald-500" />
                    <span className="text-[11px] font-medium uppercase tracking-wider">Sent</span>
                  </div>
                  <span className="text-lg font-bold text-slate-900" data-testid={`metric-sent-${step.step_number}`}>
                    {step.sent_count.toLocaleString()}
                  </span>
                </div>

                <div className="bg-white p-3 rounded-lg border border-slate-200/70">
                  <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                    <Reply className="h-3.5 w-3.5 text-indigo-500" />
                    <span className="text-[11px] font-medium uppercase tracking-wider">Replied</span>
                  </div>
                  <span className="text-lg font-bold text-slate-900" data-testid={`metric-replied-${step.step_number}`}>
                    {step.replied_count.toLocaleString()}
                  </span>
                </div>

                <div className="bg-white p-3 rounded-lg border border-slate-200/70">
                  <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                    <Clock className="h-3.5 w-3.5 text-blue-500" />
                    <span className="text-[11px] font-medium uppercase tracking-wider">Pending</span>
                  </div>
                  <span className="text-lg font-bold text-slate-900" data-testid={`metric-pending-${step.step_number}`}>
                    {step.pending_count.toLocaleString()}
                  </span>
                </div>

                <div className="bg-white p-3 rounded-lg border border-slate-200/70">
                  <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                    <AlertTriangle className="h-3.5 w-3.5 text-rose-500" />
                    <span className="text-[11px] font-medium uppercase tracking-wider">Bounced</span>
                  </div>
                  <span className="text-lg font-bold text-slate-900" data-testid={`metric-bounced-${step.step_number}`}>
                    {step.bounced_count.toLocaleString()}
                  </span>
                </div>

                <div className="bg-white p-3 rounded-lg border border-slate-200/70">
                  <div className="flex items-center gap-1.5 text-slate-500 mb-1">
                    <SkipForward className="h-3.5 w-3.5 text-amber-500" />
                    <span className="text-[11px] font-medium uppercase tracking-wider">Skipped</span>
                  </div>
                  <span className="text-lg font-bold text-slate-900" data-testid={`metric-skipped-${step.step_number}`}>
                    {step.skipped_count.toLocaleString()}
                  </span>
                </div>
              </div>

              {/* Proportional Mini-Funnel Bar */}
              {totalT > 0 && (
                <div className="pt-2">
                  <div
                    className="w-full bg-slate-200 rounded-full h-2 overflow-hidden flex"
                    data-testid={`step-funnel-bar-${step.step_number}`}
                  >
                    <div
                      className="bg-emerald-500 h-full transition-all duration-300"
                      style={{ width: `${sentP}%` }}
                      title={`Sent: ${step.sent_count}`}
                    />
                    <div
                      className="bg-blue-400 h-full transition-all duration-300"
                      style={{ width: `${pendingP}%` }}
                      title={`Pending: ${step.pending_count}`}
                    />
                    <div
                      className="bg-amber-400 h-full transition-all duration-300"
                      style={{ width: `${skipP}%` }}
                      title={`Skipped: ${step.skipped_count}`}
                    />
                    <div
                      className="bg-rose-500 h-full transition-all duration-300"
                      style={{ width: `${bounceP}%` }}
                      title={`Bounced: ${step.bounced_count}`}
                    />
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

