import React, { useState } from "react";
import { Mail, Plus, Loader2 } from "lucide-react";
import type { CampaignRecipientCreatePayload } from "../../../types/campaign";

interface RecipientManualFormProps {
  onSubmit: (payload: CampaignRecipientCreatePayload) => Promise<void> | void;
  isLoading?: boolean;
  disabled?: boolean;
}

export const RecipientManualForm: React.FC<RecipientManualFormProps> = ({
  onSubmit,
  isLoading = false,
  disabled = false,
}) => {
  const [email, setEmail] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (disabled || isLoading) return;

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setValidationError("Email address is required.");
      return;
    }

    // Basic RFC 5322 regex check
    const emailRegex = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
    if (!emailRegex.test(trimmedEmail)) {
      setValidationError("Please enter a valid email address.");
      return;
    }

    setValidationError(null);

    await onSubmit({
      email: trimmedEmail,
      first_name: firstName.trim() || null,
      last_name: lastName.trim() || null,
    });

    setEmail("");
    setFirstName("");
    setLastName("");
  };

  return (
    <form noValidate onSubmit={handleSubmit} className="w-full">
      <div className="grid grid-cols-1 md:grid-cols-12 gap-4 items-end">
        {/* Email Address */}
        <div className="md:col-span-5 min-w-0">
          <label
            htmlFor="manual-recipient-email"
            className="block text-xs font-semibold text-slate-700 mb-1.5"
          >
            Email Address <span className="text-rose-500">*</span>
          </label>
          <div className="relative">
            <Mail className="absolute left-3 top-2.5 h-4 w-4 text-slate-400 pointer-events-none" />
            <input
              id="manual-recipient-email"
              type="email"
              value={email}
              onChange={(e) => {
                setEmail(e.target.value);
                if (validationError) setValidationError(null);
              }}
              disabled={disabled || isLoading}
              placeholder="e.g. sarah.jenkins@acme.corp"
              required
              className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            />
          </div>
          {validationError ? (
            <p className="text-xs text-rose-500 mt-1 font-medium">{validationError}</p>
          ) : (
            <p className="text-xs text-slate-500 mt-1 truncate">Valid email format required</p>
          )}
        </div>

        {/* First Name */}
        <div className="md:col-span-3 min-w-0">
          <label
            htmlFor="manual-recipient-fname"
            className="block text-xs font-semibold text-slate-700 mb-1.5"
          >
            First Name
          </label>
          <input
            id="manual-recipient-fname"
            type="text"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            disabled={disabled || isLoading}
            placeholder="e.g. Sarah"
            className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <p className="text-xs text-slate-500 mt-1 truncate">Maps to {"{{first_name}}"} tag</p>
        </div>

        {/* Last Name */}
        <div className="md:col-span-2 min-w-0">
          <label
            htmlFor="manual-recipient-lname"
            className="block text-xs font-semibold text-slate-700 mb-1.5"
          >
            Last Name
          </label>
          <input
            id="manual-recipient-lname"
            type="text"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            disabled={disabled || isLoading}
            placeholder="e.g. Jenkins"
            className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          />
          <p className="text-xs text-slate-500 mt-1 truncate">Optional surname</p>
        </div>

        {/* Submit Button */}
        <div className="md:col-span-2 min-w-0">
          <button
            type="submit"
            disabled={disabled || isLoading}
            className="w-full h-10 px-4 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 active:bg-indigo-800 transition-colors flex items-center justify-center gap-1.5 shadow-2xs disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="truncate">Adding...</span>
              </>
            ) : (
              <>
                <Plus className="h-4 w-4" />
                <span className="truncate">Add Recipient</span>
              </>
            )}
          </button>
        </div>
      </div>
    </form>
  );
};
