import React from "react";
import { Filter, Layers, Mail, RotateCcw } from "lucide-react";
import type { CampaignStepAnalytics } from "../../../types/campaign";

interface AnalyticsScopeToolbarProps {
  steps: CampaignStepAnalytics[];
  selectedStepNumber: number | null;
  onSelectStep: (stepNumber: number | null) => void;
}

export const AnalyticsScopeToolbar: React.FC<AnalyticsScopeToolbarProps> = ({
  steps = [],
  selectedStepNumber,
  onSelectStep,
}) => {
  const activeStep = steps.find((s) => s.step_number === selectedStepNumber);

  return (
    <div
      className="bg-white rounded-xl p-3 sm:p-4 border border-slate-200/90 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-3"
      data-testid="analytics-scope-toolbar"
    >
      {/* Current Scope Label */}
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
          <Layers className="h-4 w-4" />
        </div>
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Tracking Scope:
            </span>
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-indigo-50 text-indigo-700 border border-indigo-200/80">
              {selectedStepNumber === null ? (
                <>
                  <Layers className="h-3 w-3" />
                  <span>All Campaign Emails</span>
                </>
              ) : (
                <>
                  <Mail className="h-3 w-3" />
                  <span>
                    {activeStep?.step_number === 1
                      ? "Step 1: Initial Outreach"
                      : `Step ${activeStep?.step_number}: Follow-Up #${(activeStep?.step_number || 2) - 1}`}
                  </span>
                </>
              )}
            </span>
          </div>
          <p className="text-[11px] text-slate-500 mt-0.5">
            {selectedStepNumber === null
              ? "Displaying aggregate campaign-wide performance and recipient engagement."
              : `Scoped to "${activeStep?.subject || `Step ${selectedStepNumber}`}". Showing email-level metrics and drilldown.`}
          </p>
        </div>
      </div>

      {/* Scope Controls */}
      <div className="flex items-center gap-2 self-start sm:self-auto flex-wrap">
        <div className="relative inline-flex items-center">
          <label htmlFor="analytics-email-scope-select" className="sr-only">
            Select email scope
          </label>
          <select
            id="analytics-email-scope-select"
            value={selectedStepNumber === null ? "all" : String(selectedStepNumber)}
            onChange={(e) => {
              const val = e.target.value;
              onSelectStep(val === "all" ? null : Number(val));
            }}
            className="pl-8 pr-8 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-700 hover:bg-slate-100 hover:border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 transition-colors cursor-pointer appearance-none"
            data-testid="scope-select-dropdown"
          >
            <option value="all">All Campaign Emails (Aggregate)</option>
            {steps.map((s) => {
              const label =
                s.step_number === 1
                  ? "Step 1: Initial Outreach"
                  : `Step ${s.step_number}: Follow-Up #${s.step_number - 1}`;
              return (
                <option key={s.step_id || s.step_number} value={String(s.step_number)}>
                  {label} — {s.subject || `Step ${s.step_number}`}
                </option>
              );
            })}
          </select>
          <Filter className="h-3.5 w-3.5 text-slate-400 absolute left-2.5 pointer-events-none" />
        </div>

        {selectedStepNumber !== null && (
          <button
            type="button"
            onClick={() => onSelectStep(null)}
            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-slate-200 text-xs font-medium text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors cursor-pointer"
            title="Reset to All Campaign Emails"
            data-testid="reset-scope-button"
          >
            <RotateCcw className="h-3 w-3 text-slate-400" />
            <span>Reset Scope</span>
          </button>
        )}
      </div>
    </div>
  );
};
