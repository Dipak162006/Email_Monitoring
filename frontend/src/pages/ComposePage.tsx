import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useWorkspace } from "../hooks/useWorkspace";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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
  signaturesApi,
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

  // Attachments: server attachments persisted directly to the active draft
  const [serverAttachments, setServerAttachments] = useState<AttachmentItem[]>([]);

  // Draft & Autosave State
  const [draftId, setDraftId] = useState<number | null>(null);
  const draftIdRef = useRef<number | null>(null);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [lastSavedTime, setLastSavedTime] = useState<string | null>(null);
  const [selectedSignature, setSelectedSignature] = useState<EmailSignatureItem | null>(null);

  // Concurrency & Lifecycle Refs
  const isSavingRef = useRef(false);
  const pendingSaveRef = useRef(false);
  const isSendingRef = useRef(false);
  const isDiscardingRef = useRef(false);
  const hasUnsavedChangesRef = useRef(false);
  const autosaveTimerRef = useRef<NodeJS.Timeout | null>(null);

  // UI Modals & Loading
  const [isSending, setIsSending] = useState(false);
  const [isDiscarding, setIsDiscarding] = useState(false);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [isSignatureModalOpen, setIsSignatureModalOpen] = useState(false);
  const [isUploadingAttachment, setIsUploadingAttachment] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { currentCompanyId } = useWorkspace();

  // Fetch Authorized Accounts
  const { data: rawAccounts = [], isLoading: isLoadingAccounts } = useQuery({
    queryKey: ["authorized-accounts"],
    queryFn: () => emailAccountsApi.getAuthorizedAccounts(),
    staleTime: 60000,
  });

  // Filter accounts strictly to active workspace
  const accounts = useMemo(() => {
    if (!currentCompanyId) return rawAccounts;
    return rawAccounts.filter((acc) => acc.company_id === currentCompanyId);
  }, [rawAccounts, currentCompanyId]);

  // Fetch default signature for selected account
  const { data: defaultSignature } = useQuery({
    queryKey: ["default-signature", selectedAccountId],
    queryFn: () => (selectedAccountId ? signaturesApi.getDefaultSignature(selectedAccountId) : null),
    enabled: Boolean(selectedAccountId),
    staleTime: 30000,
  });

  // Effective signature is explicit selectedSignature if chosen, otherwise account defaultSignature
  const effectiveSignature = selectedSignature || defaultSignature || null;

  // Keep draftIdRef synchronized with draftId state
  useEffect(() => {
    draftIdRef.current = draftId;
  }, [draftId]);

  // Set default account when accounts load or change, resetting if account belongs to different company
  useEffect(() => {
    if (accounts.length > 0) {
      const isValid = accounts.some((a) => a.id === selectedAccountId);
      if (!isValid) {
        setSelectedAccountId(accounts[0].id);
      }
    } else {
      setSelectedAccountId(null);
    }
  }, [accounts, selectedAccountId]);

  // Keep latest state ref up to date for reliable autosave reads
  const latestStateRef = useRef({
    selectedAccountId,
    toRecipients,
    ccRecipients,
    bccRecipients,
    subject,
    bodyHtml,
    bodyText,
    replyThreadId,
    replyInReplyTo,
    selectedSignature,
    serverAttachments,
  });

  useEffect(() => {
    latestStateRef.current = {
      selectedAccountId,
      toRecipients,
      ccRecipients,
      bccRecipients,
      subject,
      bodyHtml,
      bodyText,
      replyThreadId,
      replyInReplyTo,
      selectedSignature,
      serverAttachments,
    };
  }, [
    selectedAccountId,
    toRecipients,
    ccRecipients,
    bccRecipients,
    subject,
    bodyHtml,
    bodyText,
    replyThreadId,
    replyInReplyTo,
    selectedSignature,
    serverAttachments,
  ]);

  // Check if there is meaningful content to warrant creating or updating a draft
  const hasMeaningfulContent = useCallback(() => {
    const s = latestStateRef.current;
    return (
      s.toRecipients.length > 0 ||
      s.ccRecipients.length > 0 ||
      s.bccRecipients.length > 0 ||
      s.subject.trim().length > 0 ||
      s.bodyText.trim().length > 0 ||
      (s.bodyHtml.trim().length > 0 && s.bodyHtml !== "<p></p>" && s.bodyHtml !== "<p><br></p>") ||
      s.serverAttachments.length > 0 ||
      s.selectedSignature !== null
    );
  }, []);

  // Handle Reply, Forward, or existing Draft pre-population
  useEffect(() => {
    const loadReferencedEmail = async () => {
      // 1. Existing Draft loading
      if (draftParamId) {
        try {
          const draftEmail = await emailsApi.getEmailById(Number(draftParamId));
          setDraftId(draftEmail.id);
          draftIdRef.current = draftEmail.id;
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
          const saveDate = draftEmail.updated_at || draftEmail.created_at;
          if (saveDate) {
            setLastSavedTime(
              new Date(saveDate).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
            );
            setSaveStatus("saved");
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

  // Core save routine with race-condition protection and serialization
  const performSave = useCallback(async (): Promise<number | null> => {
    if (isSendingRef.current || isDiscardingRef.current) return null;
    const cur = latestStateRef.current;
    if (!cur.selectedAccountId) return null;
    if (!hasMeaningfulContent()) return null;

    // If another save is currently in-flight, mark pending and return current ID
    if (isSavingRef.current) {
      pendingSaveRef.current = true;
      return draftIdRef.current;
    }

    isSavingRef.current = true;
    setSaveStatus("saving");

    try {
      const state = latestStateRef.current;
      const payload: EmailDraftPayload = {
        email_account_id: state.selectedAccountId!,
        to: state.toRecipients,
        cc: state.ccRecipients.length > 0 ? state.ccRecipients : undefined,
        bcc: state.bccRecipients.length > 0 ? state.bccRecipients : undefined,
        subject: state.subject,
        body_text: state.bodyText || undefined,
        body_html: state.bodyHtml || undefined,
        signature_id: state.selectedSignature ? state.selectedSignature.id : undefined,
        thread_id: state.replyThreadId,
        in_reply_to: state.replyInReplyTo,
      };

      let activeId = draftIdRef.current;
      if (activeId) {
        const updated = await emailsApi.updateDraft(activeId, payload);
        activeId = updated.id;
      } else {
        const created = await emailsApi.createDraft(payload);
        activeId = created.id;
        draftIdRef.current = created.id;
        setDraftId(created.id);
      }

      const timeStr = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
      setLastSavedTime(timeStr);
      setSaveStatus("saved");
      hasUnsavedChangesRef.current = false;
      queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
      return activeId;
    } catch (err: unknown) {
      console.error("Autosave draft error:", err);
      setSaveStatus("error");
      return null;
    } finally {
      isSavingRef.current = false;
      // If changes occurred during the in-flight request, process the pending save immediately
      if (pendingSaveRef.current && !isSendingRef.current && !isDiscardingRef.current) {
        pendingSaveRef.current = false;
        performSave();
      }
    }
  }, [hasMeaningfulContent, queryClient]);

  // Debounced autosave trigger (900ms delay)
  const triggerAutosave = useCallback(() => {
    if (isSendingRef.current || isDiscardingRef.current) return;
    hasUnsavedChangesRef.current = true;

    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current);
    }

    autosaveTimerRef.current = setTimeout(() => {
      if (!isSendingRef.current && !isDiscardingRef.current) {
        performSave();
      }
    }, 900);
  }, [performSave]);

  // Input Handlers with automatic autosave triggers
  const handleToRecipientsChange = (recipients: string[]) => {
    setToRecipients(recipients);
    latestStateRef.current.toRecipients = recipients;
    triggerAutosave();
  };

  const handleCcRecipientsChange = (recipients: string[]) => {
    setCcRecipients(recipients);
    latestStateRef.current.ccRecipients = recipients;
    triggerAutosave();
  };

  const handleBccRecipientsChange = (recipients: string[]) => {
    setBccRecipients(recipients);
    latestStateRef.current.bccRecipients = recipients;
    triggerAutosave();
  };

  const handleSubjectChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSubject(val);
    latestStateRef.current.subject = val;
    triggerAutosave();
  };

  const handleBodyChange = (html: string, text: string) => {
    setBodyHtml(html);
    setBodyText(text);
    latestStateRef.current.bodyHtml = html;
    latestStateRef.current.bodyText = text;
    triggerAutosave();
  };

  const handleAccountChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const accId = Number(e.target.value);
    setSelectedAccountId(accId);
    latestStateRef.current.selectedAccountId = accId;
    if (selectedSignature && selectedSignature.email_account_id !== accId) {
      setSelectedSignature(null);
      latestStateRef.current.selectedSignature = null;
    }
    triggerAutosave();
  };

  const handleSelectTemplate = (template: EmailTemplateItem) => {
    if (!template.is_active) {
      setErrorMessage("Cannot apply an inactive email template.");
      queryClient.invalidateQueries({ queryKey: ["templates"], refetchType: "all" });
      return;
    }
    if (template.subject) {
      setSubject(template.subject);
      latestStateRef.current.subject = template.subject;
    }
    if (template.body_html) {
      setBodyHtml(template.body_html);
      const cleanHtmlForText = template.body_html
        .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, " ")
        .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, " ");
      const textFallback =
        template.body_text ||
        cleanHtmlForText.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      setBodyText(textFallback);
      latestStateRef.current.bodyHtml = template.body_html;
      latestStateRef.current.bodyText = textFallback;
    } else if (template.body_text) {
      const html = `<p>${template.body_text.replace(/\n/g, "<br/>")}</p>`;
      setBodyHtml(html);
      setBodyText(template.body_text);
      latestStateRef.current.bodyHtml = html;
      latestStateRef.current.bodyText = template.body_text;
    }
    triggerAutosave();
  };

  const handleSelectSignature = (sig: EmailSignatureItem) => {
    setSelectedSignature(sig);
    latestStateRef.current.selectedSignature = sig;
    triggerAutosave();
  };

  // Handle Attachment Selection
  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;

    const files = Array.from(fileList);

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
      setErrorMessage(`File ${names} exceeds the maximum attachment limit of 25 MB.`);
    }

    if (validFiles.length > 0) {
      if (!selectedAccountId) {
        setErrorMessage("Please select an authorized sender account before attaching files.");
        return;
      }

      try {
        setIsUploadingAttachment(true);
        setSaveStatus("saving");

        // Ensure draft exists prior to uploading attachment
        let activeDraftId = draftIdRef.current;
        if (!activeDraftId) {
          const payload: EmailDraftPayload = {
            email_account_id: selectedAccountId,
            to: toRecipients,
            cc: ccRecipients.length > 0 ? ccRecipients : undefined,
            bcc: bccRecipients.length > 0 ? bccRecipients : undefined,
            subject,
            body_text: bodyText || undefined,
            body_html: bodyHtml || undefined,
            signature_id: latestStateRef.current.selectedSignature ? latestStateRef.current.selectedSignature.id : undefined,
            thread_id: replyThreadId,
            in_reply_to: replyInReplyTo,
          };
          const created = await emailsApi.createDraft(payload);
          activeDraftId = created.id;
          draftIdRef.current = created.id;
          setDraftId(created.id);
        }

        // Upload attachments directly to the server draft
        for (const file of validFiles) {
          const uploaded = await emailsApi.uploadDraftAttachment(activeDraftId, file);
          setServerAttachments((prev) => [...prev, uploaded]);
        }

        const timeStr = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
        setLastSavedTime(timeStr);
        setSaveStatus("saved");
        hasUnsavedChangesRef.current = false;
        queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to upload attachment.";
        setErrorMessage(msg);
        setSaveStatus("error");
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
    if (isAttachmentError(errorMessage)) {
      setErrorMessage(null);
    }

    const activeDraftId = draftIdRef.current;
    if (activeDraftId && typeof id === "number") {
      try {
        await emailsApi.deleteDraftAttachment(activeDraftId, id);
        setServerAttachments((prev) => prev.filter((a) => a.id !== id));
        queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
      } catch (err) {
        console.error("Failed to delete attachment:", err);
        setErrorMessage("Failed to remove attachment from server.");
      }
    } else {
      setServerAttachments((prev) => prev.filter((a) => a.id !== id));
    }
  };

  // Discard Handler
  const handleDiscard = async () => {
    isDiscardingRef.current = true;
    setIsDiscarding(true);

    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }
    pendingSaveRef.current = false;

    const activeDraftId = draftIdRef.current;
    if (activeDraftId) {
      try {
        await emailsApi.discardDraft(activeDraftId);
      } catch (err) {
        console.error("Error discarding draft:", err);
      }
    }

    setServerAttachments([]);
    queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
    queryClient.invalidateQueries({ queryKey: ["emails"] });
    navigate("/mailbox");
  };

  // Back Navigation Handler: saves any pending meaningful changes before leaving
  const handleBackToMailbox = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (isDiscardingRef.current || isSendingRef.current) {
      navigate("/mailbox");
      return;
    }

    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }

    if (hasUnsavedChangesRef.current && hasMeaningfulContent() && selectedAccountId) {
      try {
        await performSave();
      } catch (err) {
        console.error("Failed to save draft on exit:", err);
      }
    }
    navigate("/mailbox");
  };

  // Send Message Handler
  const handleSend = async () => {
    if (!selectedAccountId) {
      setErrorMessage(
        "A sender email account is required before sending. Please select an authorized account from the 'From' selector."
      );
      return;
    }
    if (toRecipients.length === 0) {
      setErrorMessage("Please provide at least one recipient in the 'To' field.");
      return;
    }
    if (!bodyText.trim() && !bodyHtml.trim()) {
      setErrorMessage("Please enter email body content before sending.");
      return;
    }

    // 1. Mark as sending to stop autosaves
    isSendingRef.current = true;
    setIsSending(true);
    if (autosaveTimerRef.current) {
      clearTimeout(autosaveTimerRef.current);
      autosaveTimerRef.current = null;
    }
    pendingSaveRef.current = false;

    // 2. Wait for any in-flight autosave to settle
    while (isSavingRef.current) {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }

    try {
      const cur = latestStateRef.current;
      const activeDraftId = draftIdRef.current;

      // Case B: Draft exists
      if (activeDraftId) {
        // Persist latest state to the draft before sending
        await emailsApi.updateDraft(activeDraftId, {
          email_account_id: cur.selectedAccountId!,
          to: cur.toRecipients,
          cc: cur.ccRecipients.length > 0 ? cur.ccRecipients : undefined,
          bcc: cur.bccRecipients.length > 0 ? cur.bccRecipients : undefined,
          subject: cur.subject,
          body_text: cur.bodyText || undefined,
          body_html: cur.bodyHtml || undefined,
          signature_id: cur.selectedSignature ? cur.selectedSignature.id : undefined,
          thread_id: cur.replyThreadId,
          in_reply_to: cur.replyInReplyTo,
        });

        await emailsApi.sendDraft(activeDraftId);
      } else {
        // Case A: No draft exists yet (direct send)
        const payload: EmailSendPayload = {
          email_account_id: cur.selectedAccountId!,
          to: cur.toRecipients,
          cc: cur.ccRecipients.length > 0 ? cur.ccRecipients : undefined,
          bcc: cur.bccRecipients.length > 0 ? cur.bccRecipients : undefined,
          subject: cur.subject,
          body_text: cur.bodyText || undefined,
          body_html: cur.bodyHtml || undefined,
          signature_id: cur.selectedSignature ? cur.selectedSignature.id : undefined,
          thread_id: cur.replyThreadId,
          in_reply_to: cur.replyInReplyTo,
        };
        await emailsApi.sendEmail(payload);
      }

      queryClient.invalidateQueries({ queryKey: ["emails"] });
      queryClient.invalidateQueries({ queryKey: ["mailbox-counts"] });
      navigate("/mailbox?folder=sent");
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to send email. Please check your recipient addresses and SMTP settings.";
      setErrorMessage(msg);
      isSendingRef.current = false;
      setIsSending(false);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (autosaveTimerRef.current) {
        clearTimeout(autosaveTimerRef.current);
      }
    };
  }, []);

  const selectedAccount = accounts.find((a: AuthorizedEmailAccount) => a.id === selectedAccountId);

  const combinedAttachments: ComposeAttachment[] = serverAttachments.map((att) => ({
    id: att.id,
    file_name: att.file_name,
    file_size: att.file_size,
    content_type: att.content_type,
    isPending: false,
  }));

  return (
    <div className="w-full max-w-5xl mx-auto space-y-4">
      {/* Top Action Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Back to Mailbox Button */}
        <button
          type="button"
          onClick={handleBackToMailbox}
          className="inline-flex items-center gap-2 px-3 py-1.5 text-xs sm:text-sm font-medium text-slate-700 hover:text-slate-900 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Back to Mailbox</span>
        </button>

        {/* Status and Action Buttons */}
        <div className="flex items-center gap-3">
          {saveStatus === "saving" && (
            <span className="text-xs text-slate-500 font-medium flex items-center gap-1.5 mr-1 animate-pulse">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-600" />
              <span>Saving...</span>
            </span>
          )}
          {saveStatus === "saved" && lastSavedTime && (
            <span className="text-xs text-slate-500 font-medium flex items-center gap-1.5 mr-1">
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              <span>Saved {lastSavedTime}</span>
            </span>
          )}
          {saveStatus === "error" && (
            <span className="text-xs text-rose-500 font-medium flex items-center gap-1.5 mr-1">
              <AlertCircle className="h-4 w-4 text-rose-500" />
              <span>Save failed</span>
            </span>
          )}

          <button
            type="button"
            onClick={handleDiscard}
            disabled={isSending || isDiscarding}
            className="text-slate-500 hover:text-rose-600 text-xs sm:text-sm font-medium transition-colors px-3 py-1.5 rounded-lg hover:bg-rose-50 disabled:opacity-50 cursor-pointer"
          >
            Discard
          </button>

          <button
            type="button"
            onClick={handleSend}
            disabled={isSending || isUploadingAttachment}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-1.5 rounded-lg text-xs sm:text-sm font-medium flex items-center gap-2 shadow-xs transition-all disabled:opacity-50 cursor-pointer"
          >
            {isSending ? (
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
            <h1 className="text-lg sm:text-xl font-semibold text-slate-900">
              {draftId ? "Edit Draft" : "New Message"}
            </h1>
            <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
              {draftId ? "Draft" : "New"}
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
                    onChange={handleAccountChange}
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
            onChange={handleToRecipientsChange}
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
              onChange={handleCcRecipientsChange}
              placeholder="Add CC recipients..."
            />
          )}

          {/* Bcc Row */}
          {(showBcc || bccRecipients.length > 0) && (
            <RecipientInput
              label="Bcc"
              recipients={bccRecipients}
              onChange={handleBccRecipientsChange}
              placeholder="Add BCC recipients..."
            />
          )}

          {/* Subject Row */}
          <div className="py-3 flex items-center text-xs sm:text-sm">
            <span className="w-16 text-slate-500 font-medium select-none">Subject</span>
            <input
              type="text"
              value={subject}
              onChange={handleSubjectChange}
              placeholder="Enter email subject"
              className="flex-1 text-slate-900 font-medium text-sm sm:text-base outline-none placeholder-slate-400 py-0.5 bg-transparent"
            />
          </div>
        </div>

        {/* Rich Text Editor & Writing Area */}
        <div className="p-6 sm:p-8 space-y-4">
          <RichTextEditor
            initialHtml={bodyHtml}
            onChange={handleBodyChange}
            placeholder="Write your email message here..."
          />

          {/* Attachment Upload List */}
          <AttachmentUploadList
            attachments={combinedAttachments}
            onRemove={handleRemoveAttachment}
            isUploading={isUploadingAttachment}
          />

          {/* Signature Preview if selected or default */}
          {effectiveSignature && (
            <div className="pt-4 border-t border-dashed border-slate-200 text-xs sm:text-sm">
              <div className="flex items-start justify-between gap-3 text-slate-600">
                <div className="flex items-start gap-3">
                  <div className="w-8 h-8 rounded-full bg-indigo-50 text-indigo-600 flex items-center justify-center font-bold text-xs border border-indigo-100 shrink-0">
                    {effectiveSignature.name.slice(0, 2).toUpperCase()}
                  </div>
                  <div className="flex flex-col">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-900">{effectiveSignature.name}</span>
                      {effectiveSignature.is_default && !selectedSignature && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          Default
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-slate-500">
                      {effectiveSignature.body_text || "Custom Signature"}
                    </span>
                  </div>
                </div>
                {selectedSignature && (
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedSignature(null);
                      latestStateRef.current.selectedSignature = null;
                      triggerAutosave();
                    }}
                    className="text-xs text-indigo-600 hover:text-indigo-800 hover:underline cursor-pointer"
                  >
                    Reset to default
                  </button>
                )}
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
            {saveStatus === "saving" && (
              <span className="text-xs text-slate-400 font-medium flex items-center gap-1.5 mr-1 animate-pulse">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-500" />
                <span>Saving...</span>
              </span>
            )}
            {saveStatus === "saved" && lastSavedTime && (
              <span className="text-xs text-slate-400 font-medium flex items-center gap-1.5 mr-1">
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span>Saved {lastSavedTime}</span>
              </span>
            )}
            {saveStatus === "error" && (
              <span className="text-xs text-rose-500 font-medium flex items-center gap-1.5 mr-1">
                <AlertCircle className="h-4 w-4 text-rose-500" />
                <span>Save failed</span>
              </span>
            )}

            <button
              type="button"
              onClick={handleDiscard}
              disabled={isSending || isDiscarding}
              className="text-slate-500 hover:text-rose-600 text-xs sm:text-sm font-medium transition-colors px-3 py-1.5 rounded-lg hover:bg-rose-50 disabled:opacity-50 cursor-pointer"
            >
              Discard
            </button>

            <button
              type="button"
              onClick={handleSend}
              disabled={isSending || isUploadingAttachment}
              className="bg-indigo-600 hover:bg-indigo-700 text-white px-5 py-2 rounded-lg text-xs sm:text-sm font-medium flex items-center gap-2 shadow-xs transition-all disabled:opacity-50 cursor-pointer"
            >
              {isSending ? (
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
        selectedAccountId={selectedAccountId}
      />

      <SignatureModal
        isOpen={isSignatureModalOpen}
        accountId={selectedAccountId || undefined}
        onClose={() => setIsSignatureModalOpen(false)}
        onSelectSignature={handleSelectSignature}
      />
    </div>
  );
}
