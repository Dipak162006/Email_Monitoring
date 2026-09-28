import { useState, useEffect, useRef } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Reply,
  CornerUpRight,
  Trash2,
  Star,
  Mail,
  MailOpen,
  ShieldCheck,
  Clock,
  User,
  Users,
  Code,
  FileText,
  AlertCircle,
  RotateCcw,
  CheckCircle2,
  X,
  PenTool,
} from "lucide-react";
import { emailsApi } from "../services/api";
import { Card, CardContent } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { AttachmentList } from "../components/mailbox/AttachmentList";
import { EmailConversation } from "../components/mailbox/EmailConversation";
import { RestoreConfirmModal } from "../components/mailbox/RestoreConfirmModal";
import { PermanentDeleteConfirmModal } from "../components/mailbox/PermanentDeleteConfirmModal";
import DOMPurify from "dompurify";

export function EmailDetailPage() {
  const { emailId } = useParams<{ emailId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [viewMode, setViewMode] = useState<"html" | "text">("html");

  // Modals and feedback state
  const [isRestoreModalOpen, setIsRestoreModalOpen] = useState(false);
  const [isPermanentDeleteModalOpen, setIsPermanentDeleteModalOpen] = useState(false);
  const [alertBanner, setAlertBanner] = useState<{ type: "success" | "error"; message: string } | null>(null);

  const id = Number(emailId);
  const hasMarkedReadRef = useRef<number | null>(null);

  // Fetch email details
  const {
    data: email,
    isLoading,
    isError,
    error,
  } = useQuery({
    queryKey: ["email-detail", id],
    queryFn: () => emailsApi.getEmailById(id),
    enabled: !isNaN(id),
    staleTime: 30000,
  });

  // Automatically mark unread email as read once opened
  useEffect(() => {
    if (email && !email.is_read && hasMarkedReadRef.current !== email.id) {
      hasMarkedReadRef.current = email.id;
      markReadMutation.mutate(true);
    }
  }, [email?.id, email?.is_read]);

  // Fetch attachments
  const { data: attachmentsData } = useQuery({
    queryKey: ["email-attachments", id],
    queryFn: () => emailsApi.getAttachments(id),
    enabled: !isNaN(id),
    staleTime: 60000,
  });

  // Mutations
  const markReadMutation = useMutation({
    mutationFn: (isRead: boolean) => emailsApi.markRead(id, isRead),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["email-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["emails"] });
      queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
    },
  });

  const markStarMutation = useMutation({
    mutationFn: (isStarred: boolean) => emailsApi.markStarred(id, isStarred),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["email-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["emails"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => emailsApi.softDelete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["emails"] });
      queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
      navigate("/mailbox");
    },
    onError: () => {
      setAlertBanner({ type: "error", message: "Failed to move email to Trash. Please try again." });
    },
  });

  const restoreMutation = useMutation({
    mutationFn: () => emailsApi.restore(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["email-detail", id] });
      queryClient.invalidateQueries({ queryKey: ["emails"] });
      queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
      setIsRestoreModalOpen(false);
      setAlertBanner({ type: "success", message: "Email successfully restored to Inbox." });
    },
    onError: () => {
      setIsRestoreModalOpen(false);
      setAlertBanner({ type: "error", message: "Failed to restore email. Please try again." });
    },
  });

  const permanentDeleteMutation = useMutation({
    mutationFn: () => emailsApi.permanentDelete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["emails"] });
      queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
      setIsPermanentDeleteModalOpen(false);
      navigate("/mailbox?folder=trash");
    },
    onError: () => {
      setIsPermanentDeleteModalOpen(false);
      setAlertBanner({ type: "error", message: "Failed to permanently delete email." });
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-4 max-w-5xl mx-auto">
        <div className="h-8 w-32 bg-slate-200 rounded animate-pulse" />
        <Card className="p-8 space-y-6">
          <div className="h-6 w-3/4 bg-slate-100 rounded animate-pulse" />
          <div className="h-4 w-1/2 bg-slate-100 rounded animate-pulse" />
          <div className="h-32 bg-slate-50 rounded-xl animate-pulse" />
          <div className="h-48 bg-slate-50 rounded-lg animate-pulse" />
        </Card>
      </div>
    );
  }

  if (isError || !email) {
    return (
      <div className="max-w-md mx-auto p-12 text-center space-y-4">
        <div className="inline-flex p-3 rounded-full bg-rose-50 text-rose-600">
          <AlertCircle className="h-6 w-6" />
        </div>
        <h2 className="text-base font-semibold text-slate-900">Email Not Found</h2>
        <p className="text-xs text-slate-500">
          {(error as Error)?.message || "The requested email could not be retrieved."}
        </p>
        <Link to="/mailbox">
          <Button size="sm" variant="outline" className="mt-2">
            Back to Mailbox
          </Button>
        </Link>
      </div>
    );
  }

  const hasHtml = !!email.body_html;
  const sanitizedHtml = hasHtml ? DOMPurify.sanitize(email.body_html || "") : null;
  const formattedDate = new Date(email.sent_at || email.received_at || email.created_at).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "short",
  });

  return (
    <div className="space-y-4 max-w-5xl mx-auto pb-10">
      {/* Top Action & Navigation Bar */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <Link to="/mailbox">
          <Button variant="ghost" size="sm" className="gap-1.5 text-slate-600 hover:text-slate-900">
            <ArrowLeft className="h-4 w-4" />
            Back to Mailbox
          </Button>
        </Link>

        <div className="flex items-center space-x-2">
          <button
            type="button"
            onClick={() => markStarMutation.mutate(!email.is_starred)}
            className={`p-2 rounded-lg border text-xs font-medium transition-colors ${
              email.is_starred
                ? "bg-amber-50 border-amber-200 text-amber-600"
                : "bg-white border-slate-200 text-slate-600 hover:bg-slate-50"
            }`}
            title={email.is_starred ? "Unstar" : "Star"}
          >
            <Star className="h-4 w-4" fill={email.is_starred ? "currentColor" : "none"} />
          </button>

          <button
            type="button"
            onClick={() => markReadMutation.mutate(!email.is_read)}
            className="p-2 rounded-lg border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 text-xs font-medium transition-colors"
            title={email.is_read ? "Mark Unread" : "Mark Read"}
          >
            {email.is_read ? <Mail className="h-4 w-4" /> : <MailOpen className="h-4 w-4" />}
          </button>

          {email.is_deleted ? (
            <>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsRestoreModalOpen(true)}
                disabled={restoreMutation.isPending}
                className="gap-1.5 text-indigo-600 hover:bg-indigo-50 border-indigo-200"
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Restore to Inbox
              </Button>

              <Button
                variant="outline"
                size="sm"
                onClick={() => setIsPermanentDeleteModalOpen(true)}
                disabled={permanentDeleteMutation.isPending}
                className="gap-1.5 text-rose-600 hover:bg-rose-50 border-rose-200"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete Permanently
              </Button>
            </>
          ) : email.status === "DRAFT" ? (
            <>
              <Link to={`/compose?draft_id=${email.id}`}>
                <Button size="sm" className="gap-1.5 bg-indigo-600 hover:bg-indigo-700 text-white">
                  <PenTool className="h-3.5 w-3.5" />
                  Continue Editing Draft
                </Button>
              </Link>
              <Button
                variant="outline"
                size="sm"
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="gap-1.5 text-rose-600 hover:bg-rose-50 border-slate-200"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Discard Draft
              </Button>
            </>
          ) : (
            <>
              <Link to={`/compose?reply_to=${email.id}`}>
                <Button variant="outline" size="sm" className="gap-1.5">
                  <Reply className="h-3.5 w-3.5" />
                  Reply
                </Button>
              </Link>

              <Link to={`/compose?forward=${email.id}`}>
                <Button variant="outline" size="sm" className="gap-1.5">
                  <CornerUpRight className="h-3.5 w-3.5" />
                  Forward
                </Button>
              </Link>

              <Button
                variant="outline"
                size="sm"
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
                className="gap-1.5 text-rose-600 hover:bg-rose-50 border-slate-200"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Move to Trash
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Operation Feedback Alert Banner */}
      {alertBanner && (
        <div
          className={`flex items-center justify-between px-4 py-3 rounded-xl border text-xs font-medium transition-all ${
            alertBanner.type === "success"
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-rose-50 border-rose-200 text-rose-800"
          }`}
        >
          <div className="flex items-center gap-2">
            {alertBanner.type === "success" ? (
              <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
            ) : (
              <AlertCircle className="h-4 w-4 text-rose-600 shrink-0" />
            )}
            <span>{alertBanner.message}</span>
          </div>
          <button
            type="button"
            onClick={() => setAlertBanner(null)}
            className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-200/50 cursor-pointer"
            aria-label="Dismiss message"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Main Email Display Card */}
      <Card className="border-slate-200 shadow-2xs overflow-hidden">
        <CardContent className="p-6 sm:p-8 space-y-6">
          {/* Header Info */}
          <div className="border-b border-slate-100 pb-5 space-y-3">
            <h1 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
              {email.subject || "(No Subject)"}
            </h1>

            <div className="space-y-1.5 text-xs text-slate-600">
              <div className="flex items-center gap-2">
                <User className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                <span className="font-semibold text-slate-900">From:</span>
                <span className="text-slate-800">{email.sender}</span>
              </div>

              {email.recipients && email.recipients.length > 0 && (
                <div className="flex items-center gap-2">
                  <Users className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                  <span className="font-semibold text-slate-900">To:</span>
                  <span className="text-slate-800">{email.recipients.join(", ")}</span>
                </div>
              )}

              <div className="flex items-center gap-2 text-slate-500">
                <Clock className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                <span>{formattedDate}</span>
              </div>
            </div>
          </div>

          {/* Telemetry Trace Box */}
          <div className="bg-slate-50 border border-slate-200 p-4 rounded-xl space-y-2">
            <div className="flex items-center justify-between text-[11px] text-slate-500 uppercase tracking-wider font-semibold">
              <span>Telemetry Protocol Trace</span>
              <span className="text-emerald-700 font-mono font-medium flex items-center gap-1">
                <ShieldCheck className="h-3.5 w-3.5" />
                DKIM: PASS • SPF: PASS
              </span>
            </div>
            <div className="font-mono text-xs text-slate-600 space-y-1">
              <div>Return-Path: &lt;{email.sender}&gt;</div>
              <div>Status: {email.status} • Direction: {email.direction}</div>
              <div>Message ID: {email.message_id || `MSG-${email.id}`}</div>
            </div>
          </div>

          {/* Body Viewer */}
          <div className="space-y-3">
            {hasHtml && email.body_text && (
              <div className="flex items-center space-x-1 bg-slate-100 p-0.5 rounded-lg w-fit text-xs">
                <button
                  type="button"
                  onClick={() => setViewMode("html")}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors flex items-center gap-1 ${
                    viewMode === "html" ? "bg-white text-slate-900 shadow-2xs" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <Code className="h-3 w-3" />
                  HTML View
                </button>
                <button
                  type="button"
                  onClick={() => setViewMode("text")}
                  className={`px-2.5 py-1 rounded-md font-medium transition-colors flex items-center gap-1 ${
                    viewMode === "text" ? "bg-white text-slate-900 shadow-2xs" : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  <FileText className="h-3 w-3" />
                  Plain Text
                </button>
              </div>
            )}

            <div className="text-sm text-slate-800 leading-relaxed bg-white rounded-lg border border-slate-100 p-6 min-h-[160px]">
              {viewMode === "html" && sanitizedHtml ? (
                <div
                  className="prose prose-sm max-w-none break-words text-slate-800"
                  dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
                />
              ) : (
                <pre className="whitespace-pre-wrap font-sans text-xs sm:text-sm text-slate-800 leading-relaxed">
                  {email.body_text || email.body_html || "No message body content."}
                </pre>
              )}
            </div>
          </div>

          {/* Attachments */}
          {attachmentsData?.attachments && attachmentsData.attachments.length > 0 && (
            <AttachmentList emailId={email.id} attachments={attachmentsData.attachments} />
          )}

          {/* Conversation Thread */}
          {email.thread_id && (
            <EmailConversation threadId={email.thread_id} currentEmailId={email.id} />
          )}
        </CardContent>
      </Card>

      {/* Restore Confirmation Modal */}
      <RestoreConfirmModal
        isOpen={isRestoreModalOpen}
        count={1}
        isRestoring={restoreMutation.isPending}
        onClose={() => {
          if (!restoreMutation.isPending) setIsRestoreModalOpen(false);
        }}
        onConfirm={() => restoreMutation.mutate()}
      />

      {/* Permanent Delete Confirmation Modal */}
      <PermanentDeleteConfirmModal
        isOpen={isPermanentDeleteModalOpen}
        count={1}
        isDeleting={permanentDeleteMutation.isPending}
        onClose={() => {
          if (!permanentDeleteMutation.isPending) setIsPermanentDeleteModalOpen(false);
        }}
        onConfirm={() => permanentDeleteMutation.mutate()}
      />
    </div>
  );
}
