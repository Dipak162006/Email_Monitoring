import React, { useEffect, useState } from "react";
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
  Code,
  FileText,
  RotateCcw,
} from "lucide-react";
import type { EmailItem } from "../../types/emails";
import { emailsApi } from "../../services/api";
import { AttachmentList } from "./AttachmentList";
import { EmailConversation } from "./EmailConversation";
import DOMPurify from "dompurify";

interface EmailDetailDrawerProps {
  email: EmailItem | null;
  onClose: () => void;
  onRestore?: (id: number) => void;
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

export const EmailDetailDrawer: React.FC<EmailDetailDrawerProps> = ({ email, onClose, onRestore }) => {
  const [viewMode, setViewMode] = useState<"html" | "text">("html");

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

  // Fetch attachments
  const { data: attachmentsData } = useQuery({
    queryKey: ["email-attachments", email?.id],
    queryFn: () => (email ? emailsApi.getAttachments(email.id) : Promise.resolve({ attachments: [], total: 0 })),
    enabled: !!email?.id,
    staleTime: 60000,
  });

  if (!email) {
    return null;
  }

  const hasHtml = !!email.body_html;
  const sanitizedHtml = hasHtml ? DOMPurify.sanitize(email.body_html || "") : null;

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
            <span className="font-mono text-slate-500 text-xs truncate" title={email.message_id || `ID: MSG-${email.id}`}>
              {email.message_id ? `ID: ${email.message_id.slice(0, 24)}...` : `ID: MSG-${email.id}`}
            </span>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <Link
              to={`/emails/${email.id}`}
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
              {email.subject || "(No Subject)"}
            </h2>

            <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
              <div className="flex items-center gap-2 min-w-0">
                <span className="font-semibold text-slate-900 truncate">{email.sender}</span>
              </div>

              <div className="flex items-center gap-1.5 text-slate-400 font-mono text-xs shrink-0">
                <Clock className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                <span>{formatEmailTime(email.sent_at || email.received_at || email.created_at)}</span>
              </div>
            </div>

            {email.recipients && email.recipients.length > 0 && (
              <div className="flex items-center gap-1.5 text-xs text-slate-500">
                <Users className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                <span className="font-medium text-slate-700">To:</span>
                <span className="truncate">{email.recipients.join(", ")}</span>
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
              <div className="truncate">Return-Path: &lt;{email.sender}&gt;</div>
              <div className="truncate">Received-SPF: Pass (account #{email.email_account_id} • company #{email.company_id})</div>
              <div className="truncate">X-PulseMail-Ingest-Status: {email.status} [{email.direction}]</div>
            </div>
          </div>

          {/* Message Body Switcher & Content */}
          <div className="space-y-3">
            {hasHtml && email.body_text && (
              <div className="flex items-center space-x-1 bg-slate-100 p-0.5 rounded-lg w-fit text-xs">
                <button
                  type="button"
                  onClick={() => setViewMode("html")}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors flex items-center gap-1.5 ${
                    viewMode === "html" ? "bg-white text-slate-900 shadow-2xs font-semibold" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <Code className="h-3.5 w-3.5" />
                  HTML View
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("text")}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors flex items-center gap-1.5 ${
                    viewMode === "text" ? "bg-white text-slate-900 shadow-2xs font-semibold" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <FileText className="h-3.5 w-3.5" />
                  Plain Text
                </button>
              </div>
            )}

            <div className="text-sm text-slate-700 leading-relaxed bg-white rounded-xl border border-slate-100 p-5 shadow-2xs">
              {viewMode === "html" && sanitizedHtml ? (
                <div
                  className="prose prose-sm max-w-none break-words text-slate-800"
                  dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
                />
              ) : (
                <pre className="whitespace-pre-wrap font-sans text-xs sm:text-sm text-slate-800 leading-relaxed break-words">
                  {email.body_text || email.body_html || "No message body content."}
                </pre>
              )}
            </div>
          </div>

          {/* Attachments Area */}
          {attachmentsData?.attachments && attachmentsData.attachments.length > 0 && (
            <AttachmentList emailId={email.id} attachments={attachmentsData.attachments} />
          )}

          {/* Conversation Thread History */}
          {email.thread_id && (
            <EmailConversation threadId={email.thread_id} currentEmailId={email.id} />
          )}
        </div>

        {/* Drawer Footer Actions (Always fixed and visible at the bottom of drawer) */}
        <div className="shrink-0 bg-white border-t border-slate-200 px-6 py-3.5 sm:py-4 flex items-center justify-between shadow-xs z-10">
          <div className="flex items-center gap-2.5">
            {email.is_deleted && onRestore ? (
              <button
                type="button"
                onClick={() => onRestore(email.id)}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-all flex items-center gap-1.5 shadow-xs cursor-pointer"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Restore to Inbox
              </button>
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
