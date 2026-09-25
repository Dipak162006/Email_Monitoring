import React, { useState, useEffect, useRef } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Send,
  CheckCircle2,
  Paperclip,
  LayoutTemplate,
  PenTool,
  Loader2,
  AlertCircle,
  ChevronDown,
} from "lucide-react";
import {
  emailsApi,
  emailAccountsApi,
} from "../services/api";
import type {
  AuthorizedEmailAccount,
  AttachmentItem,
  EmailTemplateItem,
  EmailSignatureItem,
  EmailSendPayload,
  EmailDraftPayload,
} from "../types/emails";
import { RecipientInput } from "../components/compose/RecipientInput";
import { RichTextEditor } from "../components/compose/RichTextEditor";
import { AttachmentUploadList, type ComposeAttachment } from "../components/compose/AttachmentUploadList";
import { TemplateModal } from "../components/compose/TemplateModal";
import { SignatureModal } from "../components/compose/SignatureModal";

/**
 * Authoritative maximum attachment file size matching the backend configuration
 * (backend/app/core/config.py: MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024 = 25 MB).
 */
export const MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024;

export function isAttachmentError(msg: string | null): boolean {
  if (!msg) return false;
  const lower = msg.toLowerCase();
  return (
    lower.includes("attachment") ||
    lower.includes("maximum limit") ||
    lower.includes("exceeds") ||
    lower.includes("file size") ||
    lower.includes("upload")
  );
}

export function ComposePage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();

  const replyToId = searchParams.get("reply_to");
  const forwardId = searchParams.get("forward");
  const draftParamId = searchParams.get("draft_id") || searchParams.get("draft");

  // Threading / Reply State
  const [replyThreadId, setReplyThreadId] = useState<number | undefined>(undefined);
  const [replyInReplyTo, setReplyInReplyTo] = useState<string | undefined>(undefined);

  // Form State
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);
  const [toRecipients, setToRecipients] = useState<string[]>([]);
  const [ccRecipients, setCcRecipients] = useState<string[]>([]);
  const [bccRecipients, setBccRecipients] = useState<string[]>([]);
  const [showCc, setShowCc] = useState(false);
  const [showBcc, setShowBcc] = useState(false);
  const [subject, setSubject] = useState("");
  const [bodyHtml, setBodyHtml] = useState("");
  const [bodyText, setBodyText] = useState("");
  
  // Attachments: server attachments (saved to draft) + staged local files
  const [serverAttachments, setServerAttachments] = useState<AttachmentItem[]>([]);
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);

  const [draftId, setDraftId] = useState<number | null>(null);
  const [lastSavedTime, setLastSavedTime] = useState<string | null>(null);
  const [selectedSignature, setSelectedSignature] = useState<EmailSignatureItem | null>(null);

  // UI Modals & Loading
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [isSignatureModalOpen, setIsSignatureModalOpen] = useState(false);
  const [isUploadingAttachment, setIsUploadingAttachment] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Fetch Authorized Accounts
  const { data: accounts = [], isLoading: isLoadingAccounts } = useQuery({
    queryKey: ["authorized-accounts"],
    queryFn: () => emailAccountsApi.getAuthorizedAccounts(),
    staleTime: 60000,
  });

  // Set default account when accounts load
  useEffect(() => {
    if (accounts.length > 0 && selectedAccountId === null) {
      setSelectedAccountId(accounts[0].id);
    }
  }, [accounts, selectedAccountId]);

  // Handle Reply, Forward, or existing Draft pre-population
  useEffect(() => {
    const loadReferencedEmail = async () => {
      // 1. Existing Draft loading
      if (draftParamId) {
        try {
          const draftEmail = await emailsApi.getEmailById(Number(draftParamId));
          setDraftId(draftEmail.id);
          if (draftEmail.email_account_id) {
            setSelectedAccountId(draftEmail.email_account_id);
          }
          if (draftEmail.recipients) {
            setToRecipients(draftEmail.recipients);
          }
          if (draftEmail.cc && draftEmail.cc.length > 0) {
            setCcRecipients(draftEmail.cc);
            setShowCc(true);
          }
          if (draftEmail.bcc && draftEmail.bcc.length > 0) {
            setBccRecipients(draftEmail.bcc);
            setShowBcc(true);
          }
          if (draftEmail.subject) {
            setSubject(draftEmail.subject);
          }
          if (draftEmail.body_html) {
            setBodyHtml(draftEmail.body_html);
          }
          if (draftEmail.body_text) {
            setBodyText(draftEmail.body_text);
          }
          if (draftEmail.thread_id) {
            setReplyThreadId(draftEmail.thread_id);
          }
          if (draftEmail.in_reply_to) {
            setReplyInReplyTo(draftEmail.in_reply_to);
          }
          const atts = await emailsApi.getAttachments(draftEmail.id);
          if (atts?.attachments) {
            setServerAttachments(atts.attachments);
          }
          return;
        } catch (err) {
          console.error("Failed to load draft email:", err);
        }
      }

      // 2. Reply or Forward loading
      const refId = replyToId || forwardId;
      if (!refId) return;

      try {
        const sourceEmail = await emailsApi.getEmailById(Number(refId));
        if (sourceEmail.email_account_id) {
          setSelectedAccountId(sourceEmail.email_account_id);
        }

        if (replyToId) {
          if (sourceEmail.thread_id) {
            setReplyThreadId(sourceEmail.thread_id);
          }
          if (sourceEmail.message_id) {
            setReplyInReplyTo(sourceEmail.message_id);
          }

          setToRecipients([sourceEmail.sender]);
          setSubject(
            sourceEmail.subject.toLowerCase().startsWith("re:")
              ? sourceEmail.subject
              : `Re: ${sourceEmail.subject}`
          );
          const quotedBody = `<p></p><br/><blockquote style="border-left: 2px solid #cbd5e1; padding-left: 12px; margin-left: 0; color: #64748b;"><p>On ${new Date(
            sourceEmail.sent_at || sourceEmail.received_at || sourceEmail.created_at
          ).toLocaleString()}, ${sourceEmail.sender} wrote:</p>${sourceEmail.body_html || sourceEmail.body_text || ""}</blockquote>`;
          setBodyHtml(quotedBody);
        } else if (forwardId) {
          setSubject(
            sourceEmail.subject.toLowerCase().startsWith("fwd:")
              ? sourceEmail.subject
              : `Fwd: ${sourceEmail.subject}`
          );
          const forwardedBody = `<p></p><br/><blockquote style="border-left: 2px solid #cbd5e1; padding-left: 12px; margin-left: 0; color: #64748b;"><p>---------- Forwarded message ---------<br/>From: ${sourceEmail.sender}<br/>Subject: ${sourceEmail.subject}<br/>Date: ${new Date(
            sourceEmail.sent_at || sourceEmail.received_at || sourceEmail.created_at
          ).toLocaleString()}</p>${sourceEmail.body_html || sourceEmail.body_text || ""}</blockquote>`;
          setBodyHtml(forwardedBody);
        }
      } catch (err) {
        console.error("Failed to load referenced email:", err);
      }
    };

    loadReferencedEmail();
  }, [replyToId, forwardId, draftParamId]);

  const selectedAccount = accounts.find((a: AuthorizedEmailAccount) => a.id === selectedAccountId);

  // Combine server attachments and staged local files
  const combinedAttachments: ComposeAttachment[] = [
    ...serverAttachments.map((att) => ({
      id: att.id,
      file_name: att.file_name,
      file_size: att.file_size,
      content_type: att.content_type,
      isPending: false,
    })),
    ...stagedFiles.map((file, idx) => ({
      id: `staged-${idx}-${file.name}`,
      file_name: file.name,
      file_size: file.size,
      content_type: file.type || "application/octet-stream",
      isPending: true,
    })),
  ];

  // Save Draft Mutation
  const saveDraftMutation = useMutation({
    mutationFn: async (): Promise<number> => {
      if (!selectedAccountId) {
        throw new Error(
          "A sender email account is required to save drafts. Please select an authorized account from the 'From' selector."
        );
      }

      const payload: EmailDraftPayload = {
        email_account_id: selectedAccountId,
        to: toRecipients,
        cc: ccRecipients.length > 0 ? ccRecipients : undefined,
        bcc: bccRecipients.length > 0 ? bccRecipients : undefined,
        subject,
        body_text: bodyText || undefined,
        body_html: bodyHtml || undefined,
        thread_id: replyThreadId,
        in_reply_to: replyInReplyTo,
      };

      let activeDraftId = draftId;
      if (activeDraftId) {
        const updated = await emailsApi.updateDraft(activeDraftId, payload);
        activeDraftId = updated.id;
      } else {
        const created = await emailsApi.createDraft(payload);
        activeDraftId = created.id;
        setDraftId(created.id);
      }

      // If there are staged files, upload them now to the draft
      if (stagedFiles.length > 0) {
        setIsUploadingAttachment(true);
        const remaining = [...stagedFiles];
        try {
          while (remaining.length > 0) {
            const file = remaining[0];
            const uploaded = await emailsApi.uploadDraftAttachment(activeDraftId, file);
            setServerAttachments((prev) => [...prev, uploaded]);
            remaining.shift();
            setStagedFiles([...remaining]);
          }
        } catch (uploadErr) {
          remaining.shift();
          setStagedFiles([...remaining]);
          throw uploadErr;
        }
      }

      return activeDraftId;
    },
    onSuccess: () => {
      setLastSavedTime(new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));
      queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
      setErrorMessage(null);
    },
    onError: (err: Error) => {
      setErrorMessage(err.message || "Failed to save draft.");
    },
    onSettled: () => {
      setIsUploadingAttachment(false);
    },
  });

  // Send Mutation
  const sendMutation = useMutation({
    mutationFn: async () => {
      if (!selectedAccountId) {
        throw new Error(
          "A sender email account is required before sending. Please select an authorized account from the 'From' selector."
        );
      }
      if (toRecipients.length === 0) {
        throw new Error("Please provide at least one recipient in the 'To' field.");
      }
      if (!bodyText.trim() && !bodyHtml.trim()) {
        throw new Error("Please enter email body content before sending.");
      }

      // If we have staged files or existing server attachments, we must send via the draft workflow
      let activeDraftId = draftId;
      if (!activeDraftId && (stagedFiles.length > 0 || serverAttachments.length > 0)) {
        const created = await emailsApi.createDraft({
          email_account_id: selectedAccountId,
          to: toRecipients,
          cc: ccRecipients.length > 0 ? ccRecipients : undefined,
          bcc: bccRecipients.length > 0 ? bccRecipients : undefined,
          subject,
          body_text: bodyText,
          body_html: bodyHtml,
          thread_id: replyThreadId,
          in_reply_to: replyInReplyTo,
        });
        activeDraftId = created.id;
        setDraftId(created.id);
      }

      // Upload any staged files to the draft
      if (activeDraftId && stagedFiles.length > 0) {
        setIsUploadingAttachment(true);
        const remaining = [...stagedFiles];
        try {
          while (remaining.length > 0) {
            const file = remaining[0];
            const uploaded = await emailsApi.uploadDraftAttachment(activeDraftId, file);
            setServerAttachments((prev) => [...prev, uploaded]);
            remaining.shift();
            setStagedFiles([...remaining]);
          }
        } catch (uploadErr) {
          remaining.shift();
          setStagedFiles([...remaining]);
          throw uploadErr;
        }
      }

      // Transmit via draft if a draft exists
      if (activeDraftId) {
        await emailsApi.updateDraft(activeDraftId, {
          email_account_id: selectedAccountId,
          to: toRecipients,
          cc: ccRecipients.length > 0 ? ccRecipients : undefined,
          bcc: bccRecipients.length > 0 ? bccRecipients : undefined,
          subject,
          body_text: bodyText,
          body_html: bodyHtml,
          thread_id: replyThreadId,
          in_reply_to: replyInReplyTo,
        });
        return emailsApi.sendDraft(activeDraftId);
      }

      // Direct send when there are no attachments
      const payload: EmailSendPayload = {
        email_account_id: selectedAccountId,
        to: toRecipients,
        cc: ccRecipients.length > 0 ? ccRecipients : undefined,
        bcc: bccRecipients.length > 0 ? bccRecipients : undefined,
        subject,
        body_text: bodyText || undefined,
        body_html: bodyHtml || undefined,
        signature_id: selectedSignature ? selectedSignature.id : undefined,
        thread_id: replyThreadId,
        in_reply_to: replyInReplyTo,
      };

      return emailsApi.sendEmail(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["emails"] });
      queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
      navigate("/mailbox?folder=sent");
    },
    onError: (err: Error) => {
      setErrorMessage(err.message || "Failed to send email. Please check your recipient addresses and SMTP settings.");
    },
    onSettled: () => {
      setIsUploadingAttachment(false);
    },
  });

  // Handle Discard
  const handleDiscard = async () => {
    if (draftId) {
      try {
        await emailsApi.discardDraft(draftId);
      } catch (err) {
        console.error("Error discarding draft:", err);
      }
    }
    setStagedFiles([]);
    setServerAttachments([]);
    navigate("/mailbox");
  };

  // Handle Attachment Selection
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;

    const files = Array.from(fileList);

    // Clear previous attachment-related error when a new selection begins
    if (isAttachmentError(errorMessage)) {
      setErrorMessage(null);
    }

    const validFiles: File[] = [];
    const oversizedFiles: File[] = [];

    for (const file of files) {
      if (file.size > MAX_ATTACHMENT_SIZE_BYTES) {
        oversizedFiles.push(file);
      } else {
        validFiles.push(file);
      }
    }

    if (oversizedFiles.length > 0) {
      const names = oversizedFiles.map((f) => `"${f.name}"`).join(", ");
      setErrorMessage(
        `File ${names} exceeds the maximum attachment limit of 25 MB.`
      );
    }

    // Process valid files if any
    if (validFiles.length > 0) {
      try {
        if (draftId) {
          setIsUploadingAttachment(true);
          for (const file of validFiles) {
            const uploaded = await emailsApi.uploadDraftAttachment(draftId, file);
            setServerAttachments((prev) => [...prev, uploaded]);
          }
        } else {
          // Stage files locally until user saves or sends
          setStagedFiles((prev) => [...prev, ...validFiles]);
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to upload attachment.";
        setErrorMessage(msg);
      } finally {
        setIsUploadingAttachment(false);
      }
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // Handle Attachment Removal
  const handleRemoveAttachment = async (id: number | string) => {
    // Clear attachment error when an attachment is removed
    if (isAttachmentError(errorMessage)) {
      setErrorMessage(null);
    }

    if (typeof id === "string") {
      // Staged local file (e.g., staged-0-filename)
      const parts = id.split("-");
      const idx = parseInt(parts[1], 10);
      setStagedFiles((prev) => prev.filter((_, i) => i !== idx));
    } else {
      // Server attachment
      if (draftId) {
        try {
          await emailsApi.deleteDraftAttachment(draftId, id);
          setServerAttachments((prev) => prev.filter((a) => a.id !== id));
        } catch (err) {
          console.error("Failed to delete attachment:", err);
          setErrorMessage("Failed to remove attachment from server.");
        }
      }
    }
  };

  // Handle Template Insertion
  const handleSelectTemplate = (template: EmailTemplateItem) => {
    if (template.subject) {
      setSubject(template.subject);
    }
    if (template.body_html) {
      setBodyHtml(template.body_html);
      setBodyText(template.body_text || "");
    } else if (template.body_text) {
      setBodyHtml(`<p>${template.body_text.replace(/\n/g, "<br/>")}</p>`);
      setBodyText(template.body_text);
    } 
  };

  // Handle Signature Insertion
  const handleSelectSignature = (sig: EmailSignatureItem) => {
    setSelectedSignature(sig);
  };

  return (
    <div className="w-full max-w-5xl mx-auto space-y-4">
      {/* Top Action Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Back to Mailbox Button */}
        <Link
          to="/mailbox"
          className="inline-flex items-center gap-2 px-3 py-1.5 text-xs sm:text-sm font-medium text-slate-700 hover:text-slate-900 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to Mailbox</span>
        </Link>

        {/* Status and Action Buttons */}
        <div className="flex items-center gap-3">
          {lastSavedTime && (
            <span className="text-xs text-slate-500 font-medium flex items-center gap-1.5 mr-1">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              <span>Draft saved at {lastSavedTime}</span>
            </span>
          )}

          <button
            type="button"
            onClick={handleDiscard}
            className="text-slate-500 hover:text-rose-600 text-xs sm:text-sm font-medium transition-colors px-3 py-1.5 rounded-lg hover:bg-rose-50"
          >
            Discard
          </button>

          <button
            type="button"
            onClick={() => saveDraftMutation.mutate()}
            disabled={saveDraftMutation.isPending}
            className="border border-slate-300 text-slate-700 bg-white px-3.5 py-1.5 rounded-lg text-xs sm:text-sm font-medium hover:bg-slate-50 transition-colors shadow-2xs flex items-center gap-1.5 disabled:opacity-50"
          >
            {saveDraftMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            <span>Save Draft</span>
          </button>

          <button
            type="button"
            onClick={() => sendMutation.mutate()}
            disabled={sendMutation.isPending}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded-lg text-xs sm:text-sm font-medium flex items-center gap-2 shadow-xs transition-all disabled:opacity-50"
          >
            {sendMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                <span>Sending...</span>
              </>
            ) : (
              <>
                <Send className="h-4 w-4" />
                <span>Send Message</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error Notice */}
      {errorMessage && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-xl text-xs sm:text-sm flex items-start justify-between gap-3 shadow-2xs">
          <div className="flex items-center gap-2">
            <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="text-rose-400 hover:text-rose-700 font-bold"
          >
            ✕
          </button>
        </div>
      )}

      {/* Main Compose Card Container */}
      <div className="bg-white border border-slate-200 rounded-xl shadow-xs overflow-hidden">
        {/* Card Header */}
        <div className="px-6 sm:px-8 pt-6 pb-4 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-lg sm:text-xl font-semibold text-slate-900">New Message</h1>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
              {draftId ? "Draft Saved" : "New"}
            </span>
          </div>
        </div>

        {/* Envelope Metadata Fields */}
        <div className="px-6 sm:px-8 py-2 divide-y divide-slate-100">
          {/* From Row */}
          <div className="py-3 flex items-center text-xs sm:text-sm">
            <span className="w-16 text-slate-500 font-medium select-none">From</span>
            <div className="relative flex items-center flex-1">
              {isLoadingAccounts ? (
                <div className="h-8 w-48 bg-slate-100 rounded-lg animate-pulse" />
              ) : accounts.length === 0 ? (
                <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
                  <AlertCircle className="h-3.5 w-3.5 text-amber-600 shrink-0" />
                  <span>No authorized sender email accounts found for this company.</span>
                </div>
              ) : (
                <div className="relative flex items-center">
                  <select
                    value={selectedAccountId ?? ""}
                    onChange={(e) => setSelectedAccountId(Number(e.target.value))}
                    className="appearance-none bg-slate-50 hover:bg-slate-100 rounded-lg text-slate-900 text-xs sm:text-sm font-medium py-1.5 pl-7 pr-8 border border-slate-200 shadow-2xs outline-none focus:ring-1 focus:ring-indigo-600 focus:border-indigo-600 cursor-pointer transition-colors"
                  >
                    {accounts.map((acc: AuthorizedEmailAccount) => (
                      <option key={acc.id} value={acc.id}>
                        {acc.name} &lt;{acc.email_address}&gt; ({acc.provider})
                      </option>
                    ))}
                  </select>
                  <span className="h-2 w-2 rounded-full bg-emerald-500 absolute left-2.5 pointer-events-none" />
                  <ChevronDown className="h-3.5 w-3.5 text-slate-400 absolute right-2.5 pointer-events-none" />
                </div>
              )}

              {selectedAccount && (
                <span className="text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded ml-2 hidden sm:inline-block">
                  Verified
                </span>
              )}
            </div>
          </div>

          {/* To Row */}
          <RecipientInput
            label="To"
            recipients={toRecipients}
            onChange={setToRecipients}
            placeholder="Add recipients (press Enter)..."
            rightAction={
              <button
                type="button"
                onClick={() => {
                  setShowCc((prev) => !prev);
                  setShowBcc((prev) => !prev);
                }}
                className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold cursor-pointer select-none"
              >
                Cc / Bcc
              </button>
            }
          />

          {/* Cc Row */}
          {(showCc || ccRecipients.length > 0) && (
            <RecipientInput
              label="Cc"
              recipients={ccRecipients}
              onChange={setCcRecipients}
              placeholder="Add CC recipients..."
            />
          )}

          {/* Bcc Row */}
          {(showBcc || bccRecipients.length > 0) && (
            <RecipientInput
              label="Bcc"
              recipients={bccRecipients}
              onChange={setBccRecipients}
              placeholder="Add BCC recipients..."
            />
          )}

          {/* Subject Row */}
          <div className="py-3 flex items-center text-xs sm:text-sm">
            <span className="w-16 text-slate-500 font-medium select-none">Subject</span>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Enter email subject"
              className="flex-1 text-slate-900 font-medium text-sm sm:text-base outline-none placeholder-slate-400 py-0.5 bg-transparent"
            />
          </div>
        </div>

        {/* Rich Text Editor & Writing Area */}
        <div className="p-6 sm:p-8 space-y-4">
          <RichTextEditor
            initialHtml={bodyHtml}
            onChange={(html, text) => {
              setBodyHtml(html);
              setBodyText(text);
            }}
            placeholder="Write your email message here..."
          />

          {/* Attachment Upload List (server attachments + staged files) */}
          <AttachmentUploadList
            attachments={combinedAttachments}
            onRemove={handleRemoveAttachment}
            isUploading={isUploadingAttachment}
          />

          {/* Signature Preview if selected */}
          {selectedSignature && (
            <div className="pt-4 border-t border-dashed border-slate-200 text-xs sm:text-sm">
              <div className="flex items-start gap-3 text-slate-600">
                <div className="w-8 h-8 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold text-xs border border-indigo-100 shrink-0">
                  {selectedSignature.name.slice(0, 2).toUpperCase()}
                </div>
                <div className="flex flex-col">
                  <span className="font-semibold text-slate-900">{selectedSignature.name}</span>
                  <span className="text-xs text-slate-500">
                    {selectedSignature.body_text || "Custom Signature"}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Bottom Card Action Bar */}
        <div className="bg-slate-50/80 border-t border-slate-200 px-6 sm:px-8 py-4 flex flex-wrap justify-between items-center gap-4">
          {/* Hidden File Input for Attachments */}
          <input
            ref={fileInputRef}
            type="file"
            multiple
            onChange={handleFileSelect}
            className="hidden"
          />

          {/* Left Quick Tools */}
          <div className="flex items-center gap-2 flex-wrap">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploadingAttachment}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
            >
              <Paperclip className="h-3.5 w-3.5 text-slate-500" />
              <span>Attach Files</span>
            </button>

            <button
              type="button"
              onClick={() => setIsTemplateModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer"
            >
              <LayoutTemplate className="h-3.5 w-3.5 text-slate-500" />
              <span>Insert Template</span>
            </button>

            <button
              type="button"
              onClick={() => setIsSignatureModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer"
            >
              <PenTool className="h-3.5 w-3.5 text-slate-500" />
              <span>Insert Signature</span>
            </button>
          </div>

          {/* Right Actions */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleDiscard}
              className="text-slate-500 hover:text-rose-600 text-xs sm:text-sm font-medium transition-colors px-3 py-1.5 rounded-lg hover:bg-rose-50"
            >
              Discard
            </button>

            <button
              type="button"
              onClick={() => saveDraftMutation.mutate()}
              disabled={saveDraftMutation.isPending}
              className="border border-slate-300 text-slate-700 bg-white px-4 py-2 rounded-lg text-xs sm:text-sm font-medium hover:bg-slate-50 transition-colors shadow-2xs flex items-center gap-1.5 disabled:opacity-50"
            >
              {saveDraftMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              <span>Save as Draft</span>
            </button>

            <button
              type="button"
              onClick={() => sendMutation.mutate()}
              disabled={sendMutation.isPending}
              className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-lg text-xs sm:text-sm font-medium flex items-center gap-2 shadow-xs transition-all disabled:opacity-50"
            >
              {sendMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  <span>Sending...</span>
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  <span>Send Message</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Modals */}
      <TemplateModal
        isOpen={isTemplateModalOpen}
        onClose={() => setIsTemplateModalOpen(false)}
        onSelectTemplate={handleSelectTemplate}
        hasExistingContent={Boolean(subject.trim() || bodyText.trim())}
      />

      <SignatureModal
        isOpen={isSignatureModalOpen}
        onClose={() => setIsSignatureModalOpen(false)}
        onSelectSignature={handleSelectSignature}
      />
    </div>
  );
}
