import React from "react";
import { Mail, Headphones, Receipt, Server } from "lucide-react";
import type { EmailAccountItem } from "../../types/emails";
import type { CompanyMember } from "../../types/auth";
import { getInitials } from "./MemberRow";

interface SharedInboxCardProps {
  account: EmailAccountItem;
  assignedMembers: CompanyMember[];
  isCurrentUserAdminOrOwner: boolean;
  onOpenManageAccess: (account: EmailAccountItem) => void;
}

export const SharedInboxCard: React.FC<SharedInboxCardProps> = ({
  account,
  assignedMembers,
  isCurrentUserAdminOrOwner,
  onOpenManageAccess,
}) => {
  const getAccountIcon = (name: string) => {
    const lower = name.toLowerCase();
    if (lower.includes("support") || lower.includes("help") || lower.includes("desk")) {
      return Headphones;
    }
    if (lower.includes("bill") || lower.includes("invoice") || lower.includes("finance")) {
      return Receipt;
    }
    if (lower.includes("dev") || lower.includes("telemetry") || lower.includes("system")) {
      return Server;
    }
    return Mail;
  };

  const Icon = getAccountIcon(account.name);
  const memberCount = assignedMembers.length;

  return (
    <div className="border border-slate-200 rounded-xl p-5 bg-white hover:border-slate-300 transition-all flex flex-col justify-between gap-4 shadow-2xs">
      <div className="space-y-3">
        {/* Top: Icon, Name, Address, Status */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0">
              <Icon className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <h3 className="font-semibold text-slate-900 text-sm leading-snug truncate">
                {account.name}
              </h3>
              <span className="text-xs text-slate-500 block truncate">{account.email_address}</span>
            </div>
          </div>

          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border shrink-0 ${
              account.is_active
                ? "bg-emerald-50 text-emerald-700 border-emerald-200/80"
                : "bg-slate-100 text-slate-600 border-slate-200"
            }`}
          >
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                account.is_active ? "bg-emerald-500" : "bg-slate-400"
              }`}
            />
            {account.is_active ? "Connected" : "Inactive"}
          </span>
        </div>

        {/* Assigned Members Box */}
        <div className="bg-slate-50 rounded-lg p-3 border border-slate-100 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-slate-700">
                {memberCount} {memberCount === 1 ? "member" : "members"}
              </span>
              <span className="text-[11px] text-slate-400">(assigned Members)</span>
            </div>
            <span className="text-[11px] text-slate-400 font-medium">Owner &amp; Admin auto-access</span>
          </div>

          {memberCount > 0 ? (
            <div className="flex items-center gap-1.5 flex-wrap">
              {assignedMembers.map((m) => (
                <span
                  key={m.user_id}
                  className="inline-flex items-center gap-1.5 bg-white border border-slate-200 px-2 py-1 rounded-md text-xs text-slate-700 font-medium shadow-2xs truncate max-w-[180px]"
                  title={m.full_name || m.email}
                >
                  <span className="w-4 h-4 rounded-full bg-slate-200 text-slate-700 text-[10px] flex items-center justify-center font-bold shrink-0">
                    {getInitials(m.full_name, m.email).substring(0, 1)}
                  </span>
                  <span className="truncate">{m.full_name || m.email}</span>
                </span>
              ))}
            </div>
          ) : (
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-slate-400 italic">No individual members assigned</span>
            </div>
          )}
        </div>
      </div>

      {/* Footer: Manage Access Action */}
      <div className="flex items-center justify-end pt-2 border-t border-slate-100">
        {isCurrentUserAdminOrOwner ? (
          <button
            type="button"
            onClick={() => onOpenManageAccess(account)}
            className="text-xs font-medium text-indigo-600 hover:text-indigo-700 hover:bg-indigo-50 px-3 py-1.5 rounded-lg border border-indigo-200 transition-colors cursor-pointer"
          >
            Manage Access
          </button>
        ) : (
          <span className="text-xs text-slate-400">View Only</span>
        )}
      </div>
    </div>
  );
};
