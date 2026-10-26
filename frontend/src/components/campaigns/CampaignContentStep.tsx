import React, { useState, useRef, useEffect } from "react";
import DOMPurify from "dompurify";
import {
  Edit3,
  Eye,
  Code,
  ChevronDown,
  Paperclip,
  LayoutTemplate,
  PenTool,
  FileText,
  AlertCircle,
  Loader2,
} from "lucide-react";
import type { AuthorizedEmailAccount, EmailTemplateItem, EmailSignatureItem, EmailItem } from "../../types/emails";
import type { CampaignAttachment } from "../../types/campaign";
import { RichTextEditor, type RichTextEditorRef } from "../compose/RichTextEditor";
import { AttachmentUploadList, type ComposeAttachment } from "../compose/AttachmentUploadList";
import { TemplateModal } from "../compose/TemplateModal";
import { SignatureModal } from "../compose/SignatureModal";
import { DraftImportModal } from "./DraftImportModal";

export const MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB
export const MAX_CAMPAIGN_ATTACHMENTS = 10;
export const DISALLOWED_EXTENSIONS = [
  ".exe",
  ".bat",
  ".cmd",
  ".sh",
  ".bin",
  ".vbs",
  ".msi",
  ".dll",
  ".scr",
  ".pif",
  ".com",
  ".jar",
  ".ps1",
];

export interface MergeTagItem {
  tag: string;
  label: string;
  description: string;
  category: "Recipient" | "Sender & Workspace" | "Compliance";
}

export const CAMPAIGN_MERGE_TAGS: MergeTagItem[] = [
  { tag: "{{first_name}}", label: "First Name", description: "Recipient's first name", category: "Recipient" },
  { tag: "{{last_name}}", label: "Last Name", description: "Recipient's last name", category: "Recipient" },
  { tag: "{{customer_name}}", label: "Full Customer Name", description: "Recipient's full display name", category: "Recipient" },
  { tag: "{{customer_email}}", label: "Customer Email", description: "Recipient's email address", category: "Recipient" },
  { tag: "{{company_name}}", label: "Company / Workspace Name", description: "Current workspace or company name", category: "Sender & Workspace" },
  { tag: "{{sender_name}}", label: "Sender Display Name", description: "Name of the sending email account", category: "Sender & Workspace" },
  { tag: "{{sender_email}}", label: "Sender Email Address", description: "Email address sending this campaign", category: "Sender & Workspace" },
  { tag: "{{unsubscribe_url}}", label: "Unsubscribe Opt-Out Link", description: "RFC 8058 compliant unsubscribe link", category: "Compliance" },
];

export interface CampaignContentStepProps {
  subject: string;
  bodyHtml: string;
  bodyText?: string;
  onBodyHtmlChange: (html: string, text: string) => void;
  onSubjectChange?: (subject: string) => void;
  selectedSender?: AuthorizedEmailAccount | null;
  contentError?: string | null;
  companyId?: number | null;
  selectedAccountId?: number | null;
  attachments?: CampaignAttachment[];
  onUploadAttachment?: (file: File) => Promise<void>;
  onDeleteAttachment?: (attachmentId: number) => Promise<void>;
  isUploadingAttachment?: boolean;
  onImportDraft?: (draftId: number) => Promise<void>;
  onSelectTemplate?: (template: EmailTemplateItem) => void;
  onSelectSignature?: (signature: EmailSignatureItem) => void;
}

export const CampaignContentStep: React.FC<CampaignContentStepProps> = ({
  subject,
  bodyHtml,
  bodyText = "",
  onBodyHtmlChange,
  onSubjectChange,
  selectedSender,
  contentError,
  companyId,
  selectedAccountId,
  attachments = [],
  onUploadAttachment,
  onDeleteAttachment,
  isUploadingAttachment = false,
  onImportDraft,
  onSelectTemplate,
  onSelectSignature,
}) => {
  const [activeTab, setActiveTab] = useState<"edit" | "preview">("edit");
  const [isPersonalizeOpen, setIsPersonalizeOpen] = useState(false);
  const [isDraftModalOpen, setIsDraftModalOpen] = useState(false);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [isSignatureModalOpen, setIsSignatureModalOpen] = useState(false);
  const [attachmentError, setAttachmentError] = useState<string | null>(null);

  const richEditorRef = useRef<RichTextEditorRef>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Close personalize menu on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsPersonalizeOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleInsertMergeTag = (tag: string) => {
    if (richEditorRef.current) {
      richEditorRef.current.insertText(tag);
    }
    setIsPersonalizeOpen(false);
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    setAttachmentError(null);
    const fileList = e.target.files;
    if (!fileList || fileList.length === 0) return;

    const files = Array.from(fileList);
    const currentCount = attachments.length;

    if (currentCount + files.length > MAX_CAMPAIGN_ATTACHMENTS) {
      setAttachmentError(`A campaign can have a maximum of ${MAX_CAMPAIGN_ATTACHMENTS} attachments.`);
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }

    for (const file of files) {
      // Validate file size
      if (file.size > MAX_ATTACHMENT_SIZE_BYTES) {
        setAttachmentError(`File "${file.name}" exceeds the maximum limit of 25 MB.`);
        if (fileInputRef.current) fileInputRef.current.value = "";
        return;
      }

      // Validate disallowed extensions
      const lowerName = file.name.toLowerCase();
      const isDisallowed = DISALLOWED_EXTENSIONS.some((ext) => lowerName.endsWith(ext));
      if (isDisallowed) {
        setAttachmentError(`File "${file.name}" has an unsafe file extension that is not permitted.`);
        if (fileInputRef.current) fileInputRef.current.value = "";
        return;
      }
    }

    if (onUploadAttachment) {
      for (const file of files) {
        try {
          await onUploadAttachment(file);
        } catch (err: unknown) {
          const msg = err instanceof Error ? err.message : "Failed to upload attachment.";
          setAttachmentError(msg);
          break;
        }
      }
    }

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleRemoveAttachment = async (id: number | string) => {
    setAttachmentError(null);
    if (onDeleteAttachment && typeof id === "number") {
      try {
        await onDeleteAttachment(id);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : "Failed to remove attachment.";
        setAttachmentError(msg);
      }
    }
  };

  const handleSelectTemplate = (template: EmailTemplateItem) => {
    if (onSelectTemplate) {
      onSelectTemplate(template);
    } else {
      if (template.subject && onSubjectChange) {
        onSubjectChange(template.subject);
      }
      if (template.body_html) {
        const cleanHtmlForText = template.body_html
          .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, " ")
          .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, " ");
        const textFallback =
          template.body_text ||
          cleanHtmlForText.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        onBodyHtmlChange(template.body_html, textFallback);
        richEditorRef.current?.setHtml(template.body_html);
      } else if (template.body_text) {
        const html = `<p>${template.body_text.replace(/\n/g, "<br/>")}</p>`;
        onBodyHtmlChange(html, template.body_text);
        richEditorRef.current?.setHtml(html);
      }
    }
    setIsTemplateModalOpen(false);
  };

  const handleSelectSignature = (signature: EmailSignatureItem) => {
    const rawSigHtml =
      signature.body_html ||
      `<p>${(signature.body_text || "").replace(/\n/g, "<br/>")}</p>`;
    const cleanSigHtml = DOMPurify.sanitize(rawSigHtml, {
      ADD_ATTR: ["target"],
    });
    const cleanSigText = (
      signature.body_text ||
      rawSigHtml.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ")
    ).trim();

    // Prevent duplicating signature if already in bodyHtml or bodyText
    const isAlreadyInHtml = Boolean(cleanSigHtml && bodyHtml.includes(cleanSigHtml));
    const isAlreadyInText = Boolean(cleanSigText && bodyText && bodyText.includes(cleanSigText));

    if (!isAlreadyInHtml && !isAlreadyInText) {
      if (richEditorRef.current) {
        richEditorRef.current.insertBlockHtml(cleanSigHtml);
      } else {
        const updatedHtml = bodyHtml ? `${bodyHtml}<br/><br/>${cleanSigHtml}` : cleanSigHtml;
        const updatedText = bodyText ? `${bodyText}\n\n${cleanSigText}` : cleanSigText;
        onBodyHtmlChange(updatedHtml, updatedText);
      }
    }

    if (onSelectSignature) {
      onSelectSignature(signature);
    }
    setIsSignatureModalOpen(false);
  };

  const handleSelectDraft = async (draft: EmailItem) => {
    if (onImportDraft) {
      await onImportDraft(draft.id);
    }
    setIsDraftModalOpen(false);
  };

  // Preview data rendering
  const previewSampleName = "Jane";
  const replaceAllMergeTags = (content: string) => {
    return content
      .replace(/\{\{first_name\}\}/g, previewSampleName)
      .replace(/\{\{last_name\}\}/g, "Doe")
      .replace(/\{\{customer_name\}\}/g, "Jane Doe")
      .replace(/\{\{customer_email\}\}/g, "jane.doe@example.com")
      .replace(/\{\{company_name\}\}/g, "Acme Corp")
      .replace(/\{\{sender_name\}\}/g, selectedSender?.name || "Sender")
      .replace(/\{\{sender_email\}\}/g, selectedSender?.email_address || "sender@example.com")
      .replace(/\{\{unsubscribe_url\}\}/g, "#unsubscribe");
  };

  const resolvedSubject = subject
    ? replaceAllMergeTags(subject)
    : "(No Subject)";

  const rawHtmlForPreview = bodyHtml && bodyHtml.trim()
    ? replaceAllMergeTags(bodyHtml)
    : "<p class='text-slate-400 italic'>No message content provided.</p>";

  const sanitizedPreviewHtml = DOMPurify.sanitize(rawHtmlForPreview, {
    ADD_ATTR: ["target"],
  });

  const composeAttachments: ComposeAttachment[] = attachments.map((a) => ({
    id: a.id,
    file_name: a.file_name,
    file_size: a.file_size,
    content_type: a.content_type,
  }));

  const hasExistingContent = Boolean(
    subject.trim() || bodyHtml.replace(/<[^>]*>/g, "").trim()
  );

  return (
    <section className="space-y-4 sm:space-y-5">
      <div className="bg-white rounded-xl border border-slate-200 shadow-2xs overflow-hidden">
        {/* Unified Card Header & Controls */}
        <div className="px-5 py-3.5 sm:px-6 bg-white border-b border-slate-200/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="space-y-0.5 min-w-0">
            <h2 className="text-base sm:text-lg font-bold text-slate-900 tracking-tight">
              Email Content
            </h2>
            <p className="text-xs text-slate-500 truncate">
              Compose professional emails using rich formatting, attachments, templates, and signatures.
            </p>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            {/* Edit / Preview Segmented Switch */}
            <div className="flex items-center gap-0.5 bg-slate-100 p-0.5 rounded-lg border border-slate-200/60">
              <button
                type="button"
                onClick={() => setActiveTab("edit")}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                  activeTab === "edit"
                    ? "bg-white text-slate-900 shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Edit3 className="h-3.5 w-3.5" />
                <span>Edit</span>
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("preview")}
                className={`px-3 py-1.5 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
                  activeTab === "preview"
                    ? "bg-white text-slate-900 shadow-2xs"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                <Eye className="h-3.5 w-3.5" />
                <span>Preview</span>
              </button>
            </div>

            {/* Merge Tag Dropdown: {{first_name}} */}
            <div className="relative" ref={dropdownRef}>
              <button
                type="button"
                id="personalize-btn"
                onClick={() => setIsPersonalizeOpen((prev) => !prev)}
                className="px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/20 cursor-pointer"
              >
                <Code className="h-3.5 w-3.5 text-indigo-600" />
                <span>Personalize</span>
                <ChevronDown className="h-3 w-3 text-slate-400" />
              </button>

              {isPersonalizeOpen && (
                <div
                  id="personalize-menu"
                  className="absolute right-0 mt-2 w-72 rounded-xl bg-white border border-slate-200 p-2 shadow-xl z-30 animate-in fade-in zoom-in-95 duration-100"
                >
                  <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Merge Tags
                  </p>
                  <button
                    type="button"
                    onClick={() => handleInsertMergeTag("{{first_name}}")}
                    className="w-full text-left p-2 rounded-lg hover:bg-indigo-50/50 transition-colors flex items-center justify-between group focus:outline-none focus:bg-indigo-50/50 cursor-pointer"
                  >
                    <div>
                      <p className="text-xs font-bold text-indigo-600 font-mono">
                        {"{{first_name}}"}
                      </p>
                      <p className="text-[11px] text-slate-500">
                        Recipient first name
                      </p>
                    </div>
                    <span className="text-xs text-indigo-500 font-semibold opacity-0 group-hover:opacity-100 transition-opacity">
                      Insert
                    </span>
                  </button>
                  <div className="px-2 py-1.5 mt-1 bg-slate-50 rounded-lg border border-slate-100">
                    <p className="text-[11px] text-slate-500">
                      Inserts recipient first name into current email body at cursor position.
                    </p>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Subject Display Strip */}
        <div className="px-5 py-2.5 sm:px-6 bg-slate-50/80 border-b border-slate-200/80 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-semibold uppercase tracking-wider text-slate-400 text-[10px]">
              Subject:
            </span>
            <span className="font-medium text-slate-800 truncate">
              {subject || <span className="text-slate-400 italic">No subject specified</span>}
            </span>
          </div>
          <span className="text-[11px] text-slate-400 hidden sm:inline font-mono">
            Step 3 of 4
          </span>
        </div>

        {/* Editor Body Surface (Edit View) */}
        {activeTab === "edit" && (
          <div className="p-4 sm:p-5 space-y-4">
            <div id="email-body-content">
              <RichTextEditor
                ref={richEditorRef}
                initialHtml={bodyHtml}
                onChange={(html, text) => onBodyHtmlChange(html, text)}
                placeholder="Write your campaign email content here..."
                minHeightClass="min-h-[300px]"
              />
            </div>

            {/* Attachments Section */}
            {(composeAttachments.length > 0 || isUploadingAttachment) && (
              <AttachmentUploadList
                attachments={composeAttachments}
                onRemove={handleRemoveAttachment}
                isUploading={isUploadingAttachment}
              />
            )}

            {/* Quick Tools Action Bar */}
            <div className="pt-2 flex items-center gap-2 flex-wrap border-t border-slate-100">
              <input
                ref={fileInputRef}
                type="file"
                multiple
                onChange={handleFileSelect}
                className="hidden"
              />

              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploadingAttachment || attachments.length >= MAX_CAMPAIGN_ATTACHMENTS}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
              >
                {isUploadingAttachment ? (
                  <Loader2 className="h-3.5 w-3.5 text-indigo-500 animate-spin" />
                ) : (
                  <Paperclip className="h-3.5 w-3.5 text-slate-500" />
                )}
                <span>Attach Files</span>
                {attachments.length > 0 && (
                  <span className="ml-1 px-1.5 py-0.2 bg-slate-100 text-slate-600 rounded text-[10px]">
                    {attachments.length}/{MAX_CAMPAIGN_ATTACHMENTS}
                  </span>
                )}
              </button>

              <button
                type="button"
                onClick={() => setIsDraftModalOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer"
              >
                <FileText className="h-3.5 w-3.5 text-slate-500" />
                <span>Use Existing Draft</span>
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
          </div>
        )}

        {/* Preview Tab Surface */}
        {activeTab === "preview" && (
          <div className="p-6 bg-slate-50/40">
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 sm:p-5 space-y-4">
              {/* Preview Metadata Card */}
              <div className="space-y-1.5 text-xs border-b border-slate-200/80 pb-3">
                <div className="flex items-center gap-2">
                  <span className="text-slate-400 w-16 shrink-0 font-medium">From:</span>
                  <span className="font-semibold text-slate-900 truncate">
                    {selectedSender
                      ? `${selectedSender.name} <${selectedSender.email_address}>`
                      : "Sender not selected"}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-slate-400 w-16 shrink-0 font-medium">To:</span>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-slate-800">
                      Sample Recipient (Jane)
                    </span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-200 text-slate-600 font-medium">
                      Simulated Preview
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-slate-400 w-16 shrink-0 font-medium">Subject:</span>
                  <span className="font-semibold text-slate-900">
                    {resolvedSubject}
                  </span>
                </div>
                {attachments.length > 0 && (
                  <div className="flex items-center gap-2 pt-1">
                    <span className="text-slate-400 w-16 shrink-0 font-medium">Files:</span>
                    <div className="flex flex-wrap gap-1.5">
                      {attachments.map((att) => (
                        <span
                          key={att.id}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] bg-slate-200/80 text-slate-700 font-medium"
                        >
                          <Paperclip className="h-3 w-3 text-slate-500" />
                          <span>{att.file_name}</span>
                          <span className="text-slate-400">({(att.file_size / 1024).toFixed(0)} KB)</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* Rendered HTML Content Card */}
              <div className="bg-white rounded-lg border border-slate-200 p-5 shadow-2xs space-y-3 text-xs sm:text-sm text-slate-900 leading-relaxed min-h-[220px]">
                <div
                  dangerouslySetInnerHTML={{ __html: sanitizedPreviewHtml }}
                  className="space-y-2"
                />
              </div>
            </div>
          </div>
        )}

        {/* Inline Attachment Error */}
        {attachmentError && (
          <div className="px-6 py-2.5 bg-amber-50/70 border-t border-amber-200 text-xs text-amber-700 flex items-center justify-between gap-1.5 font-medium">
            <div className="flex items-center gap-1.5">
              <AlertCircle className="h-4 w-4 shrink-0 text-amber-600" />
              <span>{attachmentError}</span>
            </div>
            <button
              type="button"
              onClick={() => setAttachmentError(null)}
              className="text-amber-500 hover:text-amber-700 text-xs underline cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* Inline Content Error */}
        {contentError && (
          <div className="px-6 py-2.5 bg-red-50/50 border-t border-red-200 text-xs text-red-600 flex items-center gap-1.5 font-medium">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{contentError}</span>
          </div>
        )}
      </div>

      {/* Modals */}
      {isDraftModalOpen && (
        <DraftImportModal
          isOpen={isDraftModalOpen}
          onClose={() => setIsDraftModalOpen(false)}
          onSelectDraft={handleSelectDraft}
          selectedAccountId={selectedAccountId}
          companyId={companyId}
          hasExistingContent={hasExistingContent}
        />
      )}

      {isTemplateModalOpen && (
        <TemplateModal
          isOpen={isTemplateModalOpen}
          onClose={() => setIsTemplateModalOpen(false)}
          onSelectTemplate={handleSelectTemplate}
          hasExistingContent={hasExistingContent}
          selectedAccountId={selectedAccountId}
          companyId={companyId}
        />
      )}

      {isSignatureModalOpen && (
        <SignatureModal
          isOpen={isSignatureModalOpen}
          accountId={selectedAccountId || undefined}
          companyId={companyId || undefined}
          onClose={() => setIsSignatureModalOpen(false)}
          onSelectSignature={handleSelectSignature}
        />
      )}
    </section>
  );
};
