import React, { useState } from "react";
import { Copy, Check, Edit, Trash2, Calendar, FastForward, StopCircle, Clock, Tag } from "lucide-react";
import type { CampaignRecipient } from "../../../types/campaign";
import { RecipientStatusBadge } from "./RecipientStatusBadge";

interface RecipientMobileCardProps {
  recipient: CampaignRecipient;
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

export const RecipientMobileCard: React.FC<RecipientMobileCardProps> = ({
  recipient,
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
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    onCopyEmail(recipient.email);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const fullName = [recipient.first_name, recipient.last_name]
    .filter(Boolean)
    .join(" ");

  const getInitials = () => {
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

  const isActionable = () => {
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

  const nextSendFormatted = formatDateTime(recipient.next_step_due_at);
  const actionable = isActionable();

  return (
    <div className="p-3.5 bg-slate-50/70 border border-slate-200/80 rounded-xl space-y-2.5 min-w-0">
      {/* Top Header Row */}
      <div className="flex items-center justify-between gap-2 min-w-0">
        <div className="flex items-center gap-2 min-w-0">
          <div className="w-6 h-6 rounded-full bg-indigo-100 text-indigo-700 font-bold text-[10px] flex items-center justify-center shrink-0">
            {getInitials()}
          </div>
          <div className="min-w-0 truncate">
            <p className="font-semibold text-slate-900 text-xs truncate">
              {fullName || recipient.email.split("@")[0]}
            </p>
          </div>
        </div>
        <RecipientStatusBadge
          status={recipient.status}
          stoppedReason={recipient.stopped_reason}
          currentStepNumber={recipient.current_step_number}
          nextStepDueAt={recipient.next_step_due_at}
          className="shrink-0"
        />
      </div>

      {/* Monospace Email Box */}
      <div className="flex items-center justify-between gap-2 bg-white px-2.5 py-1.5 rounded-lg border border-slate-200/70 text-xs min-w-0">
        <span className="font-mono text-slate-800 text-xs truncate select-all">
          {recipient.email}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="p-0.5 text-slate-400 hover:text-slate-600 transition-colors shrink-0"
          title="Copy email"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-emerald-600" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </button>
      </div>

      {/* Recipient Tags */}
      {recipient.tags && recipient.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 px-0.5">
          {recipient.tags.map((t) => (
            <span
              key={t}
              className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-indigo-50 text-indigo-700 border border-indigo-100"
            >
              #{t}
            </span>
          ))}
        </div>
      )}

      {/* Next Send Info (if pending) */}
      {nextSendFormatted && (
        <div className="flex items-center gap-1.5 px-2.5 py-1.5 bg-blue-50/60 border border-blue-100 rounded-lg text-[11px] text-blue-800 font-medium">
          <Clock className="h-3.5 w-3.5 text-blue-600 shrink-0" />
          <span>Next send: {nextSendFormatted}</span>
        </div>
      )}

      {/* Footer Info & Actions */}
      <div className="flex items-center justify-between text-slate-500 text-xs pt-0.5">
        <span className="text-[11px]">Added {formatDate(recipient.created_at)}</span>

        <div className="flex items-center gap-1">
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

          {/* DRAFT Actions: Edit & Delete */}
          {isEditable && (
            <>
              <button
                type="button"
                onClick={() => onEdit(recipient)}
                className="p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-200 transition-colors"
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

          {/* Follow-Up Controls */}
          {canManageFollowups && actionable && (
            <>
              {onReschedule && (
                <button
                  type="button"
                  onClick={() => onReschedule(recipient)}
                  className="px-2 py-1 rounded bg-white border border-slate-200 text-indigo-700 hover:bg-indigo-50 text-[11px] font-medium flex items-center gap-1 transition-colors"
                  title="Reschedule next send"
                  aria-label={`Reschedule next step for ${recipient.email}`}
                >
                  <Calendar className="h-3 w-3 text-indigo-600" />
                  <span>Reschedule</span>
                </button>
              )}
              {onSkip && (
                <button
                  type="button"
                  onClick={() => onSkip(recipient)}
                  className="px-2 py-1 rounded bg-white border border-slate-200 text-blue-700 hover:bg-blue-50 text-[11px] font-medium flex items-center gap-1 transition-colors"
                  title="Skip next step"
                  aria-label={`Skip next step for ${recipient.email}`}
                >
                  <FastForward className="h-3 w-3 text-blue-600" />
                  <span>Skip</span>
                </button>
              )}
              {onStop && (
                <button
                  type="button"
                  onClick={() => onStop(recipient)}
                  className="px-2 py-1 rounded bg-white border border-slate-200 text-rose-700 hover:bg-rose-50 text-[11px] font-medium flex items-center gap-1 transition-colors"
                  title="Stop future follow-ups"
                  aria-label={`Stop follow-ups for ${recipient.email}`}
                >
                  <StopCircle className="h-3 w-3 text-rose-600" />
                  <span>Stop</span>
                </button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
