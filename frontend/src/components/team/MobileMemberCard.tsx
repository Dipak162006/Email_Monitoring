import React from "react";
import { Shield, ShieldCheck, Lock, Star } from "lucide-react";
import type { CompanyMember } from "../../types/auth";
import type { EmailAccountItem } from "../../types/emails";
import { formatMemberDate, getInitials } from "./MemberRow";

interface MobileMemberCardProps {
  member: CompanyMember;
  assignedAccounts: EmailAccountItem[];
  isCurrentUserAdminOrOwner: boolean;
  isSelf?: boolean;
  onOpenManageAccess: (member: CompanyMember) => void;
  onOpenChangeRole: (member: CompanyMember) => void;
  onOpenRemove: (member: CompanyMember) => void;
}

export const MobileMemberCard: React.FC<MobileMemberCardProps> = ({
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
    <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-3 shadow-2xs">
      {/* Top row: Avatar, Name, Email, Role */}
      <div className="flex items-start justify-between gap-2.5">
        <div className="flex items-center gap-2.5 min-w-0">
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
          <div className="min-w-0">
            <h4 className="text-sm font-semibold text-slate-900 flex items-center gap-1.5 truncate">
              {member.full_name || member.email}
              {isOwner && <Star className="h-3.5 w-3.5 text-amber-500 fill-amber-500 shrink-0" />}
            </h4>
            <p className="text-xs text-slate-500 truncate">{member.email}</p>
          </div>
        </div>

        <div className="shrink-0">
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
        </div>
      </div>

      {/* Middle row: Access info & Joined date */}
      <div className="bg-slate-50 rounded-lg p-2.5 border border-slate-100 space-y-1.5 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-slate-500 font-medium">Email Access:</span>
          {isOwner || isAdmin ? (
            <span className="inline-flex items-center bg-indigo-50 text-indigo-700 border border-indigo-100 px-2 py-0.5 rounded text-[11px] font-medium">
              Full Access
            </span>
          ) : assignedAccounts.length > 0 ? (
            <span className="text-slate-700 font-semibold">{assignedAccounts.length} assigned</span>
          ) : (
            <span className="text-slate-400 italic">No access</span>
          )}
        </div>

        {isMember && assignedAccounts.length > 0 && (
          <div className="flex items-center gap-1 flex-wrap pt-0.5">
            {assignedAccounts.map((acc) => (
              <span
                key={acc.id}
                className="bg-white text-slate-700 border border-slate-200 text-[11px] px-1.5 py-0.5 rounded font-medium truncate max-w-[140px]"
              >
                {acc.name}
              </span>
            ))}
          </div>
        )}

        <div className="flex items-center justify-between pt-1 border-t border-slate-200/60 text-[11px] text-slate-400">
          <span>Joined</span>
          <span>{formatMemberDate(member.created_at)}</span>
        </div>
      </div>

      {/* Actions */}
      {(isOwner || (!isSelf && isCurrentUserAdminOrOwner)) && (
        <div className="flex items-center justify-end gap-2 pt-1 border-t border-slate-100">
          {isOwner ? (
            <span className="inline-flex items-center gap-1 bg-slate-100 text-slate-500 px-2.5 py-1 rounded-md text-xs font-medium cursor-not-allowed select-none border border-slate-200">
              <Lock className="h-3.5 w-3.5" />
              Primary Owner
            </span>
          ) : (
            <>
              {isMember && (
                <button
                  type="button"
                  onClick={() => onOpenManageAccess(member)}
                  className="text-xs font-medium text-slate-700 hover:text-indigo-600 bg-slate-100 hover:bg-slate-200 px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
                >
                  Manage Access
                </button>
              )}
              <button
                type="button"
                onClick={() => onOpenChangeRole(member)}
                className="text-xs font-medium text-slate-700 hover:text-indigo-600 bg-slate-100 hover:bg-slate-200 px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
              >
                Role
              </button>
              <button
                type="button"
                onClick={() => onOpenRemove(member)}
                className="text-xs font-medium text-rose-600 hover:text-rose-700 bg-rose-50 hover:bg-rose-100 px-2.5 py-1 rounded-lg transition-colors cursor-pointer"
              >
                Remove
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
};
