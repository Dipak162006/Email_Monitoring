import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, MessageSquare, CornerDownLeft } from "lucide-react";
import type { EmailItem } from "../../types/emails";
import { emailsApi } from "../../services/api";
import { useWorkspace } from "../../hooks/useWorkspace";
import { EmailBodyViewer } from "./EmailBodyViewer";

interface EmailConversationProps {
  threadId: number;
  currentEmailId: number;
}

export const EmailConversation: React.FC<EmailConversationProps> = ({ threadId, currentEmailId }) => {
  const [expandedIds, setExpandedIds] = useState<Set<number>>(new Set());
  const { currentCompanyId } = useWorkspace();

  const { data: threadDetail, isLoading } = useQuery({
    queryKey: ["thread-detail", currentCompanyId, threadId],
    queryFn: () => emailsApi.getThread(threadId, currentCompanyId ?? undefined),
    staleTime: 60000,
  });

  const toggleExpand = (id: number) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="pt-4 border-t border-slate-100 space-y-2">
        <div className="h-4 w-32 bg-slate-100 rounded animate-pulse" />
        <div className="h-16 bg-slate-50 rounded-lg animate-pulse" />
      </div>
    );
  }

  const threadEmails = threadDetail?.emails || [];
  // Filter out messages or show conversation timeline
  if (threadEmails.length <= 1) {
    return null;
  }

  return (
    <div className="pt-4 border-t border-slate-100 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
          <MessageSquare className="h-3.5 w-3.5 text-indigo-600" />
          <span>Conversation Thread ({threadEmails.length} messages)</span>
        </div>
      </div>

      <div className="space-y-2">
        {threadEmails.map((item: EmailItem) => {
          const isCurrent = item.id === currentEmailId;
          const isExpanded = expandedIds.has(item.id) || isCurrent;

          return (
            <div
              key={item.id}
              className={`rounded-lg border text-xs transition-colors ${
                isCurrent
                  ? "bg-indigo-50/20 border-indigo-200"
                  : "bg-slate-50/80 border-slate-200"
              }`}
            >
              <div
                onClick={() => !isCurrent && toggleExpand(item.id)}
                className={`p-2.5 flex items-center justify-between cursor-pointer ${
                  isCurrent ? "cursor-default" : "hover:bg-slate-100/70"
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <span className="font-semibold text-slate-900 truncate">{item.sender}</span>
                  <span className="text-[11px] text-slate-400 truncate">
                    {new Date(item.sent_at || item.received_at || item.created_at).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                  {isCurrent && (
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-indigo-100 text-indigo-700">
                      Active
                    </span>
                  )}
                  {item.direction === "INCOMING" && (
                    <span className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-sky-50 text-sky-700 flex items-center gap-0.5">
                      <CornerDownLeft className="h-2.5 w-2.5" />
                      Reply
                    </span>
                  )}
                </div>

                {!isCurrent && (
                  <button type="button" className="text-slate-400 p-0.5">
                    {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                  </button>
                )}
              </div>

              {isExpanded && !isCurrent && (
                <div className="px-3 pb-3 pt-2 border-t border-slate-200/60">
                  <EmailBodyViewer
                    html={item.body_html}
                    text={item.body_text}
                    defaultMode={item.body_html ? "html" : "text"}
                    minHeight={80}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
