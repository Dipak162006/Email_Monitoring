import React, { useState } from "react";
import { Copy, Check, Edit, Trash2, Calendar, FastForward, StopCircle, Tag } from "lucide-react";
import type { CampaignRecipient } from "../../../types/campaign";
import { RecipientStatusBadge } from "./RecipientStatusBadge";

interface RecipientTableProps {
  recipients: CampaignRecipient[];
  isEditable: boolean;
  canManageFollowups?: boolean;
  onEdit: (recipient: CampaignRecipient) => void;
  onDelete: (recipient: CampaignRecipient) => void;
  onCopyEmail: (email: string) => void;
  onStop?: (recipient: CampaignRecipient) => void;
  onSkip?: (recipient: CampaignRecipient) => void;
  onReschedule?: (recipient: CampaignRecipient) => void;
  onManageTags?: (recipient: CampaignRecipient) => void;
}

export const RecipientTable: React.FC<RecipientTableProps> = ({
  recipients,
  isEditable,
  canManageFollowups = false,
  onEdit,
  onDelete,
  onCopyEmail,
  onStop,
  onSkip,
  onReschedule,
  onManageTags,
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

  const formatDateTime = (isoString?: string | null) => {
    if (!isoString) return null;
    try {
      const date = new Date(isoString);
      return date.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch {
      return isoString;
    }
  };

  const isActionable = (recipient: CampaignRecipient) => {
    if (
      recipient.status === "COMPLETED" ||
      recipient.status === "STOPPED" ||
      recipient.status === "BOUNCED" ||
      recipient.status === "SUPPRESSED" ||
      recipient.status === "FAILED" ||
      recipient.stopped_reason ||
      recipient.replied_at
    ) {
      return false;
    }
    return true;
  };

  return (
    <div className="w-full overflow-hidden">
      <div className="overflow-x-auto min-w-0">
        <table className="w-full text-left border-collapse min-w-[760px]">
          <thead>
            <tr className="bg-slate-50/80 border-b border-slate-200/80 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <th scope="col" className="py-3 px-4 w-[24%] min-w-[150px]">
                Recipient
              </th>
              <th scope="col" className="py-3 px-4 w-[28%] min-w-[180px]">
                Email Address
              </th>
              <th scope="col" className="py-3 px-4 w-[18%] min-w-[130px]">
                Status & Sequence
              </th>
              <th scope="col" className="py-3 px-4 w-[16%] min-w-[130px]">
                Next Scheduled Send
              </th>
              <th scope="col" className="py-3 px-4 w-[14%] text-right min-w-[100px]">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white text-xs">
            {recipients.map((recipient) => {
              const fullName = [recipient.first_name, recipient.last_name]
                .filter(Boolean)
                .join(" ");
              const nextSendFormatted = formatDateTime(recipient.next_step_due_at);
              const actionable = isActionable(recipient);

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
                        {recipient.tags && recipient.tags.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {recipient.tags.map((t) => (
                              <span
                                key={t}
                                className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-indigo-50 text-indigo-700 border border-indigo-100"
                              >
                                #{t}
                              </span>
                            ))}
                          </div>
                        )}
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
                    <RecipientStatusBadge
                      status={recipient.status}
                      stoppedReason={recipient.stopped_reason}
                      currentStepNumber={recipient.current_step_number}
                      nextStepDueAt={recipient.next_step_due_at}
                    />
                  </td>

                  {/* Next Send Time */}
                  <td className="py-3 px-4 min-w-0 text-slate-600 text-xs">
                    {nextSendFormatted ? (
                      <span className="font-medium text-slate-800">
                        {nextSendFormatted}
                      </span>
                    ) : (
                      <span className="text-slate-400 font-mono">—</span>
                    )}
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

                      {onManageTags && (
                        <button
                          type="button"
                          onClick={() => onManageTags(recipient)}
                          className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                          title="Manage tags"
                          aria-label={`Manage tags for ${recipient.email}`}
                        >
                          <Tag className="h-3.5 w-3.5" />
                        </button>
                      )}

                      {/* DRAFT campaign actions: Edit & Delete */}
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

                      {/* Live Follow-Up Actions: Reschedule, Skip, Stop */}
                      {canManageFollowups && actionable && (
                        <>
                          {onReschedule && (
                            <button
                              type="button"
                              onClick={() => onReschedule(recipient)}
                              className="p-1 rounded text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 transition-colors"
                              title="Reschedule next step"
                              aria-label={`Reschedule next step for ${recipient.email}`}
                            >
                              <Calendar className="h-3.5 w-3.5" />
                            </button>
                          )}
                          {onSkip && (
                            <button
                              type="button"
                              onClick={() => onSkip(recipient)}
                              className="p-1 rounded text-blue-600 hover:text-blue-800 hover:bg-blue-50 transition-colors"
                              title="Skip next step"
                              aria-label={`Skip next step for ${recipient.email}`}
                            >
                              <FastForward className="h-3.5 w-3.5" />
                            </button>
                          )}
                          {onStop && (
                            <button
                              type="button"
                              onClick={() => onStop(recipient)}
                              className="p-1 rounded text-amber-600 hover:text-amber-800 hover:bg-amber-50 transition-colors"
                              title="Stop future follow-ups"
                              aria-label={`Stop follow-ups for ${recipient.email}`}
                            >
                              <StopCircle className="h-3.5 w-3.5" />
                            </button>
                          )}
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
