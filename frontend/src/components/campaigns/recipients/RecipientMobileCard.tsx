import React, { useState } from "react";
import { Copy, Check, Edit, Trash2 } from "lucide-react";
import type { CampaignRecipient } from "../../../types/campaign";
import { RecipientStatusBadge } from "./RecipientStatusBadge";

interface RecipientMobileCardProps {
  recipient: CampaignRecipient;
  isEditable: boolean;
  onEdit: (recipient: CampaignRecipient) => void;
  onDelete: (recipient: CampaignRecipient) => void;
  onCopyEmail: (email: string) => void;
}

export const RecipientMobileCard: React.FC<RecipientMobileCardProps> = ({
  recipient,
  isEditable,
  onEdit,
  onDelete,
  onCopyEmail,
}) => {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    onCopyEmail(recipient.email);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const getInitials = () => {
    if (recipient.first_name && recipient.last_name) {
      return `${recipient.first_name[0]}${recipient.last_name[0]}`.toUpperCase();
    }
    if (recipient.first_name) {
      return recipient.first_name.slice(0, 2).toUpperCase();
    }
    return recipient.email.slice(0, 2).toUpperCase();
  };

  const fullName = [recipient.first_name, recipient.last_name].filter(Boolean).join(" ");

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
    <div className="p-3.5 bg-slate-50/70 border border-slate-200/80 rounded-xl space-y-2.5 min-w-0">
      {/* Top Header Row */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 font-bold text-xs flex items-center justify-center shrink-0">
            {getInitials()}
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-900 truncate">
              {fullName || recipient.email.split("@")[0]}
            </p>
          </div>
        </div>
        <RecipientStatusBadge status={recipient.status} className="shrink-0" />
      </div>

      {/* Monospace Email Box */}
      <div className="flex items-center justify-between gap-2 bg-white border border-slate-200/60 p-2 rounded-lg text-xs">
        <span className="font-mono text-slate-800 break-all select-all text-[11px]">
          {recipient.email}
        </span>
        <button
          type="button"
          onClick={handleCopy}
          className="p-1 rounded text-slate-400 hover:text-slate-600 transition-colors shrink-0"
          title="Copy email address"
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-emerald-600" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </button>
      </div>

      {/* Footer Info & Actions */}
      <div className="flex items-center justify-between text-slate-500 text-xs pt-0.5">
        <span className="text-[11px]">Added {formatDate(recipient.created_at)}</span>

        <div className="flex items-center gap-1">
          {isEditable && (
            <>
              <button
                type="button"
                onClick={() => onEdit(recipient)}
                className="px-2 py-1 rounded bg-white border border-slate-200 text-slate-700 hover:bg-slate-50 text-[11px] font-medium flex items-center gap-1 transition-colors"
              >
                <Edit className="h-3 w-3 text-slate-500" />
                <span>Edit</span>
              </button>
              <button
                type="button"
                onClick={() => onDelete(recipient)}
                className="p-1 rounded text-rose-500 hover:bg-rose-50 transition-colors"
                title="Remove recipient"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
