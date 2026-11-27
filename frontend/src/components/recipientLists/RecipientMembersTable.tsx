import React from "react";
import { Edit2, Trash2, Mail, Calendar } from "lucide-react";
import type { RecipientListMember } from "../../types/recipientList";

interface RecipientMembersTableProps {
  members: RecipientListMember[];
  onEdit: (member: RecipientListMember) => void;
  onDelete: (member: RecipientListMember) => void;
  disabled?: boolean;
}

export const RecipientMembersTable: React.FC<RecipientMembersTableProps> = ({
  members,
  onEdit,
  onDelete,
  disabled = false,
}) => {
  const formatDate = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return "—";
    }
  };

  return (
    <div className="w-full bg-white rounded-2xl border border-slate-200 shadow-xs overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50/75 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              <th scope="col" className="py-3.5 pl-6 pr-4">
                Email Address
              </th>
              <th scope="col" className="py-3.5 px-4">
                First Name
              </th>
              <th scope="col" className="py-3.5 px-4">
                Last Name
              </th>
              <th scope="col" className="py-3.5 px-4">
                Added Date
              </th>
              <th scope="col" className="py-3.5 pl-4 pr-6 text-right">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-xs">
            {members.map((member) => (
              <tr
                key={member.id}
                className="hover:bg-slate-50/80 transition-colors group"
              >
                {/* Email */}
                <td className="py-3.5 pl-6 pr-4">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                      <Mail className="h-3.5 w-3.5" />
                    </div>
                    <span className="font-semibold text-slate-900 font-mono text-xs truncate max-w-xs sm:max-w-md">
                      {member.email}
                    </span>
                  </div>
                </td>

                {/* First Name */}
                <td className="py-3.5 px-4 text-slate-700">
                  {member.first_name ? (
                    <span className="font-medium text-slate-800">{member.first_name}</span>
                  ) : (
                    <span className="text-slate-400 italic font-normal">—</span>
                  )}
                </td>

                {/* Last Name */}
                <td className="py-3.5 px-4 text-slate-700">
                  {member.last_name ? (
                    <span className="font-medium text-slate-800">{member.last_name}</span>
                  ) : (
                    <span className="text-slate-400 italic font-normal">—</span>
                  )}
                </td>

                {/* Added Date */}
                <td className="py-3.5 px-4 text-slate-500">
                  <div className="flex items-center gap-1.5 text-[11px]">
                    <Calendar className="h-3 w-3 text-slate-400" />
                    <span>{formatDate(member.created_at)}</span>
                  </div>
                </td>

                {/* Actions */}
                <td className="py-3.5 pl-4 pr-6 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => onEdit(member)}
                      className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors disabled:opacity-50"
                      title="Edit contact"
                    >
                      <Edit2 className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      disabled={disabled}
                      onClick={() => onDelete(member)}
                      className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition-colors disabled:opacity-50"
                      title="Remove contact"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
