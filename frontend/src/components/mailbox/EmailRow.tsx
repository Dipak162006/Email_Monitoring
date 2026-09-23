import {
  Star,
  Paperclip,
  Mail,
  MailOpen,
  Trash2,
  RotateCcw,
} from "lucide-react";
import type { EmailItem } from "../../types/emails";
import { EmailStatusBadge } from "./EmailStatusBadge";

interface EmailRowProps {
  email: EmailItem;
  isSelected: boolean;
  onToggleSelect: (id: number) => void;
  onToggleStar: (id: number, currentStarred: boolean) => void;
  onToggleRead: (id: number, currentRead: boolean) => void;
  onDelete?: (id: number) => void;
  onMoveToTrash?: (id: number) => void;
  onPermanentDelete?: (id: number) => void;
  onRestore?: (id: number) => void;
  onClick: (email: EmailItem) => void;
}

function getSenderInitials(sender: string): string {
  if (!sender) return "EM";
  const clean = sender.replace(/<.*?>/, "").trim();
  const parts = clean.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return clean.slice(0, 2).toUpperCase();
}

function getAvatarColor(sender: string): string {
  const hash = sender.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const colors = [
    "bg-indigo-100 text-indigo-700",
    "bg-purple-100 text-purple-700",
    "bg-sky-100 text-sky-700",
    "bg-emerald-100 text-emerald-700",
    "bg-amber-100 text-amber-700",
    "bg-rose-100 text-rose-700",
  ];
  return colors[hash % colors.length];
}

function formatTimestamp(dateStr?: string | null): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const isToday =
    date.getDate() === now.getDate() &&
    date.getMonth() === now.getMonth() &&
    date.getFullYear() === now.getFullYear();

  if (isToday) {
    return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  }

  const isThisYear = date.getFullYear() === now.getFullYear();
  if (isThisYear) {
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  }

  return date.toLocaleDateString([], { month: "short", day: "numeric", year: "2-digit" });
}

export const EmailRow: React.FC<EmailRowProps> = ({
  email,
  isSelected,
  onToggleSelect,
  onToggleStar,
  onToggleRead,
  onDelete,
  onMoveToTrash,
  onPermanentDelete,
  onRestore,
  onClick,
}) => {
  const isUnread = !email.is_read;
  const isBounced = email.status === "BOUNCED";
  const isOutgoing = email.direction === "OUTGOING";
  const initials = getSenderInitials(email.sender);
  const avatarColor = getAvatarColor(email.sender);
  const formattedTime = formatTimestamp(email.received_at || email.sent_at || email.created_at);

  const cleanSnippet = email.body_text
    ? email.body_text.replace(/\s+/g, " ").trim().slice(0, 110)
    : "";

  return (
    <div
      onClick={() => onClick(email)}
      className={`email-row group relative flex flex-col lg:grid lg:grid-cols-12 lg:items-center gap-2 lg:gap-4 px-5 py-3 transition-colors cursor-pointer border-b border-slate-100/80 ${
        isSelected
          ? "bg-indigo-50/50"
          : isUnread
          ? "bg-indigo-50/15 hover:bg-indigo-50/30"
          : "bg-white hover:bg-slate-50/80"
      }`}
    >
      {/* 1. State Column: Selection, Star, Unread Indicator */}
      <div
        className="col-span-1 flex items-center gap-2.5"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          type="checkbox"
          checked={isSelected}
          onChange={() => onToggleSelect(email.id)}
          className="row-selector w-4 h-4 rounded text-indigo-600 border-slate-300 focus:ring-indigo-500 accent-indigo-600 cursor-pointer"
          aria-label={`Select email from ${email.sender}`}
        />

        <button
          type="button"
          onClick={() => onToggleStar(email.id, email.is_starred)}
          className={`transition-colors p-0.5 rounded cursor-pointer ${
            email.is_starred ? "text-amber-500 hover:text-amber-600" : "text-slate-300 hover:text-amber-400"
          }`}
          title={email.is_starred ? "Unstar" : "Star"}
          aria-label={email.is_starred ? "Unstar email" : "Star email"}
        >
          <Star className="h-4 w-4" fill={email.is_starred ? "currentColor" : "none"} />
        </button>

        <span
          className={`w-2 h-2 rounded-full shrink-0 ${isUnread ? "bg-indigo-600" : "bg-transparent"}`}
          title={isUnread ? "Unread Message" : undefined}
        />
      </div>

      {/* 2. Sender Column: Avatar, Sender Name & Gateway */}
      <div className="col-span-3 flex items-center gap-2.5 min-w-0">
        <div
          className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold shrink-0 shadow-2xs ${avatarColor}`}
        >
          {initials}
        </div>
        <div className="flex flex-col min-w-0">
          <span
            className={`text-xs truncate ${
              isUnread ? "font-bold text-slate-900" : "font-medium text-slate-700"
            }`}
          >
            {email.sender}
          </span>
          <div className="flex items-center gap-1 mt-0.5">
            <span className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200 truncate">
              {isOutgoing ? "Outgoing" : "Incoming"}
            </span>
          </div>
        </div>
      </div>

      {/* 3. Subject & Snippet Column */}
      <div className="col-span-5 flex items-center gap-2 min-w-0">
        <div className="flex flex-col min-w-0 w-full">
          <div className="flex items-center gap-1.5 min-w-0">
            <span
              className={`text-xs truncate ${
                isUnread ? "font-bold text-slate-900" : "font-medium text-slate-700"
              }`}
            >
              {email.subject || "(No Subject)"}
            </span>
            {(email.attachment_count ?? 0) > 0 && (
              <span className="flex items-center text-slate-400 text-xs shrink-0 ml-1">
                <Paperclip className="h-3 w-3" />
              </span>
            )}
          </div>
          {cleanSnippet && (
            <span className="text-[11px] text-slate-500 truncate mt-0.5">
              {cleanSnippet}
            </span>
          )}
        </div>
      </div>

      {/* 4. Telemetry Status Badges Column */}
      <div className="col-span-2 flex items-center justify-center gap-1.5 flex-wrap">
        {isBounced && <EmailStatusBadge status="Hard Bounce" />}
        {!isBounced && isOutgoing && <EmailStatusBadge status="Sent" />}
        {!isBounced && !isOutgoing && isUnread && <EmailStatusBadge status="Unread" />}
        {!isBounced && !isOutgoing && !isUnread && <EmailStatusBadge status="Delivered" />}
      </div>

      {/* 5. Timestamp Column */}
      <div className="col-span-1 flex items-center justify-end">
        <span className="text-xs text-slate-500 font-medium whitespace-nowrap">
          {formattedTime}
        </span>
      </div>

      {/* Floating Quick Actions on Hover */}
      <div
        className="row-actions absolute right-4 top-1/2 -translate-y-1/2 opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto flex items-center gap-1 bg-white border border-slate-200 px-2 py-1 rounded-lg shadow-md z-10 transition-opacity"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          onClick={() => onToggleStar(email.id, email.is_starred)}
          className={`p-1 rounded transition-colors ${
            email.is_starred ? "text-amber-500 hover:text-amber-600" : "text-slate-400 hover:text-amber-500 hover:bg-slate-100"
          }`}
          title={email.is_starred ? "Unstar" : "Star"}
          aria-label="Toggle star"
        >
          <Star className="h-4 w-4" fill={email.is_starred ? "currentColor" : "none"} />
        </button>

        <button
          type="button"
          onClick={() => onToggleRead(email.id, email.is_read)}
          className="p-1 rounded text-slate-500 hover:text-indigo-600 hover:bg-slate-100 transition-colors"
          title={email.is_read ? "Mark Unread" : "Mark Read"}
          aria-label={email.is_read ? "Mark unread" : "Mark read"}
        >
          {email.is_read ? <Mail className="h-4 w-4" /> : <MailOpen className="h-4 w-4" />}
        </button>

        {email.is_deleted ? (
          <>
            {onRestore && (
              <button
                type="button"
                onClick={() => onRestore(email.id)}
                className="p-1 rounded text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50 transition-colors cursor-pointer"
                title="Restore to Inbox"
                aria-label="Restore email"
              >
                <RotateCcw className="h-4 w-4" />
              </button>
            )}
            <button
              type="button"
              onClick={() => (onPermanentDelete ? onPermanentDelete(email.id) : onDelete?.(email.id))}
              className="p-1 rounded text-rose-600 hover:text-rose-800 hover:bg-rose-50 transition-colors cursor-pointer"
              title="Delete Permanently"
              aria-label="Delete email permanently"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => (onMoveToTrash ? onMoveToTrash(email.id) : onDelete?.(email.id))}
            className="p-1 rounded text-slate-500 hover:text-rose-600 hover:bg-rose-50 transition-colors cursor-pointer"
            title="Move to Trash"
            aria-label="Move email to trash"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );
};
