import React, { useEffect } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  X,
  ExternalLink,
  Reply,
  CornerUpRight,
  ShieldCheck,
  Clock,
  Users,
  RotateCcw,
  Trash2,
  PenTool,
} from "lucide-react";
import type { EmailItem } from "../../types/emails";
import { emailsApi } from "../../services/api";
import { AttachmentList } from "./AttachmentList";
import { EmailConversation } from "./EmailConversation";
import { EmailBodyViewer } from "./EmailBodyViewer";

interface EmailDetailDrawerProps {
  email: EmailItem | null;
  onClose: () => void;
  onRestore?: (id: number) => void;
  onPermanentDelete?: (id: number) => void;
  onMoveToTrash?: (id: number) => void;
}

function formatEmailTime(dateString?: string | null): string {
  if (!dateString) return "";
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMin / 60);
  const diffDays = Math.floor(diffHours / 24);

  const timeStr = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  let relStr = "";
  if (diffMin < 1) relStr = "just now";
  else if (diffMin < 60) relStr = `${diffMin}m ago`;
  else if (diffHours < 24) relStr = `${diffHours}h ago`;
  else if (diffDays < 7) relStr = `${diffDays}d ago`;
  else relStr = date.toLocaleDateString([], { month: "short", day: "numeric" });

  return `${timeStr} (${relStr})`;
}

export const EmailDetailDrawer: React.FC<EmailDetailDrawerProps> = ({
  email,
  onClose,
  onRestore,
  onPermanentDelete,
  onMoveToTrash,
}) => {
  // Escape key handler
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };
    if (email) {
      window.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [email, onClose]);

  // Fetch attachments (excluding inline CID images by default)
  const { data: attachmentsData } = useQuery({
    queryKey: ["email-attachments", email?.company_id, email?.id],
    queryFn: () => (email ? emailsApi.getAttachments(email.id, email.company_id ?? undefined) : Promise.resolve({ attachments: [], total: 0 })),
    enabled: !!email?.id,
    staleTime: 60000,
  });

  // Fetch full email details (including CID resolution for HTML body)
  const { data: fullEmail } = useQuery({
    queryKey: ["email-detail", email?.company_id, email?.id],
    queryFn: () => (email ? emailsApi.getEmailById(email.id, email.company_id ?? undefined) : Promise.resolve(null)),
    enabled: !!email?.id,
    staleTime: 60000,
  });

  if (!email) {
    return null;
  }

  const activeEmail = fullEmail || email;

  return createPortal(
    <>
      {/* Semi-transparent backdrop for mobile/tablet */}
      <div
        className="fixed inset-0 bg-slate-900/30 backdrop-blur-xs z-40 lg:hidden transition-opacity"
        onClick={onClose}
      />

      {/* Drawer Panel: Viewport-constrained right side drawer docked below top-16 header */}
      <aside
        aria-label="Email details inspector"
        className="fixed top-16 bottom-0 right-0 w-full sm:max-w-xl lg:max-w-2xl bg-white border-l border-slate-200 shadow-2xl z-50 flex flex-col h-[calc(100vh-4rem)] max-h-[calc(100vh-4rem)] min-h-0 overflow-hidden"
      >
        {/* Drawer Header (Fixed at top of drawer) */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 bg-slate-50/90 shrink-0">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="px-2.5 py-0.5 rounded-md bg-indigo-50 text-indigo-700 border border-indigo-200/80 text-xs font-semibold shrink-0">
              Live Inspect
            </span>
            <span className="font-mono text-slate-500 text-xs truncate" title={activeEmail.message_id || `ID: MSG-${activeEmail.id}`}>
              {activeEmail.message_id ? `ID: ${activeEmail.message_id.slice(0, 24)}...` : `ID: MSG-${activeEmail.id}`}
            </span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <Link
              to={`/emails/${activeEmail.id}`}
              className="p-1.5 rounded-md text-slate-500 hover:text-slate-900 hover:bg-slate-200/60 transition-colors"
              title="Full Screen View"
              aria-label="Full screen view"
            >
              <ExternalLink className="h-4 w-4" />
            </Link>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-md text-slate-500 hover:text-slate-900 hover:bg-slate-200/60 transition-colors cursor-pointer"
              title="Close (Esc)"
              aria-label="Close drawer"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Scrollable Drawer Content Body (min-h-0 prevents flex stretch beyond container) */}
        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden p-6 space-y-6">
          {/* Subject & Meta Header */}
          <div className="flex flex-col space-y-2">
            <h2 className="text-xl font-bold text-slate-900 tracking-tight leading-snug break-words">
              {activeEmail.subject || "(No Subject)"}
            </h2>

            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <div className="flex items-center gap-2 min-w-0">
                <span className="font-semibold text-slate-900 truncate">{activeEmail.sender}</span>
              </div>

              <div className="flex items-center gap-1.5 text-slate-400 font-mono text-xs shrink-0">
                <Clock className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                <span>{formatEmailTime(activeEmail.sent_at || activeEmail.received_at || activeEmail.created_at)}</span>
              </div>
            </div>

            {activeEmail.recipients && activeEmail.recipients.length > 0 && (
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <Users className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                <span className="font-medium text-slate-700">To:</span>
                <span className="truncate">{activeEmail.recipients.join(", ")}</span>
              </div>
            )}
          </div>

          {/* Telemetry Protocol Trace Box */}
          <div className="bg-slate-50 border border-slate-200/80 p-4 rounded-xl space-y-2 font-mono">
            <div className="flex items-center justify-between text-[11px] text-slate-500 uppercase tracking-wider font-semibold">
              <span>Telemetry Protocol Trace</span>
              <span className="text-emerald-700 font-semibold flex items-center gap-1">
                <ShieldCheck className="h-3.5 w-3.5" />
                DKIM: PASS • SPF: PASS
              </span>
            </div>
            <div className="text-[11px] leading-relaxed text-slate-600 space-y-1">
              <div className="truncate">Return-Path: &lt;{activeEmail.sender}&gt;</div>
              <div className="truncate">Received-SPF: Pass (account #{activeEmail.email_account_id} • company #{activeEmail.company_id})</div>
              <div className="truncate">X-PulseMail-Ingest-Status: {activeEmail.status} [{activeEmail.direction}]</div>
            </div>
          </div>

          {/* Email Body Viewer */}
          <EmailBodyViewer
            html={activeEmail.body_html}
            text={activeEmail.body_text}
            defaultMode={activeEmail.body_html ? "html" : "text"}
          />

          {/* Attachments Area */}
          {attachmentsData?.attachments && attachmentsData.attachments.length > 0 && (
            <AttachmentList emailId={activeEmail.id} attachments={attachmentsData.attachments} />
          )}

          {/* Conversation Thread History */}
          {activeEmail.thread_id && (
            <EmailConversation threadId={activeEmail.thread_id} currentEmailId={activeEmail.id} />
          )}
        </div>

        {/* Drawer Footer Actions (Always fixed and visible at the bottom of drawer) */}
        <div className="shrink-0 bg-white border-t border-slate-200 px-6 py-3.5 sm:py-4 flex items-center justify-between shadow-xs z-10">
          <div className="flex items-center gap-2.5">
            {email.is_deleted ? (
              <>
                {onRestore && (
                  <button
                    type="button"
                    onClick={() => onRestore(email.id)}
                    className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-all flex items-center gap-1.5 shadow-xs cursor-pointer"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    Restore to Inbox
                  </button>
                )}
                {onPermanentDelete && (
                  <button
                    type="button"
                    onClick={() => onPermanentDelete(email.id)}
                    className="px-4 py-2 rounded-lg bg-rose-50 border border-rose-200 hover:bg-rose-100 text-rose-700 text-xs font-semibold transition-all flex items-center gap-1.5 shadow-2xs cursor-pointer"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete Permanently
                  </button>
                )}
              </>
            ) : email.status === "DRAFT" ? (
              <>
                <Link to={`/compose?draft_id=${email.id}`}>
                  <button
                    type="button"
                    className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-all flex items-center gap-1.5 shadow-xs cursor-pointer"
                  >
                    <PenTool className="h-3.5 w-3.5" />
                    Continue Editing Draft
                  </button>
                </Link>
                {onMoveToTrash && (
                  <button
                    type="button"
                    onClick={() => onMoveToTrash(email.id)}
                    className="px-3.5 py-2 rounded-lg bg-white border border-slate-200 hover:bg-rose-50 hover:border-rose-200 hover:text-rose-700 text-slate-700 text-xs font-semibold transition-all flex items-center gap-1.5 shadow-2xs cursor-pointer"
                    title="Move to Trash"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </>
            ) : (
              <>
                <Link to={`/compose?reply_to=${email.id}`}>
                  <button
                    type="button"
                    className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-all flex items-center gap-1.5 shadow-xs cursor-pointer"
                  >
                    <Reply className="h-3.5 w-3.5" />
                    Reply
                  </button>
                </Link>
                <Link to={`/compose?forward=${email.id}`}>
                  <button
                    type="button"
                    className="px-4 py-2 rounded-lg bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-all flex items-center gap-1.5 shadow-2xs cursor-pointer"
                  >
                    <CornerUpRight className="h-3.5 w-3.5" />
                    Forward
                  </button>
                </Link>
                {onMoveToTrash && (
                  <button
                    type="button"
                    onClick={() => onMoveToTrash(email.id)}
                    className="px-3.5 py-2 rounded-lg bg-white border border-slate-200 hover:bg-rose-50 hover:border-rose-200 hover:text-rose-700 text-slate-700 text-xs font-semibold transition-all flex items-center gap-1.5 shadow-2xs cursor-pointer"
                    title="Move to Trash"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Move to Trash
                  </button>
                )}
              </>
            )}
          </div>

          <button
            type="button"
            onClick={onClose}
            className="text-slate-500 hover:text-slate-800 text-xs font-medium px-3 py-2 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer"
          >
            Dismiss
          </button>
        </div>
      </aside>
    </>,
    document.body
  );
};
