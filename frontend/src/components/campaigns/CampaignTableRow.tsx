import React from "react";
import {
  Zap,
  Clock,
  CalendarClock,
  PauseCircle,
  CheckCircle2,
  FileEdit,
  AlertCircle,
  Ban,
  Users,
  Eye,
  Edit,
  Trash2,
  Loader2,
} from "lucide-react";
import type { Campaign } from "../../types/campaign";
import type { AuthorizedEmailAccount } from "../../types/emails";
import { CampaignStatusBadge } from "./CampaignStatusBadge";
import { Tooltip } from "../ui/Tooltip";

export interface CampaignTableRowProps {
  campaign: Campaign;
  senderAccount?: AuthorizedEmailAccount;
  onView: (campaign: Campaign) => void;
  onEdit?: (campaign: Campaign) => void;
  onManageRecipients?: (campaign: Campaign) => void;
  onSendNow?: (campaign: Campaign) => void;
  onPause?: (campaign: Campaign) => void;
  onResume?: (campaign: Campaign) => void;
  onCancel?: (campaign: Campaign) => void;
  onDelete?: (campaign: Campaign) => void;
  isMutating?: boolean;
  isMenuOpen?: boolean;
  onToggleMenu?: (e: React.MouseEvent) => void;
  onCloseMenu?: () => void;
}

function getStatusIcon(status: Campaign["status"]) {
  switch (status) {
    case "RUNNING":
      return (
        <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shrink-0">
          <Zap className="h-4 w-4" />
        </div>
      );
    case "SCHEDULED":
      return (
        <div className="w-8 h-8 rounded-lg bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600 shrink-0">
          <CalendarClock className="h-4 w-4" />
        </div>
      );
    case "QUEUED":
      return (
        <div className="w-8 h-8 rounded-lg bg-sky-50 border border-sky-100 flex items-center justify-center text-sky-600 shrink-0">
          <Clock className="h-4 w-4" />
        </div>
      );
    case "PAUSED":
      return (
        <div className="w-8 h-8 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-600 shrink-0">
          <PauseCircle className="h-4 w-4" />
        </div>
      );
    case "COMPLETED":
      return (
        <div className="w-8 h-8 rounded-lg bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600 shrink-0">
          <CheckCircle2 className="h-4 w-4" />
        </div>
      );
    case "DRAFT":
      return (
        <div className="w-8 h-8 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-500 shrink-0">
          <FileEdit className="h-4 w-4" />
        </div>
      );
    case "FAILED":
      return (
        <div className="w-8 h-8 rounded-lg bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-600 shrink-0">
          <AlertCircle className="h-4 w-4" />
        </div>
      );
    case "CANCELLED":
    default:
      return (
        <div className="w-8 h-8 rounded-lg bg-slate-100 border border-slate-200 flex items-center justify-center text-slate-400 shrink-0">
          <Ban className="h-4 w-4" />
        </div>
      );
  }
}

function formatDateTime(dateStr?: string | null): { date: string; time: string } | null {
  if (!dateStr) return null;
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return null;

    const now = new Date();
    const isToday =
      d.getDate() === now.getDate() &&
      d.getMonth() === now.getMonth() &&
      d.getFullYear() === now.getFullYear();

    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday =
      d.getDate() === yesterday.getDate() &&
      d.getMonth() === yesterday.getMonth() &&
      d.getFullYear() === yesterday.getFullYear();

    const date = isToday
      ? "Today"
      : isYesterday
      ? "Yesterday"
      : d.toLocaleDateString("en-US", {
          month: "short",
          day: "numeric",
          year: "numeric",
        });

    const time = d.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });

    return { date, time };
  } catch {
    return null;
  }
}

export const CampaignTableRow: React.FC<CampaignTableRowProps> = ({
  campaign,
  senderAccount,
  onView,
  onEdit,
  onManageRecipients,
  onDelete,
  isMutating = false,
}) => {
  const senderName =
    senderAccount?.name || campaign.email_account_name || "Assigned Account";
  const senderEmail =
    senderAccount?.email_address ||
    campaign.email_account_address ||
    `Account #${campaign.email_account_id}`;

  const recipientCount = campaign.recipient_count;
  const scheduled = formatDateTime(campaign.scheduled_at);
  const created = formatDateTime(campaign.created_at);

  const status = (campaign.status || "").toUpperCase();
  const isDraft = status === "DRAFT";
  const isDeletable = ["DRAFT", "COMPLETED", "CANCELLED", "FAILED"].includes(status);

  return (
    <tr className="group transition-colors duration-150 hover:bg-slate-50/80 border-b border-slate-100/90 last:border-b-0">
      {/* 1. Campaign Identity & Subject */}
      <td className="py-3 px-4 min-w-[200px] max-w-[320px]">
        <div className="flex items-center gap-3 min-w-0">
          {getStatusIcon(campaign.status)}
          <div className="flex flex-col min-w-0 flex-1">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onView(campaign);
              }}
              title={campaign.name}
              className="font-semibold text-slate-900 truncate hover:text-indigo-600 text-sm leading-snug text-left focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded-xs block w-full"
            >
              {campaign.name}
            </button>
            <span
              title={campaign.subject || undefined}
              className={`text-xs truncate mt-0.5 ${
                campaign.subject ? "text-slate-500" : "text-slate-400 italic"
              }`}
            >
              {campaign.subject || "No subject"}
            </span>
          </div>
        </div>
      </td>

      {/* 2. Sender */}
      <td className="py-3 px-4 text-xs max-w-[180px]">
        <span className="font-medium text-slate-800 block truncate" title={senderName}>
          {senderName}
        </span>
        <span className="text-slate-400 text-[11px] block truncate mt-0.5" title={senderEmail}>
          {senderEmail}
        </span>
      </td>

      {/* 3. Target Size */}
      <td className="py-3 px-4 text-xs whitespace-nowrap">
        {recipientCount !== undefined && recipientCount !== null ? (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100/70 text-slate-600 text-xs font-normal border border-slate-200/50">
            <Users className="h-3.5 w-3.5 text-slate-400 shrink-0" />
            <span>
              {recipientCount.toLocaleString()} {recipientCount === 1 ? "recipient" : "recipients"}
            </span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-slate-100/50 text-slate-400 text-xs font-normal border border-slate-200/40">
            <Users className="h-3.5 w-3.5 text-slate-400 shrink-0" />
            <span>— recipients</span>
          </span>
        )}
      </td>

      {/* 4. Status */}
      <td className="py-3 px-4 whitespace-nowrap">
        <CampaignStatusBadge status={campaign.status} />
      </td>

      {/* 5. Scheduled Date */}
      <td className="py-3 px-4 text-xs whitespace-nowrap">
        {scheduled ? (
          <div className="flex flex-col min-w-0">
            <span className="font-medium text-slate-700 whitespace-nowrap">
              {scheduled.date}
            </span>
            <span className="text-[11px] text-slate-400 whitespace-nowrap mt-0.5">
              {scheduled.time}
            </span>
          </div>
        ) : (
          <span className="text-slate-400">—</span>
        )}
      </td>

      {/* 6. Created Date + Contextual Action Buttons */}
      <td className="py-3 px-4 text-xs text-slate-500 relative whitespace-nowrap">
        {/* Default View: Created Timestamp */}
        {created ? (
          <div className="flex flex-col min-w-0 transition-opacity duration-150">
            <span className="font-medium text-slate-700 whitespace-nowrap" title={campaign.created_at}>
              {created.date}
            </span>
            <span className="text-[11px] text-slate-400 whitespace-nowrap mt-0.5">
              {created.time}
            </span>
          </div>
        ) : (
          <span className="text-slate-400">—</span>
        )}

        {/* Floating Quick Action Icons on Hover / Focus */}
        <div
          className="campaign-row-actions absolute right-3 top-1/2 -translate-y-1/2 opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto focus-within:opacity-100 focus-within:pointer-events-auto flex items-center gap-1 bg-white border border-slate-200/90 px-1.5 py-1 rounded-lg shadow-md z-10 transition-opacity"
          onClick={(e) => e.stopPropagation()}
        >
          {isMutating ? (
            <div className="p-1.5 text-slate-400">
              <Loader2 className="h-4 w-4 animate-spin" />
            </div>
          ) : (
            <>
              {/* 1. View Campaign */}
              <Tooltip content="View campaign" side="top">
                <button
                  type="button"
                  onClick={() => onView(campaign)}
                  aria-label="View campaign"
                  className="p-1 rounded text-slate-500 hover:text-indigo-600 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                >
                  <Eye className="h-4 w-4" />
                </button>
              </Tooltip>

              {/* 2. Edit Draft (only for DRAFT campaigns) */}
              {isDraft && onEdit && (
                <Tooltip content="Edit draft" side="top">
                  <button
                    type="button"
                    onClick={() => onEdit(campaign)}
                    aria-label="Edit draft"
                    className="p-1 rounded text-slate-500 hover:text-indigo-600 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                  >
                    <Edit className="h-4 w-4" />
                  </button>
                </Tooltip>
              )}

              {/* 3. Manage Recipients */}
              {onManageRecipients && (
                <Tooltip content="Manage recipients" side="top">
                  <button
                    type="button"
                    onClick={() => onManageRecipients(campaign)}
                    aria-label="Manage recipients"
                    className="p-1 rounded text-slate-500 hover:text-indigo-600 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                  >
                    <Users className="h-4 w-4" />
                  </button>
                </Tooltip>
              )}

              {/* 4. Delete Campaign (only for permitted statuses) */}
              {isDeletable && onDelete && (
                <Tooltip content="Delete campaign" side="top">
                  <button
                    type="button"
                    onClick={() => onDelete(campaign)}
                    aria-label="Delete campaign"
                    className="p-1 rounded text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors focus:outline-none focus:ring-1 focus:ring-rose-500 cursor-pointer"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </Tooltip>
              )}
            </>
          )}
        </div>
      </td>
    </tr>
  );
};
