import React from "react";
import { Users, FileEdit, Trash2, Calendar, User } from "lucide-react";
import type { RecipientList } from "../../types/recipientList";

interface RecipientListsTableProps {
  lists: RecipientList[];
  onManage: (list: RecipientList) => void;
  onEdit: (list: RecipientList) => void;
  onDelete: (list: RecipientList) => void;
}

function formatDate(dateStr?: string | null): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "2-digit",
      year: "numeric",
    });
  } catch {
    return "—";
  }
}

export const RecipientListsTable: React.FC<RecipientListsTableProps> = ({
  lists,
  onManage,
  onEdit,
  onDelete,
}) => {
  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
      {/* Desktop / Tablet Table */}
      <div className="hidden sm:block overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-slate-50/80 text-slate-500 text-[11px] font-semibold uppercase tracking-wider h-11 border-b border-slate-200/80 select-none">
              <th className="pl-6 pr-4 py-2 w-1/3">List Name</th>
              <th className="px-4 py-2 w-1/3">Description</th>
              <th className="px-4 py-2">Recipients</th>
              <th className="px-4 py-2 hidden lg:table-cell">Last Updated</th>
              <th className="px-4 py-2 text-right pr-6">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-xs text-slate-800">
            {lists.map((list) => (
              <tr
                key={list.id}
                className="group hover:bg-slate-50/70 transition-colors h-14"
              >
                {/* List Name */}
                <td className="pl-6 pr-4 py-3">
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100/60 text-indigo-600 flex items-center justify-center shrink-0">
                      <Users className="w-4 h-4" />
                    </div>
                    <div className="flex flex-col min-w-0">
                      <button
                        type="button"
                        onClick={() => onManage(list)}
                        className="text-left font-semibold text-slate-900 hover:text-indigo-600 transition-colors truncate max-w-xs xl:max-w-md block"
                      >
                        {list.name}
                      </button>
                    </div>
                  </div>
                </td>

                {/* Description */}
                <td className="px-4 py-3 text-slate-500 truncate max-w-xs xl:max-w-md">
                  {list.description ? (
                    <span title={list.description}>{list.description}</span>
                  ) : (
                    <span className="text-slate-400 italic">No description</span>
                  )}
                </td>

                {/* Recipients */}
                <td className="px-4 py-3 whitespace-nowrap">
                  <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 text-xs font-medium border border-slate-200/60">
                    <User className="w-3.5 h-3.5 text-slate-400" />
                    <span>{list.recipient_count.toLocaleString()}</span>
                    <span className="text-slate-400 text-[11px] hidden sm:inline">contacts</span>
                  </div>
                </td>

                {/* Last Updated */}
                <td className="px-4 py-3 text-slate-500 whitespace-nowrap hidden lg:table-cell">
                  {formatDate(list.updated_at || list.created_at)}
                </td>

                {/* Actions */}
                <td className="px-4 py-3 text-right pr-6 whitespace-nowrap">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      type="button"
                      onClick={() => onManage(list)}
                      className="px-2.5 py-1 rounded-lg text-indigo-600 hover:text-indigo-700 font-semibold hover:bg-indigo-50 transition-colors text-xs"
                    >
                      Manage
                    </button>
                    <button
                      type="button"
                      onClick={() => onEdit(list)}
                      title="Edit list details"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                    >
                      <FileEdit className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => onDelete(list)}
                      title="Delete list"
                      className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View (< sm screens) */}
      <div className="sm:hidden divide-y divide-slate-100">
        {lists.map((list) => (
          <div key={list.id} className="p-4 space-y-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5 min-w-0">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100/60 text-indigo-600 flex items-center justify-center shrink-0">
                  <Users className="w-4 h-4" />
                </div>
                <button
                  type="button"
                  onClick={() => onManage(list)}
                  className="font-semibold text-slate-900 text-xs hover:text-indigo-600 transition-colors text-left truncate"
                >
                  {list.name}
                </button>
              </div>
              <div className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-medium shrink-0">
                <User className="w-3 h-3 text-slate-400" />
                <span>{list.recipient_count}</span>
              </div>
            </div>

            {list.description && (
              <p className="text-xs text-slate-500 line-clamp-2 leading-relaxed">
                {list.description}
              </p>
            )}

            <div className="flex items-center justify-between pt-1 border-t border-slate-50 text-[11px] text-slate-400">
              <div className="flex items-center gap-1">
                <Calendar className="w-3 h-3 text-slate-400" />
                <span>{formatDate(list.updated_at || list.created_at)}</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onManage(list)}
                  className="px-2 py-1 rounded text-indigo-600 font-semibold hover:bg-indigo-50"
                >
                  Manage
                </button>
                <button
                  type="button"
                  onClick={() => onEdit(list)}
                  className="p-1 rounded text-slate-400 hover:text-slate-700"
                >
                  <FileEdit className="w-3.5 h-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(list)}
                  className="p-1 rounded text-slate-400 hover:text-rose-600"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
