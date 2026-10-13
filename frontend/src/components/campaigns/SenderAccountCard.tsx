import React from "react";
import { Check, AlertCircle } from "lucide-react";
import type { AuthorizedEmailAccount } from "../../types/emails";

interface SenderAccountCardProps {
  account: AuthorizedEmailAccount;
  isSelected: boolean;
  onSelect: (account: AuthorizedEmailAccount) => void;
}

export const SenderAccountCard: React.FC<SenderAccountCardProps> = ({
  account,
  isSelected,
  onSelect,
}) => {
  const isInactive = !account.is_active;

  // Extract initials from name or email
  const initials = (account.name || account.email_address)
    .split(" ")
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join("")
    .toUpperCase();

  // Provider display name helper
  const formatProvider = (p: string) => {
    switch (p?.toUpperCase()) {
      case "GMAIL":
      case "GOOGLE":
        return "Google Workspace";
      case "OUTLOOK":
      case "OFFICE365":
      case "MICROSOFT":
        return "Microsoft 365";
      case "SMTP_IMAP":
      case "SMTP":
        return "Custom SMTP";
      case "ZOHO":
        return "Zoho Mail";
      default:
        return p || "Email Account";
    }
  };

  const handleClick = () => {
    if (!isInactive) {
      onSelect(account);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if ((e.key === "Enter" || e.key === " ") && !isInactive) {
      e.preventDefault();
      onSelect(account);
    }
  };

  return (
    <div
      role="radio"
      aria-checked={isSelected}
      aria-disabled={isInactive}
      tabIndex={isInactive ? -1 : 0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={`p-4 rounded-xl border transition-all relative flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 ${
        isInactive
          ? "bg-slate-50/70 border-slate-200 opacity-60 cursor-not-allowed"
          : isSelected
          ? "bg-indigo-50/30 border-2 border-indigo-600 shadow-xs cursor-pointer"
          : "bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/50 shadow-2xs cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
      }`}
    >
      <div className="flex items-center gap-3.5 min-w-0">
        {/* Account Avatar Initials */}
        <div
          className={`w-10 h-10 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors ${
            isInactive
              ? "bg-slate-200 text-slate-500"
              : isSelected
              ? "bg-indigo-600 text-white"
              : "bg-indigo-100 text-indigo-700"
          }`}
        >
          {initials || "MB"}
        </div>

        {/* Identity Details */}
        <div className="min-w-0 space-y-0.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs sm:text-sm font-semibold text-slate-900 truncate">
              {account.name}
            </span>
            <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px] font-medium border border-slate-200">
              {formatProvider(account.provider)}
            </span>
            {account.is_active ? (
              <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-semibold border border-emerald-200">
                Active
              </span>
            ) : (
              <span className="px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 text-[10px] font-semibold border border-rose-200">
                Inactive
              </span>
            )}
          </div>
          <p className="text-xs text-slate-500 truncate">{account.email_address}</p>
          {isInactive && (
            <p className="text-[11px] text-rose-600 flex items-center gap-1 font-medium pt-0.5">
              <AlertCircle className="h-3 w-3 shrink-0" />
              <span>Mailbox is inactive. Re-activate in Connected Accounts to send.</span>
            </p>
          )}
        </div>
      </div>

      {/* Radio Check Indicator */}
      <div className="shrink-0 self-end sm:self-center">
        {isInactive ? (
          <span className="text-[11px] px-2 py-1 rounded bg-slate-100 text-slate-400 font-medium">
            Unavailable
          </span>
        ) : (
          <div
            className={`w-6 h-6 rounded-full flex items-center justify-center transition-all ${
              isSelected
                ? "bg-indigo-600 text-white shadow-2xs"
                : "border border-slate-300 bg-white text-transparent hover:border-slate-400"
            }`}
          >
            <Check className="h-3.5 w-3.5 stroke-[3]" />
          </div>
        )}
      </div>
    </div>
  );
};
