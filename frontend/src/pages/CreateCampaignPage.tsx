import { useState, useEffect, useRef, useMemo, useContext } from "react";
import DOMPurify from "dompurify";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, AlertCircle, Info, ArrowLeft, RefreshCw } from "lucide-react";

import { WorkspaceContext } from "../context/WorkspaceContext";
import { emailAccountsApi, campaignsApi, RequestError } from "../services/api";
import type { AuthorizedEmailAccount } from "../types/emails";

import { CampaignWizardHeader } from "../components/campaigns/CampaignWizardHeader";
import { CampaignWizardStepper } from "../components/campaigns/CampaignWizardStepper";
import { CampaignWizardFooter } from "../components/campaigns/CampaignWizardFooter";
import { CampaignDetailsStep } from "../components/campaigns/CampaignDetailsStep";
import { SenderSelectionStep } from "../components/campaigns/SenderSelectionStep";
import { CampaignContentStep } from "../components/campaigns/CampaignContentStep";
import { CampaignReviewStep } from "../components/campaigns/CampaignReviewStep";
import { UnsavedChangesDialog } from "../components/campaigns/UnsavedChangesDialog";

const EMPTY_ACCOUNTS: AuthorizedEmailAccount[] = [];

const scrollToTop = () => {
  if (typeof window !== "undefined") {
    try {
      window.scrollTo({ top: 0, behavior: "instant" });
    } catch {
      // Ignored in test/JSDOM environments where scrollTo is not implemented
    }
    const scrollContainers = document.querySelectorAll(".overflow-y-auto");
    scrollContainers.forEach((scrollContainer) => {
      if (scrollContainer && typeof scrollContainer.scrollTo === "function") {
        try {
          scrollContainer.scrollTo({ top: 0, behavior: "smooth" });
        } catch {
          // Ignored in test/JSDOM environments
        }
      }
    });
  }
};

import type { Campaign, CampaignCreatePayload, CampaignUpdatePayload, CampaignAttachment } from "../types/campaign";
import type { EmailTemplateItem, EmailSignatureItem } from "../types/emails";

export interface CreateCampaignPageProps {
  initialAccounts?: AuthorizedEmailAccount[];
  companyId?: number;
  campaignId?: number;
  onSaveCampaign?: (companyId: number, payload: CampaignCreatePayload) => Promise<Campaign>;
  onUpdateCampaign?: (companyId: number, campaignId: number, payload: CampaignUpdatePayload) => Promise<Campaign>;
  onNavigate?: (path: string) => void;
}

export function CreateCampaignPage({
  initialAccounts,
  companyId,
  campaignId,
  onSaveCampaign,
  onUpdateCampaign,
  onNavigate,
}: CreateCampaignPageProps = {}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const routeParams = useParams<{ campaignId?: string }>();
  const effectiveCampaignId =
    campaignId ??
    (routeParams.campaignId ? parseInt(routeParams.campaignId, 10) : undefined);
  const isEditMode = Boolean(effectiveCampaignId);

  const navigateFn = onNavigate ?? navigate;
  const saveCampaignFn = onSaveCampaign ?? campaignsApi.createCampaign;
  const updateCampaignFn = onUpdateCampaign ?? campaignsApi.updateCampaign;

  const workspaceContext = useContext(WorkspaceContext);
  const currentCompanyId = companyId ?? workspaceContext?.currentCompanyId ?? null;
  const currentRole = workspaceContext?.currentRole ?? null;
  const isMember = currentRole === "MEMBER";

  // Wizard Navigation
  const [currentStep, setCurrentStep] = useState<number>(1);
  const [showUnsavedModal, setShowUnsavedModal] = useState<boolean>(false);

  useEffect(() => {
    scrollToTop();
  }, [currentStep]);

  // Form State
  const [name, setName] = useState<string>("");
  const [subject, setSubject] = useState<string>("");
  const [selectedEmailAccountId, setSelectedEmailAccountId] = useState<number | null>(() => {
    if (initialAccounts && initialAccounts.length > 0) {
      const active = initialAccounts.find((a) => a.is_active);
      return active ? active.id : initialAccounts[0].id;
    }
    return null;
  });
  const [bodyHtml, setBodyHtml] = useState<string>("");
  const [bodyText, setBodyText] = useState<string>("");
  const [sendIntervalSeconds, setSendIntervalSeconds] = useState<number>(0);

  // Persistence & Draft Tracking
  const [draftCampaignId, setDraftCampaignId] = useState<number | null>(() => {
    return effectiveCampaignId ?? null;
  });
  const [attachments, setAttachments] = useState<CampaignAttachment[]>([]);
  const [isUploadingAttachment, setIsUploadingAttachment] = useState<boolean>(false);
  const [isDirty, setIsDirty] = useState<boolean>(false);
  const [isSaving, setIsSaving] = useState<boolean>(false);

  // Field Validation Errors
  const [errors, setErrors] = useState<{
    name?: string | null;
    subject?: string | null;
    sender?: string | null;
    content?: string | null;
  }>({});

  // Element Focus Refs for Accessible Error Recovery
  const nameInputRef = useRef<HTMLInputElement>(null);
  const subjectInputRef = useRef<HTMLInputElement>(null);

  // Notification Toast State
  const [toast, setToast] = useState<{
    message: string;
    type: "success" | "error" | "info";
  } | null>(null);

  const showToast = (message: string, type: "success" | "error" | "info" = "success") => {
    setToast({ message, type });
    setTimeout(() => {
      setToast(null);
    }, 3500);
  };

  // 1. Fetch authorized email accounts
  const {
    data: accounts = initialAccounts ?? EMPTY_ACCOUNTS,
    isLoading: isLoadingAccounts,
    isError: isAccountsError,
    refetch: refetchAccounts,
  } = useQuery<AuthorizedEmailAccount[]>({
    queryKey: ["authorizedEmailAccounts"],
    queryFn: () => emailAccountsApi.getAuthorizedAccounts(),
    initialData: initialAccounts,
    enabled: !initialAccounts,
    staleTime: 60000,
  });

  // 2. Fetch existing campaign in edit mode
  const {
    data: existingCampaign,
    isLoading: isLoadingExistingCampaign,
    isError: isExistingCampaignError,
    error: existingCampaignError,
    refetch: refetchExistingCampaign,
  } = useQuery({
    queryKey: ["campaigns", currentCompanyId, "detail", effectiveCampaignId],
    queryFn: () => {
      if (!currentCompanyId || !effectiveCampaignId) throw new Error("Missing parameters");
      return campaignsApi.getCampaign(currentCompanyId, effectiveCampaignId);
    },
    enabled: Boolean(isEditMode && currentCompanyId && effectiveCampaignId),
  });

  // Populate state from existing campaign once loaded
  const hasInitializedFromExistingRef = useRef(false);
  useEffect(() => {
    if (existingCampaign && !hasInitializedFromExistingRef.current) {
      if (existingCampaign.status === "DRAFT") {
        setName(existingCampaign.name);
        setSubject(existingCampaign.subject || "");
        if (existingCampaign.email_account_id) {
          setSelectedEmailAccountId(existingCampaign.email_account_id);
        }
        if (existingCampaign.body_html !== undefined && existingCampaign.body_html !== null) {
          setBodyHtml(existingCampaign.body_html);
        }
        if (existingCampaign.body_text !== undefined && existingCampaign.body_text !== null) {
          setBodyText(existingCampaign.body_text);
        }
        if (existingCampaign.attachments) {
          setAttachments(existingCampaign.attachments);
        }
        if (existingCampaign.send_interval_seconds !== undefined && existingCampaign.send_interval_seconds !== null) {
          setSendIntervalSeconds(existingCampaign.send_interval_seconds);
        }
        setDraftCampaignId(existingCampaign.id);
        setIsDirty(false);
      }
      hasInitializedFromExistingRef.current = true;
    }
  }, [existingCampaign]);

  // Filter accounts for current company
  const companyAccounts = useMemo(() => {
    if (!currentCompanyId) return accounts;
    return accounts.filter((a) => a.company_id === currentCompanyId);
  }, [accounts, currentCompanyId]);

  // Pre-select first active account deterministically once when accounts load (only if not already set by existing campaign)
  const hasInitializedSenderRef = useRef(false);

  useEffect(() => {
    if (!hasInitializedSenderRef.current && companyAccounts.length > 0 && !isEditMode) {
      if (selectedEmailAccountId === null) {
        const firstActive = companyAccounts.find((a) => a.is_active);
        const chosen = firstActive ? firstActive.id : companyAccounts[0].id;
        setSelectedEmailAccountId(chosen);
      }
      hasInitializedSenderRef.current = true;
    }
  }, [companyAccounts, selectedEmailAccountId, isEditMode]);

  // Selected sender account entity
  const selectedSender = useMemo(() => {
    return companyAccounts.find((a) => a.id === selectedEmailAccountId) || null;
  }, [companyAccounts, selectedEmailAccountId]);

  // Field change handlers marking dirty state
  const handleNameChange = (val: string) => {
    setName(val);
    setIsDirty(true);
    if (errors.name) {
      setErrors((prev) => ({ ...prev, name: null }));
    }
  };

  const handleSubjectChange = (val: string) => {
    setSubject(val);
    setIsDirty(true);
    if (errors.subject) {
      setErrors((prev) => ({ ...prev, subject: null }));
    }
  };

  const handleSendIntervalSecondsChange = (val: number) => {
    setSendIntervalSeconds(val);
    setIsDirty(true);
  };

  const handleSelectAccount = (accountId: number) => {
    setSelectedEmailAccountId(accountId);
    setIsDirty(true);
    if (errors.sender) {
      setErrors((prev) => ({ ...prev, sender: null }));
    }
  };

  const handleBodyChange = (html: string, text: string) => {
    setBodyHtml(html);
    setBodyText(text);
    setIsDirty(true);
    if (errors.content) {
      setErrors((prev) => ({ ...prev, content: null }));
    }
  };

  // Pure predicate validators (zero side effects, safe to evaluate during render)
  const isStep1Complete = (): boolean => {
    const trimmedName = name.trim();
    const trimmedSubject = subject.trim();
    return Boolean(trimmedName && trimmedName.length <= 80 && trimmedSubject);
  };

  const isStep2Complete = (): boolean => {
    if (!selectedEmailAccountId) return false;
    const account = companyAccounts.find((a) => a.id === selectedEmailAccountId);
    return Boolean(account && account.is_active);
  };

  const isStep3Complete = (): boolean => {
    const cleanContent = bodyHtml.replace(/<[^>]*>/g, "").trim();
    return Boolean(cleanContent || bodyText.trim());
  };

  // Interactive validation functions (updates errors state & focuses DOM, called on Continue/submit)
  const validateStep1 = (): boolean => {
    const trimmedName = name.trim();
    const trimmedSubject = subject.trim();
    let isValid = true;
    const newErrors: { name?: string | null; subject?: string | null } = {};

    if (!trimmedName) {
      newErrors.name = "Campaign name is required.";
      isValid = false;
    } else if (trimmedName.length > 80) {
      newErrors.name = "Campaign name cannot exceed 80 characters.";
      isValid = false;
    }

    if (!trimmedSubject) {
      newErrors.subject = "Subject is required.";
      isValid = false;
    }

    setErrors((prev) => ({ ...prev, ...newErrors }));

    if (!isValid) {
      if (newErrors.name) {
        nameInputRef.current?.focus();
      } else if (newErrors.subject) {
        subjectInputRef.current?.focus();
      }
    }

    return isValid;
  };

  const validateStep2 = (): boolean => {
    if (!selectedEmailAccountId) {
      setErrors((prev) => ({
        ...prev,
        sender: "Please select an authorized email account.",
      }));
      return false;
    }

    const account = companyAccounts.find((a) => a.id === selectedEmailAccountId);
    if (!account || !account.is_active) {
      setErrors((prev) => ({
        ...prev,
        sender: "Selected email account is inactive. Please select an active account.",
      }));
      return false;
    }

    setErrors((prev) => ({ ...prev, sender: null }));
    return true;
  };

  const validateStep3 = (): boolean => {
    const cleanContent = bodyHtml.replace(/<[^>]*>/g, "").trim();
    if (!cleanContent && !bodyText.trim()) {
      setErrors((prev) => ({
        ...prev,
        content: "Email content is required.",
      }));
      return false;
    }
    setErrors((prev) => ({ ...prev, content: null }));
    return true;
  };

  // Step transition checks (pure evaluation without state side effects)
  const canNavigateToStep = (targetStep: number): boolean => {
    if (targetStep <= currentStep) return true;
    if (targetStep === 2) return isStep1Complete();
    if (targetStep === 3) return isStep1Complete() && isStep2Complete();
    if (targetStep === 4) return isStep1Complete() && isStep2Complete() && isStep3Complete();
    return false;
  };

  const handleStepClick = (targetStep: number) => {
    if (targetStep === currentStep) return;
    if (targetStep < currentStep) {
      setCurrentStep(targetStep);
      scrollToTop();
      return;
    }
    if (canNavigateToStep(targetStep)) {
      setCurrentStep(targetStep);
      scrollToTop();
    }
  };

  // Save draft logic calling actual API
  const handleSaveDraft = async (): Promise<number | null> => {
    if (isSaving) return null;

    if (!currentCompanyId) {
      showToast("No active workspace company selected.", "error");
      return null;
    }

    if (!name.trim()) {
      setErrors((prev) => ({ ...prev, name: "Campaign name is required." }));
      setCurrentStep(1);
      nameInputRef.current?.focus();
      return null;
    }

    if (!selectedEmailAccountId) {
      showToast("Please choose an email account before saving.", "error");
      setCurrentStep(2);
      return null;
    }

    setIsSaving(true);
    try {
      let savedId = draftCampaignId ?? effectiveCampaignId ?? null;
      if (savedId) {
        // Update existing draft
        await updateCampaignFn(currentCompanyId, savedId, {
          name: name.trim(),
          email_account_id: selectedEmailAccountId,
          subject: subject.trim(),
          body_text: bodyText,
          body_html: bodyHtml,
          send_interval_seconds: sendIntervalSeconds,
        });
      } else {
        // Create new draft
        const created = await saveCampaignFn(currentCompanyId, {
          name: name.trim(),
          email_account_id: selectedEmailAccountId,
          subject: subject.trim(),
          body_text: bodyText,
          body_html: bodyHtml,
          send_interval_seconds: sendIntervalSeconds,
        });
        savedId = created.id;
        setDraftCampaignId(created.id);
      }

      if (currentCompanyId && savedId) {
        queryClient.invalidateQueries({
          queryKey: ["campaigns", currentCompanyId, "detail", savedId],
        });
        queryClient.invalidateQueries({
          queryKey: ["campaigns", currentCompanyId],
        });
      }

      setIsDirty(false);
      showToast("Campaign draft saved successfully.", "success");
      return savedId;
    } catch (err: unknown) {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to save campaign draft.";
      showToast(msg, "error");
      return null;
    } finally {
      setIsSaving(false);
    }
  };

  // Attachment & draft import handlers
  const handleUploadAttachment = async (file: File) => {
    if (!currentCompanyId) {
      showToast("No active workspace company selected.", "error");
      throw new Error("No active company");
    }

    let targetCampId = draftCampaignId ?? effectiveCampaignId ?? null;
    if (!targetCampId) {
      targetCampId = await handleSaveDraft();
      if (!targetCampId) {
        throw new Error("Please complete step 1 & 2 before uploading attachments.");
      }
    }

    setIsUploadingAttachment(true);
    try {
      const uploaded = await campaignsApi.uploadAttachment(currentCompanyId, targetCampId, file);
      setAttachments((prev) => [...prev, uploaded]);
      setIsDirty(true);
      showToast(`Attached "${file.name}"`, "success");
    } catch (err: unknown) {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : err instanceof Error
          ? err.message
          : "Failed to upload attachment.";
      showToast(msg, "error");
      throw new Error(msg);
    } finally {
      setIsUploadingAttachment(false);
    }
  };

  const handleDeleteAttachment = async (attachmentId: number) => {
    if (!currentCompanyId) return;
    const targetCampId = draftCampaignId ?? effectiveCampaignId ?? null;
    if (targetCampId) {
      try {
        await campaignsApi.deleteAttachment(currentCompanyId, targetCampId, attachmentId);
      } catch (err: unknown) {
        console.error("Failed to delete attachment from server:", err);
      }
    }
    setAttachments((prev) => prev.filter((a) => a.id !== attachmentId));
    setIsDirty(true);
    showToast("Attachment removed.", "info");
  };

  const handleImportDraft = async (draftId: number) => {
    if (!currentCompanyId) return;
    let targetCampId = draftCampaignId ?? effectiveCampaignId ?? null;
    if (!targetCampId) {
      targetCampId = await handleSaveDraft();
      if (!targetCampId) {
        showToast("Please complete details before importing draft.", "error");
        return;
      }
    }

    try {
      const updatedCampaign = await campaignsApi.importDraft(currentCompanyId, targetCampId, draftId);
      setSubject(updatedCampaign.subject || "");
      setBodyHtml(updatedCampaign.body_html || "");
      setBodyText(updatedCampaign.body_text || "");
      if (updatedCampaign.attachments) {
        setAttachments(updatedCampaign.attachments);
      }
      setIsDirty(true);
      showToast("Draft imported successfully.", "success");
    } catch (err: unknown) {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to import draft.";
      showToast(msg, "error");
    }
  };

  const handleSelectTemplate = (template: EmailTemplateItem) => {
    if (template.subject) {
      setSubject(template.subject);
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
    } else if (template.body_text) {
      setBodyText(template.body_text);
      setBodyHtml(`<p>${template.body_text.replace(/\n/g, "<br/>")}</p>`);
    }
    setIsDirty(true);
    showToast("Template applied.", "info");
  };

  const handleSelectSignature = (signature: EmailSignatureItem) => {
    const rawSigHtml =
      signature.body_html ||
      (signature.body_text ? `<p>${signature.body_text.replace(/\n/g, "<br/>")}</p>` : "");
    const cleanSigHtml = rawSigHtml
      ? DOMPurify.sanitize(rawSigHtml, { ADD_ATTR: ["target"] })
      : "";
    const cleanSigText = (
      signature.body_text ||
      cleanSigHtml.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ")
    ).trim();

    const isAlreadyInHtml = Boolean(cleanSigHtml && bodyHtml.includes(cleanSigHtml));
    const isAlreadyInText = Boolean(cleanSigText && bodyText && bodyText.includes(cleanSigText));

    if (!isAlreadyInHtml && !isAlreadyInText && (cleanSigHtml || cleanSigText)) {
      const updatedHtml = bodyHtml
        ? `${bodyHtml}<br/><br/>${cleanSigHtml}`
        : cleanSigHtml;
      const updatedText = bodyText
        ? `${bodyText}\n\n${cleanSigText}`
        : cleanSigText;
      setBodyHtml(updatedHtml);
      setBodyText(updatedText);
    }

    setIsDirty(true);
    showToast("Signature inserted.", "info");
  };

  // Forward Navigation
  const handleContinue = async () => {
    if (isSaving) return;

    if (currentStep === 1) {
      if (validateStep1()) {
        setCurrentStep(2);
        scrollToTop();
      }
      return;
    }

    if (currentStep === 2) {
      if (validateStep2()) {
        setCurrentStep(3);
        scrollToTop();
      }
      return;
    }

    if (currentStep === 3) {
      if (validateStep3()) {
        setCurrentStep(4);
        scrollToTop();
      }
      return;
    }

    if (currentStep === 4) {
      // Step 4 "Continue to Recipients"
      const savedCampaignId = await handleSaveDraft();
      if (savedCampaignId) {
        navigateFn(`/campaigns/${savedCampaignId}/recipients`);
      }
    }
  };

  // Backward Navigation
  const handleBack = () => {
    if (isSaving) return;
    if (currentStep > 1) {
      setCurrentStep((prev) => prev - 1);
      scrollToTop();
    } else {
      handleBackToCampaigns();
    }
  };

  // Back to Campaigns header action
  const handleBackToCampaigns = () => {
    if (isDirty) {
      setShowUnsavedModal(true);
    } else {
      if (isEditMode && effectiveCampaignId) {
        navigateFn(`/campaigns/${effectiveCampaignId}`);
      } else {
        navigateFn("/campaigns");
      }
    }
  };

  const handleConfirmDiscard = () => {
    setShowUnsavedModal(false);
    if (isEditMode && effectiveCampaignId) {
      navigateFn(`/campaigns/${effectiveCampaignId}`);
    } else {
      navigateFn("/campaigns");
    }
  };

  // Edit Mode Loading Skeleton
  if (isEditMode && isLoadingExistingCampaign) {
    return (
      <div className="w-full max-w-4xl mx-auto space-y-6 animate-pulse">
        <div className="h-6 bg-slate-200 rounded w-44"></div>
        <div className="h-10 bg-slate-200 rounded w-64"></div>
        <div className="h-14 bg-slate-200 rounded-xl"></div>
        <div className="h-72 bg-slate-200 rounded-xl"></div>
      </div>
    );
  }

  // Edit Mode Error State
  if (isEditMode && isExistingCampaignError) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center">
        <div className="bg-white rounded-xl border border-slate-200 p-8 max-w-md mx-auto shadow-sm space-y-4">
          <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto">
            <AlertCircle className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-bold text-slate-900">Campaign Not Found</h2>
          <p className="text-xs text-slate-500">
            {existingCampaignError instanceof RequestError
              ? String(existingCampaignError.detail || existingCampaignError.message)
              : `Unable to load campaign #${effectiveCampaignId}.`}
          </p>
          <div className="pt-2 flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => navigateFn("/campaigns")}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              <span>Back to Campaigns</span>
            </button>
            <button
              type="button"
              onClick={() => refetchExistingCampaign()}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-colors shadow-2xs"
            >
              <RefreshCw className="h-4 w-4" />
              <span>Retry</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Edit Mode Non-Draft State Guard
  if (isEditMode && existingCampaign && existingCampaign.status !== "DRAFT") {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center">
        <div className="bg-white rounded-xl border border-slate-200 p-8 max-w-md mx-auto shadow-sm space-y-4">
          <div className="w-12 h-12 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center mx-auto">
            <AlertCircle className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-bold text-slate-900">Editing Not Permitted</h2>
          <p className="text-xs text-slate-500">
            Only campaigns in DRAFT status may be edited. Campaign "{existingCampaign.name}" is currently {existingCampaign.status}.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={() => navigateFn(`/campaigns/${effectiveCampaignId}`)}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-colors shadow-2xs"
            >
              <span>View Campaign Details</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Edit Mode Role Guard
  if (isEditMode && isMember) {
    return (
      <div className="w-full max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12 text-center">
        <div className="bg-white rounded-xl border border-slate-200 p-8 max-w-md mx-auto shadow-sm space-y-4">
          <div className="w-12 h-12 rounded-full bg-amber-50 text-amber-600 flex items-center justify-center mx-auto">
            <AlertCircle className="h-6 w-6" />
          </div>
          <h2 className="text-lg font-bold text-slate-900">Permission Required</h2>
          <p className="text-xs text-slate-500">
            Only company owners and administrators are authorized to edit campaign drafts.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={() => navigateFn(`/campaigns/${effectiveCampaignId}`)}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-colors shadow-2xs"
            >
              <span>View Campaign Details</span>
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-4xl mx-auto space-y-4 sm:space-y-5">
      {/* 1. Wizard Header */}
      <CampaignWizardHeader
        currentStep={currentStep}
        totalSteps={4}
        onBackToCampaigns={handleBackToCampaigns}
        title={isEditMode ? "Edit Campaign Draft" : "Create Campaign"}
        subtitle={
          isEditMode
            ? "Update your draft campaign settings and content."
            : "Create and prepare your outreach campaign."
        }
      />

      {/* 2. Stepper */}
      <CampaignWizardStepper
        currentStep={currentStep}
        onStepClick={handleStepClick}
        canNavigateToStep={canNavigateToStep}
      />

      {/* 3. Active Step Panel */}
      <div className="relative">
        {currentStep === 1 && (
          <CampaignDetailsStep
            name={name}
            onNameChange={handleNameChange}
            subject={subject}
            onSubjectChange={handleSubjectChange}
            sendIntervalSeconds={sendIntervalSeconds}
            onSendIntervalSecondsChange={handleSendIntervalSecondsChange}
            nameError={errors.name}
            subjectError={errors.subject}
            nameInputRef={nameInputRef}
            subjectInputRef={subjectInputRef}
          />
        )}

        {currentStep === 2 && (
          <SenderSelectionStep
            accounts={companyAccounts}
            selectedAccountId={selectedEmailAccountId}
            onSelectAccount={handleSelectAccount}
            isLoading={isLoadingAccounts}
            isError={isAccountsError}
            onRetry={refetchAccounts}
            error={errors.sender}
          />
        )}

        {currentStep === 3 && (
          <CampaignContentStep
            subject={subject}
            bodyHtml={bodyHtml}
            bodyText={bodyText}
            onBodyHtmlChange={handleBodyChange}
            onSubjectChange={handleSubjectChange}
            selectedSender={selectedSender}
            contentError={errors.content}
            companyId={currentCompanyId}
            selectedAccountId={selectedEmailAccountId}
            attachments={attachments}
            onUploadAttachment={handleUploadAttachment}
            onDeleteAttachment={handleDeleteAttachment}
            isUploadingAttachment={isUploadingAttachment}
            onImportDraft={handleImportDraft}
            onSelectTemplate={handleSelectTemplate}
            onSelectSignature={handleSelectSignature}
          />
        )}

        {currentStep === 4 && (
          <CampaignReviewStep
            name={name}
            subject={subject}
            bodyHtml={bodyHtml}
            selectedSender={selectedSender}
            attachments={attachments}
            sendIntervalSeconds={sendIntervalSeconds}
            onEditStep={(step) => {
              setCurrentStep(step);
              scrollToTop();
            }}
          />
        )}
      </div>

      {/* 4. Wizard Footer */}
      <CampaignWizardFooter
        currentStep={currentStep}
        totalSteps={4}
        onBack={handleBack}
        onContinue={handleContinue}
        onSaveDraft={handleSaveDraft}
        isSaving={isSaving}
        isContinueDisabled={
          currentStep === 2 && companyAccounts.length === 0
        }
      />

      {/* 5. Unsaved Changes Confirmation Dialog */}
      <UnsavedChangesDialog
        isOpen={showUnsavedModal}
        onClose={() => setShowUnsavedModal(false)}
        onConfirm={handleConfirmDiscard}
      />

      {/* 6. Notification Feedback Toast */}
      {toast && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white px-4 py-2.5 rounded-lg shadow-xl flex items-center gap-2.5 text-xs font-semibold animate-in slide-in-from-bottom-2 fade-in duration-200"
        >
          {toast.type === "success" && (
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          )}
          {toast.type === "error" && (
            <AlertCircle className="h-4 w-4 text-red-400 shrink-0" />
          )}
          {toast.type === "info" && (
            <Info className="h-4 w-4 text-indigo-400 shrink-0" />
          )}
          <span>{toast.message}</span>
        </div>
      )}
    </div>
  );
}
export default CreateCampaignPage;
