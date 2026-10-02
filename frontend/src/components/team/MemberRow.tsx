import React from "react";
import { Shield, ShieldCheck, Lock, Star } from "lucide-react";
import type { CompanyMember } from "../../types/auth";
import type { EmailAccountItem } from "../../types/emails";

interface MemberRowProps {
  member: CompanyMember;
  assignedAccounts: EmailAccountItem[];
  isCurrentUserAdminOrOwner: boolean;
  isSelf?: boolean;
  onOpenManageAccess: (member: CompanyMember) => void;
  onOpenChangeRole: (member: CompanyMember) => void;
  onOpenRemove: (member: CompanyMember) => void;
}

export function formatMemberDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "2-digit",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export function getInitials(name: string | null, email: string): string {
  if (name) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return parts[0].substring(0, 2).toUpperCase();
  }
  return email.substring(0, 2).toUpperCase();
}

export const MemberRow: React.FC<MemberRowProps> = ({
  member,
  assignedAccounts,
  isCurrentUserAdminOrOwner,
  isSelf = false,
  onOpenManageAccess,
  onOpenChangeRole,
  onOpenRemove,
}) => {
  const isOwner = member.role === "OWNER";
  const isAdmin = member.role === "ADMIN";
  const isMember = member.role === "MEMBER";

  return (
    <tr className="hover:bg-slate-50/60 transition-colors">
      {/* User column */}
      <td className="py-3.5 px-6">
        <div className="flex items-center gap-3">
          <div
            className={`w-9 h-9 rounded-full font-semibold text-xs flex items-center justify-center shrink-0 shadow-xs ${
              isOwner
                ? "bg-gradient-to-tr from-indigo-600 to-indigo-800 text-white"
                : isAdmin
                ? "bg-indigo-50 border border-indigo-200 text-indigo-700"
                : "bg-slate-100 border border-slate-200 text-slate-700"
            }`}
          >
            {getInitials(member.full_name, member.email)}
          </div>
          <div className="flex flex-col min-w-0">
            <span className="font-semibold text-slate-900 flex items-center gap-1.5 truncate text-sm">
              {member.full_name || member.email}
              {isOwner && <Star className="h-3.5 w-3.5 text-amber-500 fill-amber-500 shrink-0" />}
            </span>
            <span className="text-xs text-slate-500 truncate">{member.email}</span>
          </div>
        </div>
      </td>

      {/* Role column */}
      <td className="py-3.5 px-4 whitespace-nowrap">
        {isOwner && (
          <span className="inline-flex items-center gap-1 bg-amber-50 text-amber-800 border border-amber-200/80 px-2 py-0.5 rounded-md text-xs font-medium">
            <Shield className="h-3 w-3" />
            Owner
          </span>
        )}
        {isAdmin && (
          <span className="inline-flex items-center gap-1 bg-indigo-50 text-indigo-700 border border-indigo-200 px-2 py-0.5 rounded-md text-xs font-medium">
            <ShieldCheck className="h-3 w-3" />
            Admin
          </span>
        )}
        {isMember && (
          <span className="inline-flex items-center bg-slate-100 text-slate-700 border border-slate-200 px-2 py-0.5 rounded-md text-xs font-medium">
            Member
          </span>
        )}
      </td>

      {/* Email Account Access column */}
      <td className="py-3.5 px-4">
        {isOwner || isAdmin ? (
          <span className="inline-flex items-center gap-1 bg-indigo-50 text-indigo-700 border border-indigo-100 px-2 py-0.5 rounded-md text-xs font-medium whitespace-nowrap">
            Full Access
          </span>
        ) : assignedAccounts.length > 0 ? (
          <div className="flex items-center gap-1.5 flex-wrap">
            {assignedAccounts.map((acc) => (
              <span
                key={acc.id}
                className="bg-slate-100 text-slate-700 border border-slate-200 text-xs px-2 py-0.5 rounded font-medium truncate max-w-[180px]"
                title={acc.name}
              >
                {acc.name}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-xs text-slate-400 italic">No account access</span>
        )}
      </td>

      {/* Joined date column */}
      <td className="py-3.5 px-4 text-xs text-slate-500 whitespace-nowrap">
        {formatMemberDate(member.created_at)}
      </td>

      {/* Actions column */}
      <td className="py-3.5 px-6 text-right whitespace-nowrap">
        {isOwner ? (
          <span className="inline-flex items-center gap-1 bg-slate-100 text-slate-500 px-2.5 py-1 rounded-md text-xs font-medium cursor-not-allowed select-none border border-slate-200">
            <Lock className="h-3.5 w-3.5" />
            Primary Owner
          </span>
        ) : isSelf ? null : isCurrentUserAdminOrOwner ? (
          <div className="inline-flex items-center justify-end gap-1.5">
            {isMember && (
              <button
                type="button"
                onClick={() => onOpenManageAccess(member)}
                className="text-xs font-medium text-slate-600 hover:text-indigo-600 hover:bg-slate-100 px-2 py-1 rounded-md transition-colors cursor-pointer"
                title="Manage Access"
              >
                Manage Access
              </button>
            )}
            <button
              type="button"
              onClick={() => onOpenChangeRole(member)}
              className="text-xs font-medium text-slate-600 hover:text-indigo-600 hover:bg-slate-100 px-2 py-1 rounded-md transition-colors cursor-pointer"
              title="Change Role"
            >
              Change Role
            </button>
            <button
              type="button"
              onClick={() => onOpenRemove(member)}
              className="text-xs font-medium text-rose-600 hover:text-rose-700 hover:bg-rose-50 px-2 py-1 rounded-md transition-colors cursor-pointer"
              title="Remove Member"
            >
              Remove
            </button>
          </div>
        ) : (
          <span className="text-xs text-slate-400">—</span>
        )}
      </td>
    </tr>
  );
};
