import React from "react";
import { Users, Calendar, Mail, Clock } from "lucide-react";
import type { Campaign } from "../../types/campaign";
import type { AuthorizedEmailAccount } from "../../types/emails";
import { CampaignStatusBadge } from "./CampaignStatusBadge";
import { CampaignActionsMenu } from "./CampaignActionsMenu";

interface CampaignMobileCardProps {
  campaign: Campaign;
  senderAccount?: AuthorizedEmailAccount;
  isMenuOpen: boolean;
  onToggleMenu: (e: React.MouseEvent) => void;
  onCloseMenu: () => void;
  onView: (campaign: Campaign) => void;
  onEdit?: (campaign: Campaign) => void;
  onManageRecipients?: (campaign: Campaign) => void;
  onSendNow?: (campaign: Campaign) => void;
  onPause?: (campaign: Campaign) => void;
  onResume?: (campaign: Campaign) => void;
  onCancel?: (campaign: Campaign) => void;
  onDelete?: (campaign: Campaign) => void;
  isMutating?: boolean;
}

function formatScheduledDate(dateStr?: string | null): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return "—";
  }
}

function formatCreatedDate(dateStr: string): string {
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return dateStr;
    const now = new Date();
    const isToday =
      d.getDate() === now.getDate() &&
      d.getMonth() === now.getMonth() &&
      d.getFullYear() === now.getFullYear();
    if (isToday) return "Today";

    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday =
      d.getDate() === yesterday.getDate() &&
      d.getMonth() === yesterday.getMonth() &&
      d.getFullYear() === yesterday.getFullYear();
    if (isYesterday) return "Yesterday";

    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return dateStr;
  }
}

export const CampaignMobileCard: React.FC<CampaignMobileCardProps> = ({
  campaign,
  senderAccount,
  isMenuOpen,
  onToggleMenu,
  onCloseMenu,
  onView,
  onEdit,
  onManageRecipients,
  onSendNow,
  onPause,
  onResume,
  onCancel,
  onDelete,
  isMutating = false,
}) => {
  const senderName =
    senderAccount?.name || campaign.email_account_name || "Assigned Account";
  const senderEmail =
    senderAccount?.email_address ||
    campaign.email_account_address ||
    `Account #${campaign.email_account_id}`;

  return (
    <div
      className="bg-white p-4.5 rounded-xl border border-slate-200/80 shadow-2xs flex flex-col gap-3 transition-colors hover:border-slate-300"
    >
      {/* Top row: Campaign name & Action Menu */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="min-w-0">
            <button
              type="button"
              onClick={() => onView(campaign)}
              title={campaign.name}
              className="font-bold text-sm text-slate-900 truncate hover:text-indigo-600 leading-snug text-left focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 rounded-sm block w-full"
            >
              {campaign.name}
            </button>
          </h3>
          <p
            title={campaign.subject || undefined}
            className={`text-xs truncate mt-0.5 ${
              campaign.subject ? "text-slate-500" : "text-slate-400 italic"
            }`}
          >
            {campaign.subject || "No subject"}
          </p>
        </div>

        <div className="shrink-0" onClick={(e) => e.stopPropagation()}>
          <CampaignActionsMenu
            campaign={campaign}
            isOpen={isMenuOpen}
            onToggle={onToggleMenu}
            onClose={onCloseMenu}
            onView={onView}
            onEdit={onEdit}
            onManageRecipients={onManageRecipients}
            onSendNow={onSendNow}
            onPause={onPause}
            onResume={onResume}
            onCancel={onCancel}
            onDelete={onDelete}
            isMutating={isMutating}
          />
        </div>
      </div>

      {/* Status & Recipient badge */}
      <div className="flex items-center gap-2 flex-wrap">
        <CampaignStatusBadge status={campaign.status} />

        {campaign.recipient_count !== undefined && campaign.recipient_count !== null ? (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-100/70 text-slate-600 text-[11px] font-medium border border-slate-200/50">
            <Users className="h-3 w-3 text-slate-400" />
            <span>{campaign.recipient_count.toLocaleString()} recipients</span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-slate-100/50 text-slate-400 text-[11px] font-medium border border-slate-200/40">
            <Users className="h-3 w-3 text-slate-400" />
            <span>— recipients</span>
          </span>
        )}
      </div>

      {/* Sender Information */}
      <div className="flex items-center gap-2 text-xs text-slate-600 pt-2 border-t border-slate-100 min-w-0">
        <Mail className="h-3.5 w-3.5 text-slate-400 shrink-0" />
        <span className="font-medium text-slate-800 truncate">{senderName}</span>
        <span className="text-slate-400 truncate">({senderEmail})</span>
      </div>

      {/* Dates: Scheduled & Created */}
      <div className="flex items-center justify-between text-[11px] text-slate-500">
        <div className="flex items-center gap-1.5 truncate">
          <Clock className="h-3 w-3 text-slate-400 shrink-0" />
          <span>Scheduled: </span>
          <span className="font-medium text-slate-700">
            {campaign.scheduled_at ? formatScheduledDate(campaign.scheduled_at) : "—"}
          </span>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          <Calendar className="h-3 w-3 text-slate-400" />
          <span>{formatCreatedDate(campaign.created_at)}</span>
        </div>
      </div>
    </div>
  );
};
