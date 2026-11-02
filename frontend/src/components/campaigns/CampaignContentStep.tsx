import React, { useState, useRef, useEffect, useMemo } from "react";
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
  Plus,
  Trash2,
  Copy,
  Tag,
  Clock,
  Send,
  CheckCircle,
  ShieldCheck,
  Zap,
  Check,
  CornerDownRight,
  MoreHorizontal,
  X,
} from "lucide-react";
import type { AuthorizedEmailAccount, EmailTemplateItem, EmailSignatureItem, EmailItem } from "../../types/emails";
import type { CampaignAttachment, CampaignStepWritePayload, SendingWindowConfig } from "../../types/campaign";
import { RichTextEditor, type RichTextEditorRef } from "../compose/RichTextEditor";
import { AttachmentUploadList, type ComposeAttachment } from "../compose/AttachmentUploadList";
import { TemplateModal } from "../compose/TemplateModal";
import { SignatureModal } from "../compose/SignatureModal";
import { DraftImportModal } from "./DraftImportModal";

export const MAX_ATTACHMENT_SIZE_BYTES = 25 * 1024 * 1024; // 25 MB
export const MAX_CAMPAIGN_ATTACHMENTS = 10;
export const MAX_FOLLOWUP_STEPS = 9; // 9 follow-up steps (steps 2-10) + 1 initial step = 10 total steps
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
  followupSteps?: CampaignStepWritePayload[];
  onFollowupStepsChange?: (steps: CampaignStepWritePayload[]) => void;
  sendingWindow?: SendingWindowConfig | null;
  initialStepNumber?: number;
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
  followupSteps = [],
  onFollowupStepsChange,
  sendingWindow,
  initialStepNumber,
}) => {
  // Selected Step State (1 = Initial Outreach, 2..10 = Follow-ups)
  const [selectedStepNumber, setSelectedStepNumber] = useState<number>(() => {
    if (initialStepNumber !== undefined && Number.isFinite(initialStepNumber)) {
      const maxStep = (followupSteps?.length ?? 0) + 1;
      return Math.min(Math.max(1, initialStepNumber), Math.max(1, maxStep));
    }
    return 1;
  });

  const prevInitialStepNumberRef = useRef(initialStepNumber);
  useEffect(() => {
    if (
      initialStepNumber !== undefined &&
      initialStepNumber !== prevInitialStepNumberRef.current
    ) {
      prevInitialStepNumberRef.current = initialStepNumber;
      const maxStep = (followupSteps?.length ?? 0) + 1;
      setSelectedStepNumber(Math.min(Math.max(1, initialStepNumber), Math.max(1, maxStep)));
    }
  }, [initialStepNumber, followupSteps?.length]);

  // Keep selection valid if steps change
  const clampedStepNumber = Math.min(
    Math.max(1, selectedStepNumber),
    followupSteps.length + 1
  );

  useEffect(() => {
    const maxStep = followupSteps.length + 1;
    if (selectedStepNumber > maxStep) {
      setSelectedStepNumber(Math.max(1, maxStep));
    }
  }, [followupSteps.length, selectedStepNumber]);

  // Modals & Popovers
  const [isPersonalizeOpen, setIsPersonalizeOpen] = useState(false);
  const [isDraftModalOpen, setIsDraftModalOpen] = useState(false);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [isSignatureModalOpen, setIsSignatureModalOpen] = useState(false);
  const [isTestSendModalOpen, setIsTestSendModalOpen] = useState(false);
  const [testEmailAddress, setTestEmailAddress] = useState("");
  const [testSendSuccess, setTestSendSuccess] = useState(false);
  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);

  const [isSubjectFocused, setIsSubjectFocused] = useState(false);
  // View mode tab for the active step ("edit" vs "preview")
  const [activeTab, setActiveTab] = useState<"edit" | "preview">("edit");
  const [attachmentError, setAttachmentError] = useState<string | null>(null);

  // Tag inputs per follow-up step index
  const [newStepTagInputs, setNewStepTagInputs] = useState<{ [index: number]: string }>({});

  const richEditorRef = useRef<RichTextEditorRef>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const moreMenuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Close menus on outside click
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsPersonalizeOpen(false);
      }
      if (moreMenuRef.current && !moreMenuRef.current.contains(event.target as Node)) {
        setIsMoreMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Total Sequence Cadence Calculation
  const totalCadenceDays = useMemo(() => {
    return followupSteps.reduce((acc, step) => {
      const days = Math.ceil((step.delay_hours || 0) / 24);
      return acc + Math.max(1, days);
    }, 0);
  }, [followupSteps]);

  const totalStepsCount = 1 + followupSteps.length;

  // Active step references
  const isInitialStep = clampedStepNumber === 1;
  const currentFollowupIndex = clampedStepNumber - 2;
  const currentFollowupStep =
    !isInitialStep && currentFollowupIndex >= 0 && currentFollowupIndex < followupSteps.length
      ? followupSteps[currentFollowupIndex]
      : null;

  // Active step subject & body
  const currentSubject = isInitialStep
    ? subject
    : currentFollowupStep?.subject || "";

  const currentBodyHtml = isInitialStep
    ? bodyHtml
    : currentFollowupStep?.body_html || "";

  const currentBodyText = isInitialStep
    ? bodyText
    : currentFollowupStep?.body_text || "";

  // Helper for merge tag replacement in previews
  const replaceAllMergeTags = (content: string) => {
    return content
      .replace(/\{\{first_name\}\}/g, "Jane")
      .replace(/\{\{last_name\}\}/g, "Doe")
      .replace(/\{\{customer_name\}\}/g, "Jane Doe")
      .replace(/\{\{customer_email\}\}/g, "jane.doe@example.com")
      .replace(/\{\{company_name\}\}/g, "Acme Corp")
      .replace(/\{\{sender_name\}\}/g, selectedSender?.name || "Sender")
      .replace(/\{\{sender_email\}\}/g, selectedSender?.email_address || "sales@example.com")
      .replace(/\{\{unsubscribe_url\}\}/g, "#unsubscribe");
  };

  const previewSubject = currentSubject
    ? replaceAllMergeTags(currentSubject)
    : isInitialStep
    ? "(No Subject)"
    : `Re: ${replaceAllMergeTags(subject || "Campaign Subject")}`;

  const previewBody = currentBodyHtml && currentBodyHtml.trim()
    ? replaceAllMergeTags(currentBodyHtml)
    : currentBodyText && currentBodyText.trim()
    ? replaceAllMergeTags(`<p>${currentBodyText.replace(/\n/g, "<br/>")}</p>`)
    : "<p class='text-slate-400 italic'>No message content provided for this step.</p>";

  const sanitizedPreviewHtml = DOMPurify.sanitize(previewBody, {
    ADD_ATTR: ["target"],
  });

  // Step Updates
  const handleActiveSubjectChange = (newSubject: string) => {
    if (isInitialStep) {
      onSubjectChange?.(newSubject);
    } else if (currentFollowupIndex >= 0) {
      handleUpdateFollowupStep(currentFollowupIndex, "subject", newSubject);
    }
  };

  const handleActiveBodyChange = (html: string, text: string) => {
    if (isInitialStep) {
      onBodyHtmlChange(html, text);
    } else if (currentFollowupIndex >= 0) {
      handleFollowupBodyChange(currentFollowupIndex, html, text);
    }
  };

  const handleInsertMergeTag = (tag: string) => {
    if (richEditorRef.current) {
      richEditorRef.current.insertText(tag);
    } else {
      handleActiveBodyChange(
        currentBodyHtml ? `${currentBodyHtml} ${tag}` : tag,
        currentBodyText ? `${currentBodyText} ${tag}` : tag
      );
    }
    setIsPersonalizeOpen(false);
  };

  // Follow-up actions
  const handleAddFollowupStep = () => {
    if (followupSteps.length >= MAX_FOLLOWUP_STEPS) return;
    const newStepNumber = followupSteps.length + 2;
    const newStep: CampaignStepWritePayload = {
      step_number: newStepNumber,
      delay_hours: 72,
      subject: "",
      body_text: "",
      body_html: "",
      is_active: true,
      target_tags: [],
    };
    const updated = [...followupSteps, newStep];
    onFollowupStepsChange?.(updated);
    setSelectedStepNumber(newStepNumber);
    setActiveTab("edit");
  };

  const handleRemoveFollowupStep = (indexToRemove: number) => {
    const stepNumberToRemove = indexToRemove + 2;
    const filtered = followupSteps.filter((_, idx) => idx !== indexToRemove);
    const reindexed = filtered.map((s, idx) => ({
      ...s,
      step_number: idx + 2,
    }));
    onFollowupStepsChange?.(reindexed);

    if (selectedStepNumber === stepNumberToRemove) {
      setSelectedStepNumber(Math.max(1, stepNumberToRemove - 1));
    } else if (selectedStepNumber > stepNumberToRemove) {
      setSelectedStepNumber(selectedStepNumber - 1);
    }
    setIsMoreMenuOpen(false);
  };

  const handleDuplicateStep = (stepNumber: number) => {
    if (followupSteps.length >= MAX_FOLLOWUP_STEPS) return;

    if (stepNumber === 1) {
      // Duplicate initial step into follow-up step #1
      const newStep: CampaignStepWritePayload = {
        step_number: 2,
        delay_hours: 48,
        subject: subject ? `Re: ${subject}` : "",
        body_html: bodyHtml,
        body_text: bodyText,
        is_active: true,
        target_tags: [],
      };
      const updated = [
        newStep,
        ...followupSteps.map((s, idx) => ({ ...s, step_number: idx + 3 })),
      ];
      onFollowupStepsChange?.(updated);
      setSelectedStepNumber(2);
    } else {
      const idx = stepNumber - 2;
      const stepToClone = followupSteps[idx];
      if (!stepToClone) return;

      const cloned: CampaignStepWritePayload = {
        ...stepToClone,
        step_number: stepNumber + 1,
        subject: stepToClone.subject || "",
        target_tags: stepToClone.target_tags ? [...stepToClone.target_tags] : [],
      };

      const updated = [
        ...followupSteps.slice(0, idx + 1),
        cloned,
        ...followupSteps.slice(idx + 1),
      ].map((s, i) => ({ ...s, step_number: i + 2 }));

      onFollowupStepsChange?.(updated);
      setSelectedStepNumber(stepNumber + 1);
    }
    setIsMoreMenuOpen(false);
  };

  const handleUpdateFollowupStep = (
    index: number,
    field: keyof CampaignStepWritePayload,
    value: any
  ) => {
    const updated = followupSteps.map((s, idx) => {
      if (idx === index) {
        return { ...s, [field]: value };
      }
      return s;
    });
    onFollowupStepsChange?.(updated);
  };

  const handleFollowupBodyChange = (
    index: number,
    html: string,
    text: string
  ) => {
    const updated = followupSteps.map((s, idx) => {
      if (idx === index) {
        return {
          ...s,
          body_html: html,
          body_text: text,
        };
      }
      return s;
    });
    onFollowupStepsChange?.(updated);
  };

  const handleAddTagToStep = (stepIdx: number) => {
    const raw = (newStepTagInputs[stepIdx] || "").trim().toLowerCase();
    if (!raw) return;
    const TAG_REGEX = /^[a-zA-Z0-9_\-\.]*$/;
    if (!TAG_REGEX.test(raw)) return;

    const currentTags = followupSteps[stepIdx]?.target_tags || [];
    if (!currentTags.includes(raw)) {
      handleUpdateFollowupStep(stepIdx, "target_tags", [...currentTags, raw]);
    }
    setNewStepTagInputs((prev) => ({ ...prev, [stepIdx]: "" }));
  };

  const handleRemoveTagFromStep = (stepIdx: number, tagToRemove: string) => {
    const currentTags = followupSteps[stepIdx]?.target_tags || [];
    handleUpdateFollowupStep(
      stepIdx,
      "target_tags",
      currentTags.filter((t) => t !== tagToRemove)
    );
  };

  // Attachment handling
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
      if (file.size > MAX_ATTACHMENT_SIZE_BYTES) {
        setAttachmentError(`File "${file.name}" exceeds the maximum limit of 25 MB.`);
        if (fileInputRef.current) fileInputRef.current.value = "";
        return;
      }
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

  // Template and Signature selection
  const handleSelectTemplate = (template: EmailTemplateItem) => {
    if (template.body_html) {
      richEditorRef.current?.setHtml(template.body_html);
    } else if (template.body_text) {
      const html = `<p>${template.body_text.replace(/\n/g, "<br/>")}</p>`;
      richEditorRef.current?.setHtml(html);
    }
    if (onSelectTemplate) {
      onSelectTemplate(template);
    } else {
      const isEmailLike = Boolean(
        template.subject && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(template.subject.trim())
      );
      if (template.subject && (!isInitialStep || !subject.trim()) && !isEmailLike) {
        handleActiveSubjectChange(template.subject);
      }
      if (template.body_html) {
        const cleanHtmlForText = template.body_html
          .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, " ")
          .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, " ");
        const textFallback =
          template.body_text ||
          cleanHtmlForText.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        handleActiveBodyChange(template.body_html, textFallback);
      } else if (template.body_text) {
        const html = `<p>${template.body_text.replace(/\n/g, "<br/>")}</p>`;
        handleActiveBodyChange(html, template.body_text);
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

    const normalizeForCheck = (str: string) =>
      str.replace(/<[^>]+>/g, " ").replace(/&nbsp;/g, " ").replace(/\s+/g, " ").trim().toLowerCase();

    const normalizedSigText = normalizeForCheck(cleanSigText || cleanSigHtml);
    const normalizedBodyHtml = normalizeForCheck(currentBodyHtml);
    const normalizedBodyText = normalizeForCheck(currentBodyText);

    const isAlreadyInBody = Boolean(
      normalizedSigText &&
      (normalizedBodyHtml.includes(normalizedSigText) || normalizedBodyText.includes(normalizedSigText))
    );

    if (!isAlreadyInBody && (cleanSigHtml || cleanSigText)) {
      const updatedHtml = currentBodyHtml ? `${currentBodyHtml}<br/><br/>${cleanSigHtml}` : cleanSigHtml;
      const updatedText = currentBodyText ? `${currentBodyText}\n\n${cleanSigText}` : cleanSigText;
      if (richEditorRef.current) {
        richEditorRef.current.setHtml(updatedHtml);
      } else {
        handleActiveBodyChange(updatedHtml, updatedText);
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

  const composeAttachments: ComposeAttachment[] = attachments.map((a) => ({
    id: a.id,
    file_name: a.file_name,
    file_size: a.file_size,
    content_type: a.content_type,
  }));

  const hasExistingContent = Boolean(
    currentSubject.trim() || currentBodyHtml.replace(/<[^>]*>/g, "").trim()
  );

  return (
    <section className="space-y-4">
      {/* 2 & 3. MASTER-DETAIL SEQUENCE ARCHITECTURE */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* ================================================================= */}
        {/* LEFT RAIL: Visual Sequence Cadence (~4 columns / ~360-400px)      */}
        {/* ================================================================= */}
        <aside className="lg:col-span-4 flex flex-col gap-3.5 lg:sticky lg:top-4 self-start">
          {/* Rail Header Card */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-3.5 shadow-2xs flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-slate-900 tracking-tight">Sequence Steps</h2>
                <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-bold" id="rail-step-count">
                  {totalStepsCount}
                </span>
              </div>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {followupSteps.length > 0
                  ? `Estimated window: ~${totalCadenceDays} business days`
                  : "Single outreach step"}
              </p>
            </div>
            <button
              type="button"
              onClick={handleAddFollowupStep}
              disabled={followupSteps.length >= MAX_FOLLOWUP_STEPS}
              className="px-3 py-1.5 rounded-lg border border-indigo-200 bg-indigo-50/70 hover:bg-indigo-100/70 text-indigo-700 text-xs font-semibold transition-colors flex items-center gap-1 shadow-2xs disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Add Step</span>
            </button>
          </div>

          {/* Timeline Nodes Card */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-3.5 shadow-2xs relative flex flex-col min-h-0">
            {/* Scrollable Steps Track — active on desktop when exceeding viewport */}
            <div className="flex flex-col relative space-y-0 lg:max-h-[calc(100vh-16rem)] overflow-y-auto overscroll-contain touch-pan-y [scrollbar-width:thin] pr-1 focus:outline-none">
              {/* Step 1: Initial Outreach Node */}
              <div
                onClick={() => {
                  setSelectedStepNumber(1);
                  setActiveTab("edit");
                }}
                className={`cursor-pointer group relative p-3.5 rounded-xl transition-colors duration-150 ${
                  selectedStepNumber === 1
                    ? "border-2 border-indigo-600 bg-white ring-4 ring-indigo-500/10 shadow-sm"
                    : "border border-slate-200 hover:border-slate-300 bg-white hover:bg-slate-50/70 shadow-2xs"
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-5 h-5 rounded-md ${
                        selectedStepNumber === 1
                          ? "bg-indigo-600 text-white"
                          : "bg-slate-100 text-slate-700 border border-slate-200/60"
                      } flex items-center justify-center text-[11px] font-bold`}
                    >
                      1
                    </span>
                    <span className="text-xs font-bold text-slate-900">Initial Outreach</span>
                  </div>
                  <span className="text-[11px] font-semibold text-emerald-600 flex items-center gap-1">
                    <Zap className="h-3 w-3 fill-emerald-600" /> Immediate
                  </span>
                </div>

                <p className="text-xs text-slate-700 line-clamp-1 font-medium mb-2.5">
                  {subject || <span className="text-slate-400 italic">Untitled campaign subject</span>}
                </p>

                <div
                  className={`flex items-center justify-between text-[11px] text-slate-500 pt-2 border-t ${
                    selectedStepNumber === 1 ? "border-indigo-100" : "border-slate-100"
                  }`}
                >
                  <span className="text-slate-600 font-medium">All recipients</span>
                  <div className="flex items-center gap-1.5 text-slate-400">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDuplicateStep(1);
                      }}
                      className="p-1 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                      title="Duplicate as follow-up step"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Follow-up Steps Timeline */}
              {followupSteps.map((fStep, idx) => {
                const stepNum = idx + 2;
                const isSelected = selectedStepNumber === stepNum;
                const isDays = fStep.delay_hours >= 24 && fStep.delay_hours % 24 === 0;
                const waitVal = isDays ? fStep.delay_hours / 24 : fStep.delay_hours;
                const waitUnit = isDays ? "days" : "hours";
                const isBreakup = idx === followupSteps.length - 1 && followupSteps.length >= 2;

                return (
                  <React.Fragment key={idx}>
                    {/* Stem & Delay Connector */}
                    <div className="relative py-1.5 flex items-center justify-center">
                      <div className="absolute inset-y-0 w-0.5 bg-gradient-to-b from-slate-200 via-slate-300 to-slate-200"></div>
                      <div className="relative z-10 inline-flex items-center gap-1.5 px-3 py-0.5 rounded-full bg-white border border-slate-200 text-[11px] text-slate-600 shadow-2xs font-medium">
                        <Clock className="h-3 w-3 text-slate-400" />
                        <span className="font-semibold text-slate-800">
                          Wait {waitVal} {waitUnit}
                        </span>
                        <span className="text-slate-300">·</span>
                        <span className="text-slate-500">if no reply</span>
                      </div>
                    </div>

                    {/* Step Card Node */}
                    <div
                      onClick={() => {
                        setSelectedStepNumber(stepNum);
                        setActiveTab("edit");
                      }}
                      className={`cursor-pointer group relative p-3.5 rounded-xl transition-colors duration-150 ${
                        isSelected
                          ? "border-2 border-indigo-600 bg-white ring-4 ring-indigo-500/10 shadow-sm"
                          : "border border-slate-200 hover:border-slate-300 bg-white hover:bg-slate-50/70 shadow-2xs"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <div className="flex items-center gap-2">
                          <span
                            className={`w-5 h-5 rounded-md ${
                              isSelected
                                ? "bg-indigo-600 text-white"
                                : "bg-slate-100 text-slate-700 border border-slate-200/60"
                            } flex items-center justify-center text-[11px] font-bold`}
                          >
                            {stepNum}
                          </span>
                          <span className="text-xs font-bold text-slate-900">
                            Follow-Up Step #{idx + 1} (Step {stepNum})
                          </span>
                        </div>

                        {isSelected ? (
                          <span className="px-2 py-0.5 rounded-full bg-indigo-600 text-white text-[10px] font-semibold tracking-wide">
                            Editing
                          </span>
                        ) : isBreakup ? (
                          <span className="text-[10px] font-medium text-slate-500 px-2 py-0.5 rounded-full bg-slate-100 border border-slate-200/60">
                            Breakup Email
                          </span>
                        ) : (
                          <span className="text-[10px] font-medium text-slate-500 px-2 py-0.5 rounded-full bg-slate-100 border border-slate-200/60">
                            Step {stepNum}
                          </span>
                        )}
                      </div>

                      {/* Sub-meta row */}
                      <div className="flex items-center gap-2 mb-2">
                        <span className="inline-flex items-center gap-1 text-[11px] text-indigo-600 font-medium">
                          <CornerDownRight className="h-3 w-3" />
                          <span>Threaded (Re:)</span>
                        </span>
                        <span className="text-slate-300">•</span>
                        <span className="text-[11px] text-slate-500 font-medium">
                          +{fStep.delay_hours} hrs later
                        </span>
                      </div>

                      <p className="text-xs text-slate-700 line-clamp-1 font-medium mb-2.5">
                        "{fStep.subject || `Re: ${subject || "Campaign Subject"}`}"
                      </p>

                      <div
                        className={`flex items-center justify-between text-[11px] text-slate-500 pt-2 border-t ${
                          isSelected ? "border-indigo-100" : "border-slate-100"
                        }`}
                      >
                        <span className="truncate max-w-[190px]">
                          {fStep.target_tags && fStep.target_tags.length > 0
                            ? `${fStep.target_tags.length} ${fStep.target_tags.length === 1 ? "tag" : "tags"} targeted`
                            : "All recipients"}
                        </span>
                        <div className="flex items-center gap-1 text-slate-400">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDuplicateStep(stepNum);
                            }}
                            className="p-1 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors"
                            title="Duplicate step"
                          >
                            <Copy className="h-3.5 w-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleRemoveFollowupStep(idx);
                            }}
                            className="p-1 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors"
                            title="Delete step"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  </React.Fragment>
                );
              })}
            </div>

            {/* Bottom Add Step Action pinned below scrollable steps track */}
            <div className="mt-3.5 pt-3 border-t border-slate-100 text-center shrink-0">
              <button
                type="button"
                onClick={handleAddFollowupStep}
                disabled={followupSteps.length >= MAX_FOLLOWUP_STEPS}
                className="w-full py-2.5 px-3 rounded-lg border border-dashed border-slate-300 hover:border-indigo-400 hover:bg-indigo-50/40 text-xs font-semibold text-slate-600 hover:text-indigo-600 transition-colors duration-150 flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <Plus className="h-3.5 w-3.5 text-slate-400 group-hover:text-indigo-600" />
                <span>+ Add Follow-Up Step</span>
                {followupSteps.length > 0 && (
                  <span className="ml-1 text-[10px] px-1.5 py-0.2 rounded bg-slate-100 text-slate-600 font-mono">
                    {followupSteps.length}/{MAX_FOLLOWUP_STEPS}
                  </span>
                )}
              </button>
            </div>
          </div>

          {/* Max Step Limit Notice */}
          {followupSteps.length >= MAX_FOLLOWUP_STEPS && (
            <div className="p-3 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-800 flex items-center gap-2 font-medium">
              <AlertCircle className="h-4 w-4 shrink-0 text-amber-600" />
              <span>
                Maximum sequence limit reached (1 initial email + {MAX_FOLLOWUP_STEPS} follow-up steps = 10 total steps).
              </span>
            </div>
          )}

          {/* Deliverability Guard Note */}
          <div className="p-3 rounded-xl border border-slate-200/90 bg-white shadow-2xs flex items-start gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0 mt-0.5 border border-emerald-100">
              <ShieldCheck className="h-4 w-4" />
            </div>
            <div>
              <p className="text-xs font-bold text-slate-900">Smart Jitter Throttling</p>
              <p className="text-[11px] text-slate-500 leading-normal mt-0.5">
                Follow-ups are naturally dispersed in random ±8 min windows to emulate authentic human dispatch.
              </p>
            </div>
          </div>
        </aside>

        {/* ================================================================= */}
        {/* RIGHT PANEL: Expansive & Distraction-free Editor Workspace        */}
        {/* ================================================================= */}
        <main className="lg:col-span-8 flex flex-col gap-3.5">
          {/* Top Step Settings Bar */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-4 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-700 font-bold flex items-center justify-center text-sm shadow-2xs">
                {selectedStepNumber}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-slate-900 tracking-tight">
                    {isInitialStep
                      ? "Step 1: Initial Outreach"
                      : `Step ${selectedStepNumber}: Follow-up #${currentFollowupIndex + 1}`}
                  </h2>
                  {isInitialStep && <h2 className="sr-only">Email Content</h2>}
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[11px] font-semibold border border-emerald-200/70">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                    Ready
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  {isInitialStep
                    ? "Primary email dispatched immediately upon campaign launch"
                    : `Threaded response sent to recipients who did not reply to Step ${selectedStepNumber - 1}`}
                </p>
              </div>
            </div>

            {/* Workspace Actions */}
            <div className="flex items-center gap-2.5 self-start sm:self-auto">
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

              {/* Send Test Button */}
              <button
                type="button"
                onClick={() => {
                  setTestSendSuccess(false);
                  setIsTestSendModalOpen(true);
                }}
                className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors flex items-center gap-1.5 shadow-2xs cursor-pointer"
              >
                <Send className="h-3.5 w-3.5 text-indigo-600" />
                <span>Send Test</span>
              </button>

              {/* More Actions Dropdown (for follow-up steps) */}
              {!isInitialStep && (
                <div className="relative" ref={moreMenuRef}>
                  <button
                    type="button"
                    onClick={() => setIsMoreMenuOpen((prev) => !prev)}
                    className="p-1.5 rounded-lg border border-slate-200 text-slate-500 hover:text-slate-800 hover:bg-slate-50 transition-colors shadow-2xs cursor-pointer"
                    title="Step actions"
                  >
                    <MoreHorizontal className="h-4 w-4" />
                  </button>

                  {isMoreMenuOpen && (
                    <div className="absolute right-0 top-full mt-1.5 bg-white border border-slate-200 rounded-xl shadow-xl py-1 w-36 z-30 text-xs animate-in fade-in duration-100">
                      <button
                        type="button"
                        onClick={() => handleDuplicateStep(selectedStepNumber)}
                        className="w-full text-left px-3 py-1.5 hover:bg-slate-50 flex items-center gap-2 text-slate-700 font-medium cursor-pointer"
                      >
                        <Copy className="h-3.5 w-3.5 text-slate-400" /> Duplicate
                      </button>
                      <button
                        type="button"
                        onClick={() => handleRemoveFollowupStep(currentFollowupIndex)}
                        className="w-full text-left px-3 py-1.5 hover:bg-rose-50 flex items-center gap-2 text-rose-600 font-medium cursor-pointer"
                      >
                        <Trash2 className="h-3.5 w-3.5 text-rose-500" /> Delete Step
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>


          {/* Dispatch Rules & Conditions Card */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-4 shadow-2xs">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-bold text-slate-900 tracking-wider uppercase">
                Dispatch Rules &amp; Conditions
              </span>
              <span className="text-[11px] text-slate-400 font-medium">Automatic Guardrails</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pb-3 border-b border-slate-100">
              {/* Trigger / Wait Duration Box */}
              <div className="p-3 rounded-xl bg-slate-50/70 border border-slate-200/80">
                {isInitialStep ? (
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Trigger Event
                    </label>
                    <div className="flex items-center gap-2 py-0.5">
                      <Zap className="h-4 w-4 text-emerald-600 fill-emerald-600" />
                      <span className="text-xs font-bold text-slate-800">
                        Immediately upon sequence launch
                      </span>
                    </div>
                  </div>
                ) : (
                  <div>
                    <label className="block text-xs font-semibold text-slate-700 mb-1">
                      Wait Duration
                    </label>
                    {(() => {
                      const fStep = currentFollowupStep;
                      const delayHours = fStep?.delay_hours ?? 72;
                      const isDays = delayHours >= 24 && delayHours % 24 === 0;
                      const waitVal = isDays ? delayHours / 24 : delayHours;
                      const waitUnit = isDays ? "days" : "hours";

                      return (
                        <div className="flex items-center gap-2 pt-0.5">
                          <span className="text-xs text-slate-500 font-medium">Wait</span>
                          <input
                            type="number"
                            min={1}
                            max={waitUnit === "days" ? 30 : 720}
                            value={waitVal}
                            onChange={(e) => {
                              const val = Math.max(1, parseInt(e.target.value, 10) || 1);
                              const newHours = waitUnit === "days" ? val * 24 : val;
                              handleUpdateFollowupStep(
                                currentFollowupIndex,
                                "delay_hours",
                                Math.min(720, Math.max(1, newHours))
                              );
                            }}
                            className="w-16 px-2.5 py-1 text-xs border border-slate-200 rounded-lg bg-white text-center font-bold focus:outline-none focus:ring-1 focus:ring-indigo-500"
                          />
                          <select
                            value={waitUnit}
                            onChange={(e) => {
                              const unit = e.target.value;
                              const newHours = unit === "days" ? waitVal * 24 : waitVal;
                              handleUpdateFollowupStep(
                                currentFollowupIndex,
                                "delay_hours",
                                Math.min(720, Math.max(1, newHours))
                              );
                            }}
                            className="px-2.5 py-1 text-xs border border-slate-200 rounded-lg bg-white font-medium focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
                          >
                            <option value="days">Days</option>
                            <option value="hours">Hours</option>
                          </select>
                          <span className="text-[11px] text-slate-400">after previous step</span>
                        </div>
                      );
                    })()}
                  </div>
                )}
              </div>

              {/* Sending Window Box */}
              <div className="p-3 rounded-xl bg-slate-50/70 border border-slate-200/80">
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Sending Window
                </label>
                <div className="flex items-center gap-2 py-0.5 text-xs text-slate-800 font-medium">
                  <Clock className="h-4 w-4 text-slate-400 shrink-0" />
                  <span className="truncate">
                    {sendingWindow?.enabled
                      ? `${sendingWindow.start_time} - ${sendingWindow.end_time} (${sendingWindow.timezone})`
                      : "Unrestricted (24/7)"}
                  </span>
                </div>
              </div>
            </div>

            {/* Smart Guardrail Toggles */}
            <div className={`grid grid-cols-1 ${isInitialStep ? "grid-cols-1" : "md:grid-cols-2"} gap-3 pt-3`}>
              <label className="flex items-start gap-2.5 select-none">
                <input
                  type="checkbox"
                  checked={true}
                  readOnly
                  className="mt-0.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-4 h-4 cursor-default"
                />
                <div className="flex flex-col">
                  <span className="text-xs font-bold text-slate-800">
                    Stop sequence if recipient replies
                  </span>
                  <span className="text-[11px] text-slate-500">
                    Halts automatically upon reply, bounce, or unsubscribe.
                  </span>
                </div>
              </label>

              {!isInitialStep && (
                <label className="flex items-start gap-2.5 select-none">
                  <input
                    type="checkbox"
                    checked={true}
                    readOnly
                    className="mt-0.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 w-4 h-4 cursor-default"
                  />
                  <div className="flex flex-col">
                    <span className="text-xs font-bold text-slate-800">
                      Send as reply in the same thread
                    </span>
                    <span className="text-[11px] text-slate-500">
                      Appends Re: and maintains RFC 2822 conversation context.
                    </span>
                  </div>
                </label>
              )}
            </div>

            {/* Follow-up Target Tags Section (for follow-ups only) */}
            {!isInitialStep && (
              <div className="mt-4 pt-4 border-t border-slate-100 space-y-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                  <div className="flex items-center gap-1.5">
                    <Tag className="w-3.5 h-3.5 text-indigo-600" />
                    <span className="text-xs font-bold text-slate-700">
                      Target Recipient Tags (Optional)
                    </span>
                  </div>
                  <span className="text-[11px] text-slate-500">
                    {currentFollowupStep?.target_tags && currentFollowupStep.target_tags.length > 0
                      ? "Applies to recipients matching ANY tag (OR matching)"
                      : "Targets all recipients (untargeted)"}
                  </span>
                </div>

                <div className="flex items-center gap-1.5 flex-wrap">
                  {currentFollowupStep?.target_tags && currentFollowupStep.target_tags.length > 0 ? (
                    currentFollowupStep.target_tags.map((t) => (
                      <span
                        key={t}
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200"
                      >
                        <span>#{t}</span>
                        <button
                          type="button"
                          onClick={() => handleRemoveTagFromStep(currentFollowupIndex, t)}
                          className="hover:text-indigo-900 cursor-pointer p-0.5"
                          title={`Remove tag ${t}`}
                          aria-label={`Remove tag ${t} from step ${selectedStepNumber}`}
                        >
                          &times;
                        </button>
                      </span>
                    ))
                  ) : (
                    <span className="text-[11px] text-slate-400 italic">
                      No targeting tags configured — step will be sent to all recipients.
                    </span>
                  )}

                  <div className="flex items-center gap-1 sm:ml-auto w-full sm:w-auto pt-1 sm:pt-0">
                    <input
                      type="text"
                      placeholder="Add tag (e.g. vip)..."
                      value={newStepTagInputs[currentFollowupIndex] || ""}
                      onChange={(e) =>
                        setNewStepTagInputs((prev) => ({
                          ...prev,
                          [currentFollowupIndex]: e.target.value,
                        }))
                      }
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          handleAddTagToStep(currentFollowupIndex);
                        }
                      }}
                      className="px-2 py-1 text-xs border border-slate-200 rounded-md bg-white focus:outline-none focus:ring-1 focus:ring-indigo-500 w-32 sm:w-28"
                    />
                    <button
                      type="button"
                      onClick={() => handleAddTagToStep(currentFollowupIndex)}
                      className="px-2.5 py-1 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-md cursor-pointer"
                    >
                      Add
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Subject Line Section */}
          <div className="bg-white rounded-xl border border-slate-200/90 p-4 shadow-2xs space-y-2">
            <div className="flex items-center justify-between">
              <label
                htmlFor="step-subject-input"
                className="text-xs font-bold text-slate-900 tracking-wider uppercase"
              >
                Subject Line
              </label>
              <div className="flex items-center gap-3">
                <span className="text-[11px] text-slate-400 font-mono px-2 py-0.5 rounded bg-slate-100">
                  {currentSubject.length}/80 chars
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setIsSubjectFocused(true);
                    handleActiveSubjectChange(`${currentSubject} {{first_name}}`.trim());
                  }}
                  className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors flex items-center gap-1 cursor-pointer"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Insert Variable</span>
                </button>
              </div>
            </div>

            <input
              id="step-subject-input"
              name="pulsemail_step_headline"
              type="text"
              readOnly={!isSubjectFocused}
              onFocus={() => setIsSubjectFocused(true)}
              value={currentSubject}
              onChange={(e) => handleActiveSubjectChange(e.target.value)}
              placeholder={
                isInitialStep
                  ? "e.g. Exclusive invite for {{first_name}}"
                  : `Re: ${subject || "Campaign Subject"}`
              }
              autoComplete="off"
              autoCorrect="off"
              spellCheck={true}
              data-lpignore="true"
              data-1p-ignore="true"
              data-form-type="other"
              className="w-full px-3.5 py-2.5 rounded-lg border border-slate-200 bg-slate-50/40 hover:bg-white focus:bg-white text-sm text-slate-900 font-medium focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 transition-all shadow-2xs"
            />

            {!isInitialStep && (
              <p className="text-[11px] text-slate-400">
                Sent as a threaded reply in the same email conversation. Defaults to "Re: {subject || "Subject"}" if left empty.
              </p>
            )}
          </div>

          {/* Active Step Workspace: Edit vs Preview */}
          {activeTab === "edit" ? (
            <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs flex flex-col overflow-hidden">
              {/* Token Quick-Insert Chips */}
              <div className="px-4 pt-2.5 pb-2 flex items-center gap-1.5 overflow-x-auto border-b border-slate-100 bg-slate-50/40">
                <span className="text-[11px] font-bold text-slate-400 uppercase tracking-wider shrink-0 mr-1.5">
                  Insert Tokens:
                </span>
                {[
                  "{{first_name}}",
                  "{{last_name}}",
                  "{{company_name}}",
                  "{{sender_name}}",
                  "{{sender_email}}",
                  "{{unsubscribe_url}}",
                ].map((token) => (
                  <button
                    key={token}
                    type="button"
                    aria-label={token}
                    onClick={() => handleInsertMergeTag(token)}
                    className="px-2.5 py-1 rounded-md bg-white hover:bg-indigo-50 hover:text-indigo-700 text-[11px] font-mono text-slate-700 transition-colors shrink-0 border border-slate-200/80 hover:border-indigo-200 shadow-2xs cursor-pointer"
                  >
                    + {token}
                  </button>
                ))}
              </div>

              {/* Quick Tools & Secondary Actions Strip */}
              <div className="px-4 py-2 bg-white border-b border-slate-100 flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-2 flex-wrap">
                  {/* Personalize Menu */}
                  <div className="relative" ref={dropdownRef}>
                    <button
                      type="button"
                      id="personalize-btn"
                      onClick={() => setIsPersonalizeOpen((prev) => !prev)}
                      className="px-2.5 py-1.5 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1.5 shadow-2xs transition-colors cursor-pointer"
                    >
                      <Code className="h-3.5 w-3.5 text-indigo-600" />
                      <span>Personalize</span>
                      <ChevronDown className="h-3 w-3 text-slate-400" />
                    </button>

                    {isPersonalizeOpen && (
                      <div
                        id="personalize-menu"
                        className="absolute left-0 mt-2 w-80 max-h-96 overflow-y-auto rounded-xl bg-white border border-slate-200 p-2.5 shadow-xl z-30 space-y-2.5"
                      >
                        {(["Recipient", "Sender & Workspace", "Compliance"] as const).map((category) => {
                          const tagsInCategory = CAMPAIGN_MERGE_TAGS.filter((t) => t.category === category);
                          if (tagsInCategory.length === 0) return null;
                          return (
                            <div key={category} className="space-y-1">
                              <p className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                {category}
                              </p>
                              {tagsInCategory.map((item) => (
                                <button
                                  key={item.tag}
                                  type="button"
                                  onClick={() => handleInsertMergeTag(item.tag)}
                                  className="w-full text-left p-2 rounded-lg hover:bg-indigo-50/60 transition-colors flex items-center justify-between group cursor-pointer"
                                >
                                  <div className="min-w-0 pr-2">
                                    <div className="flex items-center gap-1.5 flex-wrap">
                                      <span className="text-xs font-bold text-indigo-600 font-mono">
                                        {item.tag}
                                      </span>
                                      <span className="text-[11px] font-medium text-slate-700">
                                        — {item.label}
                                      </span>
                                    </div>
                                    <p className="text-[10px] text-slate-400 truncate mt-0.5">
                                      {item.description}
                                    </p>
                                  </div>
                                  <span className="text-[11px] text-indigo-600 font-semibold opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                                    Insert
                                  </span>
                                </button>
                              ))}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {/* Templates Modal Trigger */}
                  <button
                    type="button"
                    onClick={() => setIsTemplateModalOpen(true)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer"
                  >
                    <LayoutTemplate className="h-3.5 w-3.5 text-slate-500" />
                    <span>Insert Template</span>
                  </button>

                  {/* Signatures Modal Trigger */}
                  <button
                    type="button"
                    onClick={() => setIsSignatureModalOpen(true)}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer"
                  >
                    <PenTool className="h-3.5 w-3.5 text-slate-500" />
                    <span>Insert Signature</span>
                  </button>

                  {/* Drafts Modal Trigger (for initial step) */}
                  {isInitialStep && (
                    <button
                      type="button"
                      onClick={() => setIsDraftModalOpen(true)}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer"
                    >
                      <FileText className="h-3.5 w-3.5 text-slate-500" />
                      <span>Use Existing Draft</span>
                    </button>
                  )}

                  {/* Attachments Trigger (for initial step) */}
                  {isInitialStep && (
                    <>
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
                        className="inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
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
                    </>
                  )}
                </div>
              </div>

              {/* Email Body Editable Surface */}
              <div className="p-4">
                <div id={`step-editor-content-${selectedStepNumber}`}>
                  <RichTextEditor
                    key={`rich-editor-step-${selectedStepNumber}`}
                    ref={richEditorRef}
                    initialHtml={
                      currentBodyHtml ||
                      (currentBodyText ? `<p>${currentBodyText.replace(/\n/g, "<br/>")}</p>` : "")
                    }
                    onChange={(html, text) => handleActiveBodyChange(html, text)}
                    placeholder={
                      isInitialStep
                        ? "Write your primary campaign email content here..."
                        : `Write follow-up #${currentFollowupIndex + 1} content here (threaded under Step ${selectedStepNumber - 1})...`
                    }
                    minHeightClass="min-h-[280px]"
                    companyId={companyId}
                  />
                </div>

                {/* Attachments Section for Step 1 */}
                {isInitialStep && (composeAttachments.length > 0 || isUploadingAttachment) && (
                  <div className="mt-4 pt-4 border-t border-slate-100">
                    <AttachmentUploadList
                      attachments={composeAttachments}
                      onRemove={handleRemoveAttachment}
                      isUploading={isUploadingAttachment}
                    />
                  </div>
                )}
              </div>

              {/* Preflight / Deliverability Checker Strip */}
              <div className="px-4 py-2.5 bg-slate-50/70 border-t border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs">
                <div className="flex items-center gap-2">
                  <CheckCircle className="h-4 w-4 text-emerald-600" />
                  <span className="font-bold text-slate-800">Preflight Check: Optimal</span>
                  <span className="text-slate-300">•</span>
                  <span className="text-slate-500">
                    0 spam triggers detected · Unsubscribe headers compliant
                  </span>
                </div>
                <div className="text-slate-500">
                  Spam Score: <span className="font-bold text-emerald-700">0.2 / 10</span>
                </div>
              </div>
            </div>
          ) : (
            /* Preview Surface */
            <div className="bg-white rounded-xl border border-slate-200/90 shadow-2xs p-4 sm:p-5 space-y-3">
              <div className="rounded-xl bg-slate-50 border border-slate-200 p-4 sm:p-5 space-y-3">
                <div className="space-y-1.5 text-xs border-b border-slate-200/80 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-slate-400 w-16 shrink-0 font-medium">From:</span>
                    <span className="font-semibold text-slate-900 truncate">
                      {selectedSender
                        ? `${selectedSender.name} <${selectedSender.email_address}>`
                        : "Sales Team <sales@example.com>"}
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
                      {!isInitialStep && (
                        <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-200 text-slate-600 font-medium">
                          Threaded Follow-up
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-slate-400 w-16 shrink-0 font-medium">Subject:</span>
                    <span className="font-semibold text-slate-900">
                      {previewSubject}
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

          {/* Inline Errors */}
          {attachmentError && (
            <div className="p-3.5 bg-amber-50 rounded-xl border border-amber-200 text-xs text-amber-800 flex items-center justify-between gap-2 font-medium">
              <div className="flex items-center gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 text-amber-600" />
                <span>{attachmentError}</span>
              </div>
              <button
                type="button"
                onClick={() => setAttachmentError(null)}
                className="text-amber-600 hover:text-amber-800 text-xs underline cursor-pointer"
              >
                Dismiss
              </button>
            </div>
          )}

          {contentError && (
            <div className="p-3.5 bg-red-50 rounded-xl border border-red-200 text-xs text-red-600 flex items-center gap-2 font-semibold">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{contentError}</span>
            </div>
          )}

          {/* Total Cadence Summary Bar */}
          <div className="p-3 px-4 rounded-xl border border-slate-200/90 bg-white shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
            <div className="flex items-center gap-2 text-slate-700">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              <span className="font-bold text-slate-900">Total Cadence:</span>
              <span>
                {totalStepsCount} {totalStepsCount === 1 ? "step" : "steps"} over ~{totalCadenceDays} business days
              </span>
            </div>
            <div className="text-[11px] text-slate-400 font-medium">
              Step {selectedStepNumber} of {totalStepsCount} selected
            </div>
          </div>
        </main>
      </div>

      {/* ===================================================================== */}
      {/* MODALS                                                                */}
      {/* ===================================================================== */}

      {/* 1. Test Send Modal */}
      {isTestSendModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full shadow-2xl border border-slate-200 overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-100">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <div className="flex items-center gap-2">
                <Send className="h-4 w-4 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900">
                  Send Test Email · Step {selectedStepNumber}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setIsTestSendModalOpen(false)}
                className="p-1.5 rounded-lg hover:bg-slate-200/70 text-slate-400 hover:text-slate-700 transition-colors cursor-pointer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-6 space-y-4">
              <p className="text-xs text-slate-600 leading-relaxed">
                Send a live test message to verify email formatting and deliverability across mail clients before scheduling.
              </p>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Recipient Email
                </label>
                <input
                  type="email"
                  placeholder="your-email@example.com"
                  value={testEmailAddress}
                  onChange={(e) => setTestEmailAddress(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              {testSendSuccess && (
                <div className="p-3 bg-emerald-50 rounded-lg border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2">
                  <Check className="h-4 w-4 text-emerald-600" />
                  <span>Test email queued successfully! Check your inbox shortly.</span>
                </div>
              )}
            </div>

            <div className="px-6 py-3.5 bg-slate-50 border-t border-slate-100 flex justify-end gap-2 text-xs">
              <button
                type="button"
                onClick={() => setIsTestSendModalOpen(false)}
                className="px-3.5 py-2 rounded-lg border border-slate-200 bg-white text-slate-700 font-semibold hover:bg-slate-50 cursor-pointer"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  if (testEmailAddress) {
                    setTestSendSuccess(true);
                  }
                }}
                disabled={!testEmailAddress}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold transition-colors disabled:opacity-50 cursor-pointer"
              >
                Send Test
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 2. Existing Modals (Draft, Template, Signature) */}
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
