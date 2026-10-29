import React, { useState, useEffect } from "react";
import { Calendar, Loader2 } from "lucide-react";
import type { CampaignRecipient } from "../../../types/campaign";

interface RecipientRescheduleModalProps {
  isOpen: boolean;
  recipient: CampaignRecipient | null;
  onClose: () => void;
  onConfirm: (newScheduledIso: string) => void;
  isLoading?: boolean;
}

export const RecipientRescheduleModal: React.FC<RecipientRescheduleModalProps> = ({
  isOpen,
  recipient,
  onClose,
  onConfirm,
  isLoading = false,
}) => {
  const [dateTimeValue, setDateTimeValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen || !recipient) {
      setDateTimeValue("");
      setError(null);
      return;
    }

    try {
      const defaultDate = recipient.next_step_due_at
        ? new Date(recipient.next_step_due_at)
        : new Date(Date.now() + 24 * 60 * 60 * 1000);

      const year = defaultDate.getFullYear();
      const month = String(defaultDate.getMonth() + 1).padStart(2, "0");
      const day = String(defaultDate.getDate()).padStart(2, "0");
      const hours = String(defaultDate.getHours()).padStart(2, "0");
      const minutes = String(defaultDate.getMinutes()).padStart(2, "0");
      setDateTimeValue(`${year}-${month}-${day}T${hours}:${minutes}`);
    } catch {
      setDateTimeValue("");
    }
    setError(null);
  }, [isOpen, recipient]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        onClose();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isLoading, onClose]);

  if (!isOpen || !recipient) return null;

  const nextStepNum = (recipient.current_step_number || 1) + 1;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!dateTimeValue) {
      setError("Please select a date and time.");
      return;
    }

    const chosenDate = new Date(dateTimeValue);
    if (isNaN(chosenDate.getTime())) {
      setError("Invalid date/time format.");
      return;
    }

    if (chosenDate.getTime() <= Date.now()) {
      setError("Rescheduled time must be in the future.");
      return;
    }

    setError(null);
    onConfirm(chosenDate.toISOString());
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="reschedule-recipient-modal-title"
      className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 animate-in fade-in duration-150"
    >
      <div
        className="bg-white rounded-2xl shadow-2xl border border-slate-200 p-6 text-left animate-in zoom-in-95 duration-150 max-h-[90vh] overflow-y-auto"
        style={{ width: "min(calc(100vw - 32px), 440px)" }}
      >
        {/* Header */}
        <div className="flex items-center gap-3 mb-3">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center shrink-0">
            <Calendar className="h-5 w-5" />
          </div>
          <div className="flex flex-col min-w-0">
            <h3 id="reschedule-recipient-modal-title" className="text-sm font-bold text-slate-900 truncate">
              Reschedule Step {nextStepNum}
            </h3>
            <span className="text-xs text-slate-500 font-mono truncate">
              {recipient.email}
            </span>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <p className="text-xs text-slate-600 leading-relaxed">
            Choose a new date and time to dispatch Step {nextStepNum} to <span className="font-semibold text-slate-900 font-mono break-all">{recipient.email}</span>.
          </p>

          <div>
            <label htmlFor="reschedule-datetime-input" className="block text-xs font-semibold text-slate-700 mb-1.5">
              New Send Date & Time (Local Time)
            </label>
            <input
              id="reschedule-datetime-input"
              type="datetime-local"
              value={dateTimeValue}
              onChange={(e) => {
                setDateTimeValue(e.target.value);
                if (error) setError(null);
              }}
              disabled={isLoading}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs font-sans text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 disabled:opacity-50"
              required
            />
            {error && (
              <p className="text-xs text-rose-600 mt-1 font-medium">{error}</p>
            )}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-2.5 pt-2">
            <button
              type="button"
              disabled={isLoading}
              onClick={onClose}
              className="px-3.5 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-medium transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium shadow-sm transition-colors flex items-center gap-1.5 disabled:opacity-50"
            >
              {isLoading ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  <span>Saving...</span>
                </>
              ) : (
                <span>Confirm Reschedule</span>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

