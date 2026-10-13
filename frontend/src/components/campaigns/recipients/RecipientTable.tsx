import React, { useState } from "react";
import { Copy, Check, Edit, Trash2 } from "lucide-react";
import type { CampaignRecipient } from "../../../types/campaign";
import { RecipientStatusBadge } from "./RecipientStatusBadge";

interface RecipientTableProps {
  recipients: CampaignRecipient[];
  isEditable: boolean;
  onEdit: (recipient: CampaignRecipient) => void;
  onDelete: (recipient: CampaignRecipient) => void;
  onCopyEmail: (email: string) => void;
}

export const RecipientTable: React.FC<RecipientTableProps> = ({
  recipients,
  isEditable,
  onEdit,
  onDelete,
  onCopyEmail,
}) => {
  const [copiedId, setCopiedId] = useState<number | null>(null);

  const handleCopy = (recipient: CampaignRecipient) => {
    onCopyEmail(recipient.email);
    setCopiedId(recipient.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const getInitials = (recipient: CampaignRecipient) => {
    if (recipient.first_name && recipient.last_name) {
      return `${recipient.first_name[0]}${recipient.last_name[0]}`.toUpperCase();
    }
    if (recipient.first_name) {
      return recipient.first_name.slice(0, 2).toUpperCase();
    }
    return recipient.email.slice(0, 2).toUpperCase();
  };

  const formatDate = (isoString: string) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="w-full overflow-hidden">
      <div className="overflow-x-auto min-w-0">
        <table className="w-full text-left border-collapse min-w-[640px]">
          <thead>
            <tr className="bg-slate-50/80 border-b border-slate-200/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <th scope="col" className="py-3 px-4 w-[28%] min-w-[160px]">
                Recipient
              </th>
              <th scope="col" className="py-3 px-4 w-[36%] min-w-[200px]">
                Email Address
              </th>
              <th scope="col" className="py-3 px-4 w-[16%] min-w-[110px]">
                Status
              </th>
              <th scope="col" className="py-3 px-4 w-[14%] min-w-[100px]">
                Added Date
              </th>
              <th scope="col" className="py-3 px-4 w-[6%] text-right min-w-[70px]">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white text-xs">
            {recipients.map((recipient) => {
              const fullName = [recipient.first_name, recipient.last_name]
                .filter(Boolean)
                .join(" ");

              return (
                <tr
                  key={recipient.id}
                  className="hover:bg-slate-50/60 transition-colors group"
                >
                  {/* Recipient Identity */}
                  <td className="py-3 px-4 min-w-0">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="w-7 h-7 rounded-full bg-indigo-100 text-indigo-700 font-bold text-[11px] flex items-center justify-center shrink-0">
                        {getInitials(recipient)}
                      </div>
                      <div className="min-w-0 truncate">
                        <p className="font-semibold text-slate-900 truncate">
                          {fullName || recipient.email.split("@")[0]}
                        </p>
                      </div>
                    </div>
                  </td>

                  {/* Email Address */}
                  <td className="py-3 px-4 min-w-0">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="font-mono text-slate-800 truncate select-all">
                        {recipient.email}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleCopy(recipient)}
                        className="opacity-0 group-hover:opacity-100 focus:opacity-100 p-1 text-slate-400 hover:text-slate-600 transition-opacity"
                        title="Copy email address"
                      >
                        {copiedId === recipient.id ? (
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </button>
                    </div>
                  </td>

                  {/* Status Badge */}
                  <td className="py-3 px-4 min-w-0">
                    <RecipientStatusBadge status={recipient.status} />
                  </td>

                  {/* Added Date */}
                  <td className="py-3 px-4 min-w-0 text-slate-500 text-xs">
                    {formatDate(recipient.created_at)}
                  </td>

                  {/* Actions */}
                  <td className="py-3 px-4 text-right min-w-0 relative">
                    <div className="inline-flex items-center justify-end gap-1">
                      <button
                        type="button"
                        onClick={() => handleCopy(recipient)}
                        className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                        title="Copy email"
                      >
                        {copiedId === recipient.id ? (
                          <Check className="h-3.5 w-3.5 text-emerald-600" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </button>

                      {isEditable && (
                        <>
                          <button
                            type="button"
                            onClick={() => onEdit(recipient)}
                            className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                            title="Edit recipient"
                          >
                            <Edit className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => onDelete(recipient)}
                            className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                            title="Remove recipient"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
