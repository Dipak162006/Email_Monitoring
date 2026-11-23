import React from "react";
import { BarChart2, ArrowRight, Check } from "lucide-react";
import type { CampaignStepAnalytics } from "../../../types/campaign";

interface CampaignSequencePerformanceTableProps {
  steps: CampaignStepAnalytics[];
  selectedStepNumber: number | null;
  onSelectStep: (stepNumber: number | null) => void;
}

export const CampaignSequencePerformanceTable: React.FC<CampaignSequencePerformanceTableProps> = ({
  steps = [],
  selectedStepNumber,
  onSelectStep,
}) => {
  return (
    <div
      className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs space-y-3.5"
      data-testid="sequence-performance-section"
    >
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
            <BarChart2 className="h-3.5 w-3.5" />
          </div>
          <div>
            <h3 className="text-xs sm:text-sm font-bold text-slate-900">
              Email Sequence Performance <span className="sr-only">Step Performance</span>
            </h3>
            <p className="text-[11px] text-slate-500">
              Interactive per-email metrics. Click any row to filter top KPIs and recipient drilldown to that step.
            </p>
          </div>
        </div>

        <span className="text-[11px] text-slate-400">
          {steps.length} {steps.length === 1 ? "step" : "steps"} configured
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto [scrollbar-width:thin]">
        <table className="w-full text-left text-xs" data-testid="sequence-performance-table">
          <thead>
            <tr className="border-b border-slate-100 text-[11px] text-slate-400 uppercase font-semibold bg-slate-50/50">
              <th className="py-2.5 px-3">Step</th>
              <th className="py-2.5 px-3">Email Subject</th>
              <th className="py-2.5 px-3 text-center">Recipients</th>
              <th className="py-2.5 px-3 text-center" title="Total sent deliveries and unique recipients sent">Sent (Total / Uniq)</th>
              <th className="py-2.5 px-3 text-center">Opens (Uniq / Raw)</th>
              <th className="py-2.5 px-3 text-center">Open Rate</th>
              <th className="py-2.5 px-3 text-center">Clicks (Uniq / Raw)</th>
              <th className="py-2.5 px-3 text-center">Click Rate</th>
              <th className="py-2.5 px-3 text-center">Replies</th>
              <th className="py-2.5 px-3 text-center">Bounced / Failed</th>
              <th className="py-2.5 px-3 text-right">Scope</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-slate-700">
            {steps.map((step) => {
              const isSelected = selectedStepNumber === step.step_number;
              const stepName =
                step.step_number === 1 ? "Initial Outreach" : `Follow-Up #${step.step_number - 1}`;
              
              const sent = step.sent_count ?? 0;
              const uniqueSent = step.unique_recipients_sent ?? 0;
              const uniqueOpens = step.unique_open_recipients ?? 0;
              const rawOpens = step.raw_open_count ?? 0;
              const rawOpenRate =
                step.open_rate !== undefined && step.open_rate !== null
                  ? step.open_rate
                  : uniqueSent > 0
                  ? roundVal((uniqueOpens / uniqueSent) * 100)
                  : 0.0;
              const openRate = Number.isFinite(Number(rawOpenRate)) ? Number(rawOpenRate) : 0.0;

              const uniqueClicks = step.unique_click_recipients ?? 0;
              const rawClicks = step.raw_click_count ?? 0;
              const rawClickRate =
                step.click_rate !== undefined && step.click_rate !== null
                  ? step.click_rate
                  : uniqueSent > 0
                  ? roundVal((uniqueClicks / uniqueSent) * 100)
                  : 0.0;
              const clickRate = Number.isFinite(Number(rawClickRate)) ? Number(rawClickRate) : 0.0;

              const bounced = step.bounced_count ?? 0;
              const failed = step.failed_count ?? 0;
              const replies = step.replied_count ?? 0;
              const rawReplyRate = step.reply_rate !== undefined && step.reply_rate !== null
                ? step.reply_rate
                : (sent > 0 ? roundVal((replies / sent) * 100) : 0.0);
              const replyRate = Number.isFinite(Number(rawReplyRate)) ? Number(rawReplyRate) : 0.0;

              return (
                <tr
                  key={step.step_id || step.step_number}
                  onClick={() => onSelectStep(isSelected ? null : step.step_number)}
                  className={`transition-all cursor-pointer ${
                    isSelected
                      ? "bg-indigo-50/70 border-l-4 border-indigo-600 font-medium"
                      : "hover:bg-slate-50/80"
                  }`}
                  data-testid={`sequence-row-${step.step_number}`}
                  title={isSelected ? "Click to deselect (Show all emails)" : `Click to filter tracking to Step ${step.step_number}`}
                >
                  {/* Step Number */}
                  <td className="py-3 px-3">
                    <span
                      className={`w-6 h-6 rounded-full font-bold text-[11px] flex items-center justify-center ${
                        isSelected
                          ? "bg-indigo-600 text-white shadow-2xs"
                          : "bg-slate-100 text-slate-700"
                      }`}
                    >
                      {step.step_number}
                    </span>
                  </td>

                  {/* Subject and Step Name */}
                  <td className="py-3 px-3 max-w-xs">
                    <div className="flex flex-col min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-semibold text-slate-900 text-xs truncate">
                          {stepName}
                        </span>
                        <span
                          className={`text-[10px] px-1.5 py-0.2 rounded font-medium border ${
                            step.is_active === false
                              ? "text-amber-700 bg-amber-50 border-amber-200/60"
                              : "text-emerald-700 bg-emerald-50 border-emerald-200/60"
                          }`}
                        >
                          {step.is_active === false ? "Inactive" : "Active"}
                        </span>
                        {step.delay_hours > 0 && (
                          <span className="text-[10px] text-slate-400 font-medium bg-slate-100 px-1.5 py-0.2 rounded">
                            +{step.delay_hours}h delay
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] text-slate-500 truncate mt-0.5">
                        {step.subject || "No subject specified"}
                      </span>
                    </div>
                  </td>

                  {/* Recipients */}
                  <td className="py-3 px-3 text-center font-medium">
                    {(step.targeted_count ?? 0).toLocaleString()}
                  </td>

                  {/* Sent Deliveries */}
                  <td className="py-3 px-3 text-center">
                    <span className="font-semibold text-slate-900">
                      {sent.toLocaleString()}
                    </span>
                    <span className="text-[10px] text-slate-400 font-normal ml-1">
                      ({uniqueSent.toLocaleString()} uniq)
                    </span>
                  </td>

                  {/* Opens */}
                  <td className="py-3 px-3 text-center">
                    <span className="font-semibold text-blue-700">
                      {uniqueOpens.toLocaleString()}
                    </span>
                    <span className="text-slate-400 text-[10px] ml-1">
                      / {rawOpens.toLocaleString()}
                    </span>
                  </td>

                  {/* Open Rate */}
                  <td className="py-3 px-3 text-center">
                    <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700">
                      {openRate.toFixed(1)}%
                    </span>
                  </td>

                  {/* Clicks */}
                  <td className="py-3 px-3 text-center">
                    <span className="font-semibold text-indigo-700">
                      {uniqueClicks.toLocaleString()}
                    </span>
                    <span className="text-slate-400 text-[10px] ml-1">
                      / {rawClicks.toLocaleString()}
                    </span>
                  </td>

                  {/* Click Rate */}
                  <td className="py-3 px-3 text-center">
                    <span className="inline-block px-2 py-0.5 rounded-full text-[11px] font-bold bg-indigo-50 text-indigo-700">
                      {clickRate.toFixed(1)}%
                    </span>
                  </td>

                  {/* Replies */}
                  <td className="py-3 px-3 text-center">
                    <span className="font-semibold text-slate-800">
                      {replies.toLocaleString()}
                    </span>
                    <span className="text-slate-400 text-[10px] ml-1">
                      ({replyRate.toFixed(1)}%)
                    </span>
                  </td>

                  {/* Bounced / Failed */}
                  <td className="py-3 px-3 text-center text-[11px]">
                    {bounced > 0 ? (
                      <span className="text-rose-600 font-semibold">{bounced} bnc</span>
                    ) : (
                      <span className="text-slate-400">0</span>
                    )}
                    {failed > 0 && (
                      <span className="text-amber-600 font-semibold ml-1">/ {failed} fail</span>
                    )}
                  </td>

                  {/* Selection Button */}
                  <td className="py-3 px-3 text-right">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectStep(isSelected ? null : step.step_number);
                      }}
                      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors cursor-pointer ${
                        isSelected
                          ? "bg-indigo-600 text-white hover:bg-indigo-700"
                          : "bg-slate-100 text-slate-700 hover:bg-indigo-50 hover:text-indigo-700"
                      }`}
                      data-testid={`select-scope-step-${step.step_number}`}
                    >
                      {isSelected ? (
                        <>
                          <Check className="h-3 w-3" />
                          <span>Active Scope</span>
                        </>
                      ) : (
                        <>
                          <span>Scope to Step</span>
                          <ArrowRight className="h-3 w-3" />
                        </>
                      )}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

function roundVal(n: number): number {
  return Math.round(n * 10) / 10;
}
