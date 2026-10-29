import React, { useMemo } from "react";
import { Clock, Globe, Calendar, AlertCircle, Info, CheckCircle2 } from "lucide-react";
import type { SendingWindowConfig } from "../../types/campaign";

export interface SendingWindowCardProps {
  value?: SendingWindowConfig | null;
  onChange: (config: SendingWindowConfig | null) => void;
  disabled?: boolean;
}

const COMMON_TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Asia/Dubai",
  "Asia/Kolkata",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

const WEEKDAYS = [
  { id: 1, label: "Mon", short: "M" },
  { id: 2, label: "Tue", short: "T" },
  { id: 3, label: "Wed", short: "W" },
  { id: 4, label: "Thu", short: "T" },
  { id: 5, label: "Fri", short: "F" },
  { id: 6, label: "Sat", short: "S" },
  { id: 7, label: "Sun", short: "S" },
];

export const SendingWindowCard: React.FC<SendingWindowCardProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  const isEnabled = Boolean(value?.enabled);

  // Fallback defaults
  const currentTz = useMemo(() => {
    if (value?.timezone) return value.timezone;
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
    } catch {
      return "UTC";
    }
  }, [value?.timezone]);

  const currentDays = value?.days ?? [1, 2, 3, 4, 5];
  const startTime = value?.start_time ?? "09:00";
  const endTime = value?.end_time ?? "17:00";

  // Validate start < end and at least 1 day selected
  const isTimeOrderInvalid = isEnabled && startTime >= endTime;
  const isDaysEmpty = isEnabled && currentDays.length === 0;

  const handleToggleEnabled = (checked: boolean) => {
    if (!checked) {
      onChange(null);
    } else {
      onChange({
        enabled: true,
        timezone: currentTz,
        days: currentDays.length > 0 ? currentDays : [1, 2, 3, 4, 5],
        start_time: startTime,
        end_time: endTime,
      });
    }
  };

  const handleTimezoneChange = (tz: string) => {
    onChange({
      enabled: true,
      timezone: tz,
      days: currentDays,
      start_time: startTime,
      end_time: endTime,
    });
  };

  const handleDayToggle = (dayId: number) => {
    let nextDays: number[];
    if (currentDays.includes(dayId)) {
      nextDays = currentDays.filter((d) => d !== dayId);
    } else {
      nextDays = [...currentDays, dayId].sort((a, b) => a - b);
    }
    onChange({
      enabled: true,
      timezone: currentTz,
      days: nextDays,
      start_time: startTime,
      end_time: endTime,
    });
  };

  const handleStartTimeChange = (newStart: string) => {
    onChange({
      enabled: true,
      timezone: currentTz,
      days: currentDays,
      start_time: newStart,
      end_time: endTime,
    });
  };

  const handleEndTimeChange = (newEnd: string) => {
    onChange({
      enabled: true,
      timezone: currentTz,
      days: currentDays,
      start_time: startTime,
      end_time: newEnd,
    });
  };

  const daySummary = useMemo(() => {
    if (currentDays.length === 5 && [1, 2, 3, 4, 5].every((d) => currentDays.includes(d))) {
      return "Mon – Fri";
    }
    if (currentDays.length === 7) {
      return "Every day (Mon – Sun)";
    }
    if (currentDays.length === 0) {
      return "No days selected";
    }
    return WEEKDAYS.filter((w) => currentDays.includes(w.id))
      .map((w) => w.label)
      .join(", ");
  }, [currentDays]);

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-4 sm:p-5 shadow-2xs space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Clock className="h-4 w-4 text-indigo-600" />
            <h4 className="text-sm font-semibold text-slate-900">
              Sending Window & Timezone Governance
            </h4>
          </div>
          <p className="text-xs text-slate-500">
            Restrict initial emails and follow-ups to specific days and local business hours.
          </p>
        </div>

        <label className="relative inline-flex items-center cursor-pointer select-none">
          <input
            type="checkbox"
            checked={isEnabled}
            disabled={disabled}
            onChange={(e) => handleToggleEnabled(e.target.checked)}
            aria-label="Enable sending window"
            className="sr-only peer"
          />
          <div className="w-10 h-5.5 bg-slate-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-indigo-500 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4.5 after:w-4.5 after:transition-all peer-checked:bg-indigo-600"></div>
          <span className="ml-2 text-xs font-medium text-slate-700">
            {isEnabled ? "Enabled" : "Disabled"}
          </span>
        </label>
      </div>

      {!isEnabled ? (
        <div className="rounded-lg bg-slate-50 border border-slate-200/60 p-3 text-xs text-slate-600 flex items-center gap-2">
          <Info className="h-4 w-4 text-slate-400 shrink-0" />
          <span>
            Window is disabled. Campaigns and follow-ups will be sent 24/7 without time-of-day restrictions.
          </span>
        </div>
      ) : (
        <div className="space-y-4 pt-2 border-t border-slate-100">
          {/* 1. Timezone selector */}
          <div className="space-y-1.5">
            <label
              htmlFor="sending-window-tz"
              className="block text-xs font-semibold text-slate-700 flex items-center gap-1.5"
            >
              <Globe className="h-3.5 w-3.5 text-slate-400" />
              <span>Target Timezone (IANA)</span>
            </label>
            <select
              id="sending-window-tz"
              value={currentTz}
              disabled={disabled}
              onChange={(e) => handleTimezoneChange(e.target.value)}
              className="w-full sm:w-80 px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-800 font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500"
            >
              {!COMMON_TIMEZONES.includes(currentTz) && (
                <option value={currentTz}>{currentTz} (Detected)</option>
              )}
              {COMMON_TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>

          {/* 2. Permitted Days */}
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-700 flex items-center gap-1.5">
              <Calendar className="h-3.5 w-3.5 text-slate-400" />
              <span>Permitted Sending Days</span>
            </label>
            <div className="flex flex-wrap gap-1.5 sm:gap-2">
              {WEEKDAYS.map((w) => {
                const isSelected = currentDays.includes(w.id);
                return (
                  <button
                    key={w.id}
                    type="button"
                    disabled={disabled}
                    onClick={() => handleDayToggle(w.id)}
                    aria-pressed={isSelected}
                    className={`px-3 py-1.5 text-xs font-medium rounded-lg border transition-all ${
                      isSelected
                        ? "bg-indigo-50 border-indigo-300 text-indigo-700 font-semibold shadow-2xs"
                        : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
                    }`}
                  >
                    {w.label}
                  </button>
                );
              })}
            </div>
            {isDaysEmpty && (
              <p className="text-xs text-rose-600 flex items-center gap-1 mt-1">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                <span>At least one day must be selected.</span>
              </p>
            )}
          </div>

          {/* 3. Daily Start & End Times */}
          <div className="space-y-1.5">
            <span className="block text-xs font-semibold text-slate-700">
              Daily Active Window (Local Time)
            </span>
            <div className="flex flex-wrap items-center gap-3">
              <div className="space-y-1">
                <label htmlFor="sending-window-start" className="block text-[11px] text-slate-500">
                  Opening Time
                </label>
                <input
                  id="sending-window-start"
                  type="time"
                  value={startTime}
                  disabled={disabled}
                  onChange={(e) => handleStartTimeChange(e.target.value)}
                  className="px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-800 font-semibold focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              <span className="text-slate-400 text-xs mt-4">to</span>

              <div className="space-y-1">
                <label htmlFor="sending-window-end" className="block text-[11px] text-slate-500">
                  Closing Time
                </label>
                <input
                  id="sending-window-end"
                  type="time"
                  value={endTime}
                  disabled={disabled}
                  onChange={(e) => handleEndTimeChange(e.target.value)}
                  className="px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg text-slate-800 font-semibold focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>
            </div>
            {isTimeOrderInvalid && (
              <p className="text-xs text-rose-600 flex items-center gap-1 mt-1">
                <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                <span>Opening time must be strictly earlier than closing time.</span>
              </p>
            )}
          </div>

          {/* 4. Active Schedule Summary */}
          {!isTimeOrderInvalid && !isDaysEmpty && (
            <div className="rounded-lg bg-indigo-50/70 border border-indigo-100 p-3 text-xs text-indigo-900 flex items-start gap-2">
              <CheckCircle2 className="h-4 w-4 text-indigo-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Schedule Active</p>
                <p className="text-indigo-700 text-[11px] mt-0.5">
                  Sends allowed between <strong className="font-semibold">{startTime}</strong> and{" "}
                  <strong className="font-semibold">{endTime}</strong> ({currentTz}) on{" "}
                  <strong className="font-semibold">{daySummary}</strong>.
                </p>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

