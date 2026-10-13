import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Send,
  Calendar,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Loader2,
  X,
  RefreshCw,
  Users,
  FileEdit,
  Clock,
} from "lucide-react";
import type { CampaignDetail, CampaignPreflightResponse } from "../../types/campaign";

export interface CampaignPreflightModalProps {
  isOpen: boolean;
  mode: "launch" | "schedule";
  campaign: CampaignDetail;
  preflight: CampaignPreflightResponse | null;
  isLoadingPreflight: boolean;
  preflightError: string | null;
  onRetryPreflight: () => void;
  onClose: () => void;
  onConfirmLaunch: () => void;
  onConfirmSchedule: (scheduledAtIso: string) => void;
  isSubmitting?: boolean;
}

export const CampaignPreflightModal: React.FC<CampaignPreflightModalProps> = ({
  isOpen,
  mode,
  campaign,
  preflight,
  isLoadingPreflight,
  preflightError,
  onRetryPreflight,
  onClose,
  onConfirmLaunch,
  onConfirmSchedule,
  isSubmitting = false,
}) => {
  // Local scheduled datetime state
  const [scheduledDateTime, setScheduledDateTime] = useState<string>("");
  const [scheduleError, setScheduleError] = useState<string | null>(null);

  // Initialize default scheduled date/time (prefill existing future scheduled_at or tomorrow at 09:00 local time)
  useEffect(() => {
    if (isOpen) {
      const pad = (n: number) => String(n).padStart(2, "0");
      let initialDate: Date;

      if (campaign.scheduled_at) {
        const parsed = new Date(campaign.scheduled_at);
        if (!isNaN(parsed.getTime()) && parsed.getTime() > Date.now()) {
          initialDate = parsed;
        } else {
          initialDate = new Date();
          initialDate.setDate(initialDate.getDate() + 1);
          initialDate.setHours(9, 0, 0, 0);
        }
      } else {
        initialDate = new Date();
        initialDate.setDate(initialDate.getDate() + 1);
        initialDate.setHours(9, 0, 0, 0);
      }

      const defaultTime = `${initialDate.getFullYear()}-${pad(
        initialDate.getMonth() + 1
      )}-${pad(initialDate.getDate())}T${pad(initialDate.getHours())}:${pad(
        initialDate.getMinutes()
      )}`;

      setScheduledDateTime(defaultTime);
      setScheduleError(null);
    }
  }, [isOpen, mode, campaign.scheduled_at]);

  if (!isOpen) return null;

  const isEligible = preflight?.eligible === true;
  const issues = preflight?.issues || [];

  const handleScheduleSubmit = () => {
    if (!scheduledDateTime) {
      setScheduleError("Please select a scheduled date and time.");
      return;
    }

    const selectedDate = new Date(scheduledDateTime);
    if (isNaN(selectedDate.getTime())) {
      setScheduleError("Invalid date/time selected.");
      return;
    }

    if (selectedDate.getTime() <= Date.now()) {
      setScheduleError("Scheduled launch time must be in the future.");
      return;
    }

    setScheduleError(null);
    onConfirmSchedule(selectedDate.toISOString());
  };

  const handlePrimaryAction = () => {
    if (!isEligible || isLoadingPreflight || isSubmitting) return;

    if (mode === "launch") {
      onConfirmLaunch();
    } else {
      handleScheduleSubmit();
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="preflight-modal-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150"
    >
      <div className="bg-white rounded-2xl shadow-2xl border border-slate-200/80 max-w-xl w-full max-h-[90vh] flex flex-col overflow-hidden text-slate-800">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-100 flex items-start justify-between gap-4 bg-slate-50/50">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
              {mode === "launch" ? (
                <Send className="h-5 w-5" />
              ) : (
                <Calendar className="h-5 w-5" />
              )}
            </div>
            <div className="min-w-0">
              <h2
                id="preflight-modal-title"
                className="text-base sm:text-lg font-bold text-slate-900 truncate"
              >
                {mode === "launch"
                  ? "Launch Campaign Now"
                  : "Schedule Campaign Execution"}
              </h2>
              <p className="text-xs text-slate-500 truncate">
                {campaign.name} • #{campaign.id}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors focus:outline-none"
            aria-label="Close modal"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="px-6 py-5 overflow-y-auto space-y-4 flex-1 text-xs">
          {/* 1. Loading Preflight */}
          {isLoadingPreflight && (
            <div className="py-8 text-center space-y-3">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-600 mx-auto" />
              <p className="text-xs font-semibold text-slate-800">
                Running Campaign Preflight Validation...
              </p>
              <p className="text-[11px] text-slate-500 max-w-xs mx-auto">
                Verifying sender account authorization, domain verification status, email content, and suppression criteria.
              </p>
            </div>
          )}

          {/* 2. Error Loading Preflight */}
          {!isLoadingPreflight && preflightError && (
            <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-900 space-y-2">
              <div className="flex items-center gap-2 font-semibold">
                <AlertCircle className="h-4 w-4 text-rose-600 shrink-0" />
                <span>Preflight check could not be completed</span>
              </div>
              <p className="text-xs text-rose-700">{preflightError}</p>
              <button
                type="button"
                onClick={onRetryPreflight}
                className="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-rose-200 text-rose-700 font-semibold text-xs hover:bg-rose-100/50 transition-colors"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                <span>Retry Preflight</span>
              </button>
            </div>
          )}

          {/* 3. Preflight Results */}
          {!isLoadingPreflight && preflight && (
            <>
              {/* Overall Eligibility Status Banner */}
              <div
                className={`p-3.5 rounded-xl border flex items-start gap-3 ${
                  isEligible
                    ? "bg-emerald-50/70 border-emerald-200 text-emerald-900"
                    : "bg-rose-50/70 border-rose-200 text-rose-900"
                }`}
              >
                {isEligible ? (
                  <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0 mt-0.5" />
                ) : (
                  <AlertCircle className="h-5 w-5 text-rose-600 shrink-0 mt-0.5" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="font-bold text-xs sm:text-sm">
                    {isEligible
                      ? "Preflight Validation Passed"
                      : "Preflight Validation Blocked"}
                  </p>
                  <p className="text-[11px] mt-0.5 opacity-90 leading-relaxed">
                    {isEligible
                      ? "All safety checks passed. The campaign is ready for dispatch."
                      : "Execution is blocked until all required errors are resolved."}
                  </p>
                </div>
              </div>

              {/* Sending Interval Summary */}
              <div className="flex items-center justify-between px-3.5 py-2 bg-slate-50 rounded-lg border border-slate-200/70 text-xs">
                <span className="flex items-center gap-1.5 font-medium text-slate-500">
                  <Clock className="h-3.5 w-3.5 text-slate-400" />
                  <span>Sending Interval</span>
                </span>
                <span className="font-semibold text-slate-800">
                  {campaign.send_interval_seconds && campaign.send_interval_seconds > 0
                    ? campaign.send_interval_seconds % 60 === 0
                      ? `${campaign.send_interval_seconds / 60} ${campaign.send_interval_seconds / 60 === 1 ? "minute" : "minutes"}`
                      : `${campaign.send_interval_seconds} ${campaign.send_interval_seconds === 1 ? "second" : "seconds"}`
                    : "No intentional delay (Immediate)"}
                </span>
              </div>

              {/* Recipient Statistics Summary */}
              <div className="grid grid-cols-3 gap-2.5 pt-1">
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 text-center">
                  <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    Total
                  </p>
                  <p className="text-base font-bold text-slate-800 mt-0.5">
                    {preflight.recipient_count.toLocaleString()}
                  </p>
                  <p className="text-[10px] text-slate-500">records</p>
                </div>
                <div className="p-3 rounded-xl bg-emerald-50/50 border border-emerald-100 text-center">
                  <p className="text-[10px] uppercase font-bold text-emerald-600 tracking-wider">
                    Eligible
                  </p>
                  <p className="text-base font-bold text-emerald-700 mt-0.5">
                    {preflight.eligible_recipient_count.toLocaleString()}
                  </p>
                  <p className="text-[10px] text-emerald-600 font-medium">to deliver</p>
                </div>
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 text-center">
                  <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                    Suppressed
                  </p>
                  <p className="text-base font-bold text-slate-600 mt-0.5">
                    {preflight.suppressed_recipient_count.toLocaleString()}
                  </p>
                  <p className="text-[10px] text-slate-500">excluded</p>
                </div>
              </div>

              {/* Validation Issues Findings */}
              {issues.length > 0 && (
                <div className="space-y-2 pt-2">
                  <p className="font-bold text-slate-700 text-[11px] uppercase tracking-wider">
                    Validation Findings ({issues.length})
                  </p>
                  <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                    {issues.map((issue, idx) => (
                      <div
                        key={idx}
                        className={`p-2.5 rounded-lg border flex items-start gap-2.5 text-xs ${
                          issue.blocking
                            ? "bg-rose-50/50 border-rose-200 text-rose-900"
                            : "bg-amber-50/50 border-amber-200 text-amber-900"
                        }`}
                      >
                        {issue.blocking ? (
                          <AlertCircle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
                        ) : (
                          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                        )}
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`px-1.5 py-0.2 rounded text-[9px] font-bold uppercase tracking-wider ${
                                issue.blocking
                                  ? "bg-rose-200 text-rose-800"
                                  : "bg-amber-200 text-amber-800"
                              }`}
                            >
                              {issue.blocking ? "Blocking" : "Warning"}
                            </span>
                            <span className="font-mono text-[10px] text-slate-500">
                              {issue.code}
                            </span>
                          </div>
                          <p className="mt-0.5 text-xs font-medium leading-snug">
                            {issue.message}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Actionable buttons if blocked */}
              {!isEligible && (
                <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
                  <p className="text-[11px] font-semibold text-slate-700">
                    Resolve blocking issues before launching:
                  </p>
                  <div className="flex flex-wrap items-center gap-2">
                    <Link
                      to={`/campaigns/${campaign.id}/edit`}
                      onClick={onClose}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-200 text-slate-700 font-semibold text-xs hover:bg-slate-50 transition-colors shadow-2xs"
                    >
                      <FileEdit className="h-3.5 w-3.5 text-indigo-600" />
                      <span>Edit Campaign Details</span>
                    </Link>
                    <Link
                      to={`/campaigns/${campaign.id}/recipients`}
                      onClick={onClose}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 text-white font-semibold text-xs hover:bg-indigo-700 transition-colors shadow-2xs"
                    >
                      <Users className="h-3.5 w-3.5" />
                      <span>Manage Audience</span>
                    </Link>
                  </div>
                </div>
              )}

              {/* Mode-Specific Configuration when Eligible */}
              {isEligible && (
                <div className="pt-2 border-t border-slate-100 space-y-3">
                  {mode === "schedule" ? (
                    <div className="space-y-1.5">
                      <label
                        htmlFor="scheduled-datetime-input"
                        className="block font-semibold text-slate-800 text-xs"
                      >
                        Target Launch Date &amp; Time
                      </label>
                      <input
                        id="scheduled-datetime-input"
                        type="datetime-local"
                        value={scheduledDateTime}
                        onChange={(e) => {
                          setScheduledDateTime(e.target.value);
                          setScheduleError(null);
                        }}
                        className="w-full px-3 py-2 rounded-lg border border-slate-200 text-xs text-slate-900 bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
                      />
                      <p className="text-[11px] text-slate-500">
                        {campaign.status === "SCHEDULED"
                          ? "Select a new future date/time. The campaign will remain in SCHEDULED state."
                          : "Select a future date/time. The schedule will transition the campaign to SCHEDULED state."}
                      </p>
                      {scheduleError && (
                        <p className="text-xs text-rose-600 font-semibold">
                          {scheduleError}
                        </p>
                      )}
                    </div>
                  ) : (
                    <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
                      <p className="font-semibold text-slate-900">
                        Confirm Immediate Execution
                      </p>
                      <p className="text-[11px] text-slate-600 leading-relaxed">
                        Dispatching now will transition this campaign to <strong>QUEUED</strong> and trigger the Celery delivery worker.
                      </p>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 bg-slate-50/70 border-t border-slate-100 flex items-center justify-end gap-2.5">
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            className="px-4 py-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 font-semibold text-xs transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handlePrimaryAction}
            disabled={!isEligible || isLoadingPreflight || isSubmitting}
            className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs shadow-2xs transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin text-white" />
                <span>Processing...</span>
              </>
            ) : mode === "launch" ? (
              <>
                <Send className="h-3.5 w-3.5" />
                <span>Confirm &amp; Launch Now</span>
              </>
            ) : (
              <>
                <Calendar className="h-3.5 w-3.5" />
                <span>{campaign.status === "SCHEDULED" ? "Confirm & Reschedule" : "Confirm & Schedule"}</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
