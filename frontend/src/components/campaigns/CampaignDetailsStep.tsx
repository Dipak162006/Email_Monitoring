import React, { useState, useEffect } from "react";
import { Info, AlertCircle, Plus, Clock, Gauge } from "lucide-react";

interface CampaignDetailsStepProps {
  name: string;
  onNameChange: (val: string) => void;
  subject: string;
  onSubjectChange: (val: string) => void;
  sendIntervalSeconds?: number;
  onSendIntervalSecondsChange?: (val: number) => void;
  nameError?: string | null;
  subjectError?: string | null;
  nameInputRef?: React.RefObject<HTMLInputElement>;
  subjectInputRef?: React.RefObject<HTMLInputElement>;
}

export const CampaignDetailsStep: React.FC<CampaignDetailsStepProps> = ({
  name,
  onNameChange,
  subject,
  onSubjectChange,
  sendIntervalSeconds = 0,
  onSendIntervalSecondsChange,
  nameError,
  subjectError,
  nameInputRef,
  subjectInputRef,
}) => {
  // Pacing mode: 'none' (immediate/0s) or 'custom' (> 0s)
  const isCustomPacing = sendIntervalSeconds > 0;
  
  // Default helper calculation for unit and value
  const initialUnit =
    sendIntervalSeconds > 0
      ? sendIntervalSeconds % 60 === 0
        ? "minutes"
        : "seconds"
      : "minutes";
  const initialValue =
    sendIntervalSeconds > 0
      ? initialUnit === "minutes"
        ? Math.floor(sendIntervalSeconds / 60)
        : sendIntervalSeconds
      : 5;

  const [intervalUnit, setIntervalUnit] = useState<"seconds" | "minutes">(initialUnit);
  const [intervalNum, setIntervalNum] = useState<number>(initialValue);

  // Sync internal state when parent props change (e.g. draft edit pre-population)
  useEffect(() => {
    if (sendIntervalSeconds > 0) {
      if (sendIntervalSeconds % 60 === 0) {
        setIntervalUnit("minutes");
        setIntervalNum(Math.floor(sendIntervalSeconds / 60));
      } else {
        setIntervalUnit("seconds");
        setIntervalNum(sendIntervalSeconds);
      }
    }
  }, [sendIntervalSeconds]);

  const handleInsertFirstName = () => {
    const trimmed = subject.trimEnd();
    const newSubject = trimmed ? `${trimmed} {{first_name}}` : "{{first_name}}";
    onSubjectChange(newSubject);
    subjectInputRef?.current?.focus();
  };

  const handleNameInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    if (val.length <= 80) {
      onNameChange(val);
    }
  };

  const handlePacingModeChange = (mode: "none" | "custom") => {
    if (!onSendIntervalSecondsChange) return;
    if (mode === "none") {
      onSendIntervalSecondsChange(0);
    } else {
      const safeNum = Math.max(1, intervalNum || 1);
      const computedSec = intervalUnit === "minutes" ? safeNum * 60 : safeNum;
      onSendIntervalSecondsChange(Math.min(86400, computedSec));
    }
  };

  const handleIntervalNumChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const rawVal = e.target.value;
    const num = parseInt(rawVal, 10);
    if (isNaN(num)) {
      setIntervalNum(0);
      return;
    }
    const maxVal = intervalUnit === "minutes" ? 1440 : 86400;
    const clamped = Math.max(1, Math.min(maxVal, num));
    setIntervalNum(clamped);

    if (onSendIntervalSecondsChange) {
      const totalSec = intervalUnit === "minutes" ? clamped * 60 : clamped;
      onSendIntervalSecondsChange(Math.min(86400, totalSec));
    }
  };

  const handleUnitChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newUnit = e.target.value as "seconds" | "minutes";
    setIntervalUnit(newUnit);

    let newNum = intervalNum;
    if (newUnit === "minutes" && intervalUnit === "seconds") {
      newNum = Math.max(1, Math.round(intervalNum / 60));
    } else if (newUnit === "seconds" && intervalUnit === "minutes") {
      newNum = Math.min(86400, intervalNum * 60);
    }
    setIntervalNum(newNum);

    if (onSendIntervalSecondsChange) {
      const totalSec = newUnit === "minutes" ? newNum * 60 : newNum;
      onSendIntervalSecondsChange(Math.min(86400, totalSec));
    }
  };

  return (
    <section className="space-y-6">
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-6 sm:p-8 space-y-6">
        {/* Step Header */}
        <div className="space-y-1">
          <h2 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
            Campaign Details
          </h2>
          <p className="text-xs sm:text-sm text-slate-500">
            Configure identity, labeling, and default messaging headline.
          </p>
        </div>

        {/* Informational Callout: Draft State */}
        <div className="p-4 rounded-lg bg-indigo-50/60 border border-indigo-100 flex items-start gap-3">
          <Info className="h-5 w-5 text-indigo-600 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-xs sm:text-sm font-semibold text-slate-900 leading-snug">
              Campaign draft state
            </p>
            <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">
              Your campaign will remain a draft until you complete the setup and launch it.
            </p>
          </div>
        </div>

        {/* Form Fields */}
        <div className="space-y-6">
          {/* Campaign Name Field */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label
                htmlFor="campaign-name"
                className="text-xs sm:text-sm font-semibold text-slate-900"
              >
                Campaign Name <span className="text-red-500">*</span>
              </label>
              <span className="text-[11px] text-slate-400 font-normal">
                {name.length}/80 chars
              </span>
            </div>
            <div className="relative">
              <input
                id="campaign-name"
                ref={nameInputRef}
                type="text"
                value={name}
                maxLength={80}
                onChange={handleNameInputChange}
                placeholder="e.g. Product Launch — October"
                aria-required="true"
                aria-invalid={Boolean(nameError)}
                aria-describedby={
                  nameError ? "campaign-name-err" : "campaign-name-help"
                }
                className={`w-full px-3.5 py-2.5 rounded-lg text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 border transition-all focus:outline-none focus:ring-2 ${
                  nameError
                    ? "border-red-300 bg-red-50/20 text-red-900 focus:ring-red-500/20 focus:border-red-600"
                    : "border-slate-200 bg-white focus:ring-indigo-500/20 focus:border-indigo-600 shadow-2xs"
                }`}
              />
              {nameError && (
                <div className="absolute right-3 top-2.5 text-red-500 pointer-events-none">
                  <AlertCircle className="h-5 w-5" />
                </div>
              )}
            </div>
            {nameError ? (
              <p
                id="campaign-name-err"
                role="alert"
                className="text-xs text-red-600 flex items-center gap-1 font-medium mt-1"
              >
                <AlertCircle className="h-3.5 w-3.5" />
                <span>{nameError}</span>
              </p>
            ) : (
              <p
                id="campaign-name-help"
                className="text-xs text-slate-500 mt-1"
              >
                Internal name used to identify this campaign.
              </p>
            )}
          </div>

          {/* Subject Field */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <label
                htmlFor="campaign-subject"
                className="text-xs sm:text-sm font-semibold text-slate-900"
              >
                Subject <span className="text-red-500">*</span>
              </label>
              <button
                type="button"
                onClick={handleInsertFirstName}
                className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 flex items-center gap-1 transition-colors focus:outline-none focus:underline"
              >
                <Plus className="h-3.5 w-3.5" />
                <span>Insert {"{{first_name}}"}</span>
              </button>
            </div>
            <div className="relative">
              <input
                id="campaign-subject"
                ref={subjectInputRef}
                type="text"
                value={subject}
                onChange={(e) => onSubjectChange(e.target.value)}
                placeholder="e.g. Introducing our new product line"
                aria-required="true"
                aria-invalid={Boolean(subjectError)}
                aria-describedby={
                  subjectError ? "campaign-subject-err" : "campaign-subject-help"
                }
                className={`w-full px-3.5 py-2.5 rounded-lg text-xs sm:text-sm text-slate-900 placeholder:text-slate-400 border transition-all focus:outline-none focus:ring-2 ${
                  subjectError
                    ? "border-red-300 bg-red-50/20 text-red-900 focus:ring-red-500/20 focus:border-red-600"
                    : "border-slate-200 bg-white focus:ring-indigo-500/20 focus:border-indigo-600 shadow-2xs"
                }`}
              />
              {subjectError && (
                <div className="absolute right-3 top-2.5 text-red-500 pointer-events-none">
                  <AlertCircle className="h-5 w-5" />
                </div>
              )}
            </div>
            {subjectError ? (
              <p
                id="campaign-subject-err"
                role="alert"
                className="text-xs text-red-600 flex items-center gap-1 font-medium mt-1"
              >
                <AlertCircle className="h-3.5 w-3.5" />
                <span>{subjectError}</span>
              </p>
            ) : (
              <p
                id="campaign-subject-help"
                className="text-xs text-slate-500 mt-1"
              >
                This is the subject recipients will see.
              </p>
            )}
          </div>

          {/* C14 Configurable Sending Interval / Pacing Section */}
          <div className="pt-2 border-t border-slate-100 space-y-3">
            <div className="flex items-center gap-2">
              <Gauge className="h-4 w-4 text-indigo-600 shrink-0" />
              <label className="text-xs sm:text-sm font-semibold text-slate-900">
                Sending Interval
              </label>
            </div>
            <p className="text-xs text-slate-500 -mt-1 leading-relaxed">
              Controls the pacing delay between consecutive recipient send attempts. Useful for IP warm-up and adhering to email provider rate limits.
            </p>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
              {/* Option 1: Immediate / No delay */}
              <label
                className={`relative flex items-start gap-3 p-3.5 rounded-lg border cursor-pointer transition-all ${
                  !isCustomPacing
                    ? "border-indigo-600 bg-indigo-50/30 ring-1 ring-indigo-500/20"
                    : "border-slate-200 bg-white hover:bg-slate-50/60"
                }`}
              >
                <input
                  type="radio"
                  name="pacing-mode"
                  value="none"
                  checked={!isCustomPacing}
                  onChange={() => handlePacingModeChange("none")}
                  className="mt-0.5 text-indigo-600 focus:ring-indigo-500"
                />
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm font-semibold text-slate-900">
                    No intentional delay
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                    Send eligible recipients immediately one after another as fast as possible.
                  </p>
                </div>
              </label>

              {/* Option 2: Custom Pacing Interval */}
              <label
                className={`relative flex items-start gap-3 p-3.5 rounded-lg border cursor-pointer transition-all ${
                  isCustomPacing
                    ? "border-indigo-600 bg-indigo-50/30 ring-1 ring-indigo-500/20"
                    : "border-slate-200 bg-white hover:bg-slate-50/60"
                }`}
              >
                <input
                  type="radio"
                  name="pacing-mode"
                  value="custom"
                  checked={isCustomPacing}
                  onChange={() => handlePacingModeChange("custom")}
                  className="mt-0.5 text-indigo-600 focus:ring-indigo-500"
                />
                <div className="min-w-0">
                  <p className="text-xs sm:text-sm font-semibold text-slate-900">
                    Paced sending delay
                  </p>
                  <p className="text-[11px] text-slate-500 mt-0.5 leading-snug">
                    Wait a minimum delay between each recipient dispatch attempt.
                  </p>
                </div>
              </label>
            </div>

            {/* Custom Interval Inputs (rendered when custom pacing is active) */}
            {isCustomPacing && (
              <div className="mt-3 p-4 rounded-lg bg-slate-50 border border-slate-200/80 space-y-3">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="w-32">
                    <label htmlFor="send-interval-num" className="sr-only">
                      Interval numeric value
                    </label>
                    <input
                      id="send-interval-num"
                      type="number"
                      min={1}
                      max={intervalUnit === "minutes" ? 1440 : 86400}
                      value={intervalNum || ""}
                      onChange={handleIntervalNumChange}
                      aria-label="Pacing interval value"
                      className="w-full px-3 py-2 text-xs sm:text-sm bg-white rounded-lg border border-slate-200 text-slate-900 font-semibold focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-2xs"
                    />
                  </div>

                  <div className="w-36">
                    <label htmlFor="send-interval-unit" className="sr-only">
                      Interval unit
                    </label>
                    <select
                      id="send-interval-unit"
                      value={intervalUnit}
                      onChange={handleUnitChange}
                      aria-label="Pacing interval unit"
                      className="w-full px-3 py-2 text-xs sm:text-sm bg-white rounded-lg border border-slate-200 text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500 shadow-2xs"
                    >
                      <option value="minutes">Minutes</option>
                      <option value="seconds">Seconds</option>
                    </select>
                  </div>

                  <div className="text-xs text-slate-600 flex items-center gap-1.5">
                    <Clock className="h-3.5 w-3.5 text-indigo-600" />
                    <span>
                      {intervalUnit === "minutes"
                        ? `Equivalent to ${intervalNum * 60} seconds`
                        : `Equivalent to ${(intervalNum / 60).toFixed(1)} minutes`}
                    </span>
                  </div>
                </div>

                <p className="text-xs text-indigo-700 bg-indigo-50/80 px-3 py-1.5 rounded-md border border-indigo-100 flex items-center gap-1.5">
                  <Info className="h-3.5 w-3.5 shrink-0" />
                  <span>
                    The first recipient is sent immediately, followed by at least {intervalNum}{" "}
                    {intervalUnit} between each subsequent recipient.
                  </span>
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
};
