import React from "react";
import { Link } from "react-router-dom";
import { PlusCircle, Mail, AlertCircle, Loader2 } from "lucide-react";
import type { AuthorizedEmailAccount } from "../../types/emails";
import { SenderAccountCard } from "./SenderAccountCard";

interface SenderSelectionStepProps {
  accounts: AuthorizedEmailAccount[];
  selectedAccountId: number | null;
  onSelectAccount: (accountId: number) => void;
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  error?: string | null;
}

export const SenderSelectionStep: React.FC<SenderSelectionStepProps> = ({
  accounts,
  selectedAccountId,
  onSelectAccount,
  isLoading = false,
  isError = false,
  onRetry,
  error,
}) => {
  const selectedAccount = accounts.find((a) => a.id === selectedAccountId);

  // Extract domain from selected email
  const selectedDomain = selectedAccount?.email_address
    ? selectedAccount.email_address.split("@")[1]
    : null;

  return (
    <section className="space-y-6">
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs p-6 sm:p-8 space-y-6">
        {/* Step Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <h2 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
              Sender Account
            </h2>
            <p className="text-xs sm:text-sm text-slate-500">
              Select which authenticated mailbox will dispatch this sequence.
            </p>
          </div>
          <Link
            to="/email-accounts"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors shrink-0"
          >
            <PlusCircle className="h-4 w-4" />
            <span>Add Mailbox</span>
          </Link>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="py-12 flex flex-col items-center justify-center text-center space-y-3">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
            <p className="text-xs sm:text-sm text-slate-500 font-medium">
              Loading authorized sending accounts...
            </p>
          </div>
        )}

        {/* Error state */}
        {!isLoading && isError && (
          <div className="p-6 rounded-xl bg-red-50/50 border border-red-200 text-center space-y-3">
            <div className="w-10 h-10 mx-auto rounded-full bg-red-100 text-red-600 flex items-center justify-center">
              <AlertCircle className="h-5 w-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Failed to load email accounts
              </h3>
              <p className="text-xs text-slate-500 mt-1">
                {error || "An unexpected error occurred while fetching sending mailboxes."}
              </p>
            </div>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="px-4 py-2 rounded-lg bg-white border border-slate-200 text-slate-700 text-xs font-semibold hover:bg-slate-50 transition-colors shadow-2xs"
              >
                Retry
              </button>
            )}
          </div>
        )}

        {/* Empty state: No accounts returned */}
        {!isLoading && !isError && accounts.length === 0 && (
          <div className="p-8 sm:p-12 rounded-xl bg-slate-50 border border-dashed border-slate-200 text-center space-y-4">
            <div className="w-14 h-14 mx-auto rounded-full bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shadow-2xs">
              <Mail className="h-6 w-6" />
            </div>
            <div className="max-w-md mx-auto space-y-1">
              <h3 className="text-sm sm:text-base font-bold text-slate-900">
                No sending accounts available
              </h3>
              <p className="text-xs sm:text-sm text-slate-500 leading-relaxed">
                Connect and configure an email account before creating a campaign.
              </p>
            </div>
            <Link
              to="/email-accounts"
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-colors"
            >
              <PlusCircle className="h-4 w-4" />
              <span>Connect Email Account</span>
            </Link>
          </div>
        )}

        {/* Sender Cards List */}
        {!isLoading && !isError && accounts.length > 0 && (
          <div
            role="radiogroup"
            aria-label="Select sender account"
            className="space-y-2.5"
          >
            {accounts.map((account) => (
              <SenderAccountCard
                key={account.id}
                account={account}
                isSelected={account.id === selectedAccountId}
                onSelect={(acc) => onSelectAccount(acc.id)}
              />
            ))}
          </div>
        )}

        {/* Sender Information Summary Panel */}
        {selectedAccount && (
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
            <div className="space-y-0.5">
              <span className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold block">
                Selected Identity
              </span>
              <p className="text-xs sm:text-sm font-semibold text-slate-900">
                Sending from {selectedAccount.name} ({selectedAccount.email_address})
              </p>
              {selectedDomain && (
                <div className="flex items-center gap-1.5 pt-0.5">
                  <span className="text-xs text-slate-500">
                    Domain: <strong className="text-slate-700">{selectedDomain}</strong>
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
};
