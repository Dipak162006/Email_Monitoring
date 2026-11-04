import React, { useState, useMemo } from "react";
import { useParams, Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import DOMPurify from "dompurify";
import {
  ArrowLeft,
  ArrowRight,
  RefreshCw,
  Users,
  FileEdit,
  Mail,
  Send,
  Clock,
  Calendar,
  Trash2,
  PauseCircle,
  PlayCircle,
  XCircle,
  CheckCircle2,
  AlertCircle,
  AlertTriangle,
  Copy,
  Check,
  Monitor,
  Smartphone,
  Eye,
  Reply,
  Archive,
  RotateCcw,
  TrendingUp,
  BarChart2,
  PieChart,
  Lightbulb,
  Zap,
  ChevronDown,
  Info,
  Plus,
  ExternalLink,
} from "lucide-react";

import { useWorkspace } from "../hooks/useWorkspace";
import { campaignsApi, RequestError } from "../services/api";
import type {
  Campaign,
  CampaignDetail,
  CampaignPreflightResponse,
  SendingWindowConfig,
} from "../types/campaign";
import { CampaignStatusBadge } from "../components/campaigns/CampaignStatusBadge";
import {
  CancelCampaignModal,
  type CampaignModalMode,
} from "../components/campaigns/CancelCampaignModal";
import { CampaignPreflightModal } from "../components/campaigns/CampaignPreflightModal";

function formatDate(dateStr?: string | null): string {
  if (!dateStr) return "—";
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return dateStr;
  }
}

function formatSendInterval(seconds?: number | null): string {
  if (!seconds || seconds <= 0) return "No intentional delay (Immediate)";
  if (seconds % 60 === 0) {
    const mins = seconds / 60;
    return `${mins} ${mins === 1 ? "minute" : "minutes"}`;
  }
  return `${seconds} ${seconds === 1 ? "second" : "seconds"}`;
}

function formatSendingWindow(window?: SendingWindowConfig | null): string {
  if (!window?.enabled) return "Unrestricted (24/7)";
  const range = `${window.start_time} - ${window.end_time}`;
  return window.timezone ? `${range} (${window.timezone})` : range;
}

export const CampaignDetailPage: React.FC = () => {
  const { campaignId } = useParams<{ campaignId: string }>();
  const campaignIdNum = Number(campaignId);
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { currentCompanyId, currentRole } = useWorkspace();

  // Tab State: "overview" | "sequence" | "analytics"
  const currentTab = (searchParams.get("tab") as "overview" | "sequence" | "analytics") || "overview";
  const setActiveTab = (tab: "overview" | "sequence" | "analytics") => {
    setSearchParams({ tab });
  };

  // Preview & Viewport State
  const [selectedStepNumber, setSelectedStepNumber] = useState<number>(1);
  const [contentMode, setContentMode] = useState<"preview" | "html" | "plaintext">("preview");
  const [deviceView, setDeviceView] = useState<"desktop" | "mobile">("desktop");
  const [copiedSubject, setCopiedSubject] = useState<boolean>(false);
  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState<boolean>(false);

  // Toast feedback state
  const [toastMessage, setToastMessage] = useState<{
    text: string;
    type: "success" | "error" | "info";
  } | null>(null);

  const showToast = (text: string, type: "success" | "error" | "info" = "success") => {
    setToastMessage({ text, type });
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  const isAdminOrOwner = currentRole === "OWNER" || currentRole === "ADMIN";

  // Modal state for cancel / delete / archive / restore
  const [modalState, setModalState] = useState<{
    isOpen: boolean;
    campaign: Campaign | null;
    mode: CampaignModalMode;
  }>({
    isOpen: false,
    campaign: null,
    mode: "cancel",
  });

  // Query Campaign Details
  const {
    data: campaign,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery<CampaignDetail>({
    queryKey: ["campaigns", currentCompanyId, "detail", campaignIdNum],
    queryFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.getCampaign(currentCompanyId, campaignIdNum);
    },
    enabled: Boolean(currentCompanyId && campaignIdNum),
    staleTime: 0,
  });

  // Query Campaign Analytics (M7)
  const { data: analytics } = useQuery({
    queryKey: ["campaigns", currentCompanyId, "analytics", campaignIdNum],
    queryFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.getCampaignAnalytics(currentCompanyId, campaignIdNum);
    },
    enabled: Boolean(currentCompanyId && campaignIdNum),
  });

  const invalidateQueries = () => {
    queryClient.invalidateQueries({
      queryKey: ["campaigns", currentCompanyId, "detail", campaignIdNum],
    });
    queryClient.invalidateQueries({
      queryKey: ["campaigns", currentCompanyId, "analytics", campaignIdNum],
    });
    queryClient.invalidateQueries({
      queryKey: ["campaigns", currentCompanyId],
    });
  };

  // Follow-up Steps list (always sorted by step_number ascending, preserving inactive steps)
  const followupSteps = useMemo(() => {
    if (!campaign) return [];
    const raw =
      campaign.followup_steps && campaign.followup_steps.length > 0
        ? campaign.followup_steps
        : (campaign.steps || []).filter((s) => s.step_number >= 2);
    return [...raw].sort((a, b) => a.step_number - b.step_number);
  }, [campaign]);

  const totalStepsCount = 1 + followupSteps.length;

  // Step 1 item helper
  const step1Item = useMemo(() => {
    if (!campaign) return null;
    const step1 = campaign.steps?.find((s) => s.step_number === 1);
    return {
      step_number: 1,
      subject: campaign.subject || step1?.subject || "",
      body_html: campaign.body_html ?? step1?.body_html ?? null,
      body_text: campaign.body_text ?? step1?.body_text ?? null,
      delay_hours: 0,
      is_active: step1?.is_active ?? true,
    };
  }, [campaign]);

  // Persisted Step 1 content excerpt
  const step1Excerpt = useMemo(() => {
    if (!step1Item) return "No content provided.";
    if (step1Item.body_text && step1Item.body_text.trim()) {
      return step1Item.body_text.trim();
    }
    if (step1Item.body_html && step1Item.body_html.trim()) {
      const stripped = step1Item.body_html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (stripped) return stripped;
    }
    return "No content provided.";
  }, [step1Item]);

  // Active step selected for email preview (never synthesizes phantom steps)
  const activeStepItem = useMemo(() => {
    if (!campaign) return null;
    if (selectedStepNumber === 1) {
      return step1Item;
    }
    const found = followupSteps.find((s) => s.step_number === selectedStepNumber);
    if (found) return found;
    return step1Item;
  }, [campaign, selectedStepNumber, followupSteps, step1Item]);

  // Safe Sanitized HTML for active email preview
  const sanitizedActiveHtml = useMemo(() => {
    if (!activeStepItem?.body_html) return null;
    return DOMPurify.sanitize(activeStepItem.body_html, {
      ADD_TAGS: ["style"],
      ADD_ATTR: ["target"],
    });
  }, [activeStepItem?.body_html]);


  const handleCopySubject = () => {
    const sub = activeStepItem?.subject || campaign?.subject;
    if (!sub) return;
    navigator.clipboard
      .writeText(sub)
      .then(() => {
        setCopiedSubject(true);
        setTimeout(() => setCopiedSubject(false), 2000);
        showToast("Subject line copied to clipboard.");
      })
      .catch(() => {
        showToast("Failed to copy subject.", "error");
      });
  };

  // Action Modal State (Preflight & Schedule/Dispatch)
  const [actionModalState, setActionModalState] = useState<{
    isOpen: boolean;
    mode: "launch" | "schedule";
    preflight: CampaignPreflightResponse | null;
    isLoadingPreflight: boolean;
    preflightError: string | null;
  }>({
    isOpen: false,
    mode: "launch",
    preflight: null,
    isLoadingPreflight: false,
    preflightError: null,
  });

  const handleOpenActionModal = async (mode: "launch" | "schedule") => {
    if (!currentCompanyId || !campaignIdNum) return;
    setIsMoreMenuOpen(false);
    setActionModalState({
      isOpen: true,
      mode,
      preflight: null,
      isLoadingPreflight: true,
      preflightError: null,
    });
    try {
      const res = await campaignsApi.preflightCampaign(currentCompanyId, campaignIdNum);
      setActionModalState((prev) => ({
        ...prev,
        preflight: res,
        isLoadingPreflight: false,
      }));
    } catch (err: unknown) {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Preflight validation failed.";
      setActionModalState((prev) => ({
        ...prev,
        isLoadingPreflight: false,
        preflightError: msg,
      }));
    }
  };

  const handleRetryPreflight = async () => {
    if (!currentCompanyId || !campaignIdNum) return;
    setActionModalState((prev) => ({
      ...prev,
      isLoadingPreflight: true,
      preflightError: null,
    }));
    try {
      const res = await campaignsApi.preflightCampaign(currentCompanyId, campaignIdNum);
      setActionModalState((prev) => ({
        ...prev,
        preflight: res,
        isLoadingPreflight: false,
      }));
    } catch (err: unknown) {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Preflight validation failed.";
      setActionModalState((prev) => ({
        ...prev,
        isLoadingPreflight: false,
        preflightError: msg,
      }));
    }
  };

  const dispatchMutation = useMutation({
    mutationFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.dispatchCampaign(currentCompanyId, campaignIdNum);
    },
    onSuccess: (data) => {
      invalidateQueries();
      setActionModalState((prev) => ({ ...prev, isOpen: false }));
      showToast(`Campaign dispatched successfully (status: ${data.status}).`);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError ? String(err.detail || err.message) : "Failed to dispatch campaign.";
      showToast(msg, "error");
    },
  });

  const scheduleMutation = useMutation({
    mutationFn: (scheduledAtIso: string) => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      if (campaign?.status === "SCHEDULED") {
        return campaignsApi.rescheduleCampaign(currentCompanyId, campaignIdNum, {
          scheduled_at: scheduledAtIso,
        });
      }
      return campaignsApi.scheduleCampaign(currentCompanyId, campaignIdNum, {
        scheduled_at: scheduledAtIso,
      });
    },
    onSuccess: (updated) => {
      invalidateQueries();
      setActionModalState((prev) => ({ ...prev, isOpen: false }));
      const isRescheduled = campaign?.status === "SCHEDULED";
      showToast(
        isRescheduled
          ? `Campaign rescheduled for ${formatDate(updated.scheduled_at)}.`
          : `Campaign scheduled for ${formatDate(updated.scheduled_at)}.`
      );
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError ? String(err.detail || err.message) : "Failed to schedule campaign.";
      showToast(msg, "error");
    },
  });

  const pauseMutation = useMutation({
    mutationFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.pauseCampaign(currentCompanyId, campaignIdNum);
    },
    onSuccess: (updated) => {
      invalidateQueries();
      showToast(`Campaign "${updated.name}" paused.`);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError ? String(err.detail || err.message) : "Failed to pause campaign.";
      showToast(msg, "error");
    },
  });

  const resumeMutation = useMutation({
    mutationFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.resumeCampaign(currentCompanyId, campaignIdNum);
    },
    onSuccess: (updated) => {
      invalidateQueries();
      showToast(`Campaign "${updated.name}" resumed.`);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError ? String(err.detail || err.message) : "Failed to resume campaign.";
      showToast(msg, "error");
    },
  });

  const cancelMutation = useMutation({
    mutationFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.cancelCampaign(currentCompanyId, campaignIdNum);
    },
    onSuccess: (updated) => {
      setModalState({ isOpen: false, campaign: null, mode: "cancel" });
      invalidateQueries();
      showToast(`Campaign "${updated.name}" cancelled.`);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError ? String(err.detail || err.message) : "Failed to cancel campaign.";
      showToast(msg, "error");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.deleteCampaign(currentCompanyId, campaignIdNum);
    },
    onSuccess: () => {
      setModalState({ isOpen: false, campaign: null, mode: "delete" });
      invalidateQueries();
      navigate("/campaigns");
    },
    onError: (err: unknown) => {
      setModalState({ isOpen: false, campaign: null, mode: "delete" });
      const msg =
        err instanceof RequestError ? String(err.detail || err.message) : "Failed to delete campaign.";
      showToast(msg, "error");
    },
  });

  const archiveMutation = useMutation({
    mutationFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.archiveCampaign(currentCompanyId, campaignIdNum);
    },
    onSuccess: (updated) => {
      setModalState({ isOpen: false, campaign: null, mode: "archive" });
      invalidateQueries();
      showToast(`Campaign "${updated.name}" archived.`);
    },
    onError: (err: unknown) => {
      setModalState({ isOpen: false, campaign: null, mode: "archive" });
      const msg =
        err instanceof RequestError ? String(err.detail || err.message) : "Failed to archive campaign.";
      showToast(msg, "error");
    },
  });

  const restoreMutation = useMutation({
    mutationFn: () => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.restoreCampaign(currentCompanyId, campaignIdNum);
    },
    onSuccess: (updated) => {
      setModalState({ isOpen: false, campaign: null, mode: "restore" });
      invalidateQueries();
      showToast(`Campaign "${updated.name}" restored.`);
    },
    onError: (err: unknown) => {
      setModalState({ isOpen: false, campaign: null, mode: "restore" });
      const msg =
        err instanceof RequestError ? String(err.detail || err.message) : "Failed to restore campaign.";
      showToast(msg, "error");
    },
  });

  const handleOpenCancelModal = () => {
    if (!campaign) return;
    setIsMoreMenuOpen(false);
    setModalState({ isOpen: true, campaign, mode: "cancel" });
  };

  const handleOpenDeleteModal = () => {
    if (!campaign) return;
    setIsMoreMenuOpen(false);
    setModalState({ isOpen: true, campaign, mode: "delete" });
  };

  const handleOpenArchiveModal = () => {
    if (!campaign) return;
    setIsMoreMenuOpen(false);
    setModalState({ isOpen: true, campaign, mode: "archive" });
  };

  const handleOpenRestoreModal = () => {
    if (!campaign) return;
    setIsMoreMenuOpen(false);
    setModalState({ isOpen: true, campaign, mode: "restore" });
  };

  const handleConfirmModal = () => {
    if (modalState.mode === "cancel") {
      cancelMutation.mutate();
    } else if (modalState.mode === "delete") {
      deleteMutation.mutate();
    } else if (modalState.mode === "archive") {
      archiveMutation.mutate();
    } else if (modalState.mode === "restore") {
      restoreMutation.mutate();
    }
  };

  // 1. Loading Skeleton State
  if (isLoading) {
    return (
      <div className="w-full max-w-7xl mx-auto min-w-0 px-4 sm:px-6 lg:px-8 py-6 space-y-5 animate-pulse box-border">
        <div className="h-4 bg-slate-200 rounded w-36"></div>
        <div className="bg-white rounded-xl border border-slate-200 p-6 flex justify-between items-center">
          <div className="space-y-2">
            <div className="h-7 bg-slate-200 rounded w-64"></div>
            <div className="h-4 bg-slate-100 rounded w-96"></div>
          </div>
          <div className="flex gap-2">
            <div className="h-9 bg-slate-200 rounded w-24"></div>
            <div className="h-9 bg-slate-200 rounded w-28"></div>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-32 bg-white rounded-xl border border-slate-200 p-4"></div>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <div className="h-72 bg-white rounded-xl border border-slate-200 p-4"></div>
          <div className="h-72 bg-white rounded-xl border border-slate-200 p-4"></div>
        </div>
      </div>
    );
  }

  // 2. Error / Not Found State
  if (isError || !campaign) {
    const isNotFound = error instanceof RequestError ? error.status === 404 : false;

    return (
      <div className="w-full max-w-7xl mx-auto min-w-0 px-4 sm:px-6 lg:px-8 py-12 box-border">
        <div className="bg-white rounded-xl border border-slate-200 p-8 sm:p-12 text-center max-w-lg mx-auto shadow-sm space-y-4">
          <div className="w-14 h-14 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto">
            {isNotFound ? <AlertTriangle className="h-7 w-7" /> : <AlertCircle className="h-7 w-7" />}
          </div>
          <h2 className="text-lg sm:text-xl font-bold text-slate-900">
            {isNotFound ? "Campaign Not Found" : "Unable to load campaign details"}
          </h2>
          <p className="text-xs sm:text-sm text-slate-500">
            {isNotFound
              ? `Campaign #${campaignIdNum} does not exist or may have been deleted.`
              : error instanceof RequestError
              ? String(error.detail || error.message)
              : "A network or server error occurred while retrieving campaign details."}
          </p>
          <div className="pt-2 flex items-center justify-center gap-3">
            <Link
              to="/campaigns"
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs sm:text-sm font-semibold transition-colors"
            >
              <ArrowLeft className="h-4 w-4" />
              <span>Back to Campaigns</span>
            </Link>
            {!isNotFound && (
              <button
                type="button"
                onClick={() => refetch()}
                className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs sm:text-sm font-semibold transition-colors shadow-2xs"
              >
                <RefreshCw className="h-4 w-4" />
                <span>Retry</span>
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  const senderName = campaign.email_account_name || "Assigned Account";
  const senderEmail = campaign.email_account_address || `Account #${campaign.email_account_id}`;
  const senderDomain = senderEmail.includes("@") ? senderEmail.split("@")[1] : "—";
  const isDraft = campaign.status === "DRAFT";

  // Rate calculations
  const totalTarget = campaign.recipient_count || 0;
  const sentCount = campaign.sent_count ?? 0;
  const repliedCount = campaign.replied_count ?? 0;
  const bouncedCount = campaign.bounced_count ?? 0;
  const failedCount = campaign.failed_count ?? 0;
  const suppressedCount = campaign.suppressed_count ?? 0;
  const pendingCount =
    campaign.pending_count !== undefined
      ? campaign.pending_count
      : Math.max(0, totalTarget - sentCount - bouncedCount - failedCount - suppressedCount);

  const initialSentCount = analytics?.initial_sent_count ?? campaign.initial_sent_count ?? sentCount;
  const followupSentCount = analytics?.followup_sent_count ?? campaign.followup_sent_count ?? 0;
  const totalSentCount = analytics?.total_sent_count ?? campaign.total_sent_count ?? (initialSentCount + followupSentCount);
  const uniqueRepliedCount = analytics?.unique_replied_count ?? campaign.unique_replied_count ?? repliedCount;

  const sentRate = totalTarget > 0 ? Math.round((initialSentCount / totalTarget) * 100) : 0;
  const replyRate = initialSentCount > 0 ? Math.round((uniqueRepliedCount / initialSentCount) * 100) : 0;
  const bounceRate = totalSentCount > 0 ? Math.round((bouncedCount / totalSentCount) * 100) : 0;
  const failedRate = totalSentCount > 0 ? Math.round((failedCount / totalSentCount) * 100) : 0;

  const step1Analytics = analytics?.steps?.find((s) => s.step_number === 1);
  const initialBounced = step1Analytics?.bounced_count ?? Math.min(bouncedCount, Math.max(0, totalTarget - initialSentCount));
  const initialFailed = step1Analytics?.failed_count ?? Math.min(failedCount, Math.max(0, totalTarget - initialSentCount - initialBounced));
  const initialSuppressed = Math.min(suppressedCount, Math.max(0, totalTarget - initialSentCount - initialBounced - initialFailed));
  const processedCount = initialSentCount + initialBounced + initialSuppressed + initialFailed;
  const completionPercent = totalTarget > 0 ? Math.min(100, Math.round((processedCount / totalTarget) * 100)) : 0;

  return (
    <div className="w-full max-w-7xl mx-auto min-w-0 px-4 sm:px-6 lg:px-8 py-5 space-y-4 sm:space-y-5 box-border">
      {/* 1. Compact Navigation Breadcrumb */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <Link
            to="/campaigns"
            className="inline-flex items-center gap-1.5 text-xs sm:text-sm font-medium text-slate-500 hover:text-indigo-600 transition-colors"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Campaigns</span>
          </Link>
        </div>

        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white hover:bg-slate-50 text-slate-600 text-xs font-medium border border-slate-200/80 shadow-2xs transition-all disabled:opacity-50"
          title="Refresh Campaign Data"
        >
          <RefreshCw className={`h-3 w-3 text-indigo-600 ${isFetching ? "animate-spin" : ""}`} />
          <span className="hidden sm:inline">Refresh</span>
        </button>
      </div>

      {/* Archived Banner */}
      {campaign.status === "ARCHIVED" && (
        <div className="w-full bg-amber-50/90 border border-amber-200/80 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-amber-900 shadow-2xs">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-amber-100 flex items-center justify-center text-amber-700 shrink-0">
              <Archive className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-semibold">This campaign is archived</p>
              <p className="text-xs text-amber-700">
                All sending and schedule triggers are stopped. Campaign history, steps, and recipient logs are preserved.
              </p>
            </div>
          </div>
          {isAdminOrOwner && (
            <button
              type="button"
              onClick={handleOpenRestoreModal}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-2xs transition-colors shrink-0"
            >
              <RotateCcw className="h-4 w-4" />
              <span>Restore Campaign</span>
            </button>
          )}
        </div>
      )}

      {/* 2. Compact Modern Campaign Header */}
      <header className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs min-w-0">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 min-w-0">
          {/* Left: Icon, Name, Badges, Metadata */}
          <div className="flex items-start gap-3.5 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center shrink-0 shadow-sm mt-0.5">
              <Mail className="h-5 w-5" />
            </div>

            <div className="space-y-1.5 min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight truncate">
                  {campaign.name}
                </h1>
                {isDraft && isAdminOrOwner && (
                  <Link
                    to={`/campaigns/${campaign.id}/edit`}
                    className="p-1 rounded text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 transition-colors"
                    title="Edit Campaign Name & Details"
                  >
                    <FileEdit className="h-3.5 w-3.5" />
                  </Link>
                )}
                <CampaignStatusBadge status={campaign.status} />
                <span className="px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-semibold text-xs border border-indigo-100">
                  {campaign.recipient_count.toLocaleString()} {campaign.recipient_count === 1 ? "recipient" : "recipients"}
                </span>
              </div>

              {/* Metadata Subtitle Row */}
              <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
                <span>Created {formatDate(campaign.created_at)}</span>
                <span className="text-slate-300">•</span>
                <span>Last modified {formatDate(campaign.updated_at)}</span>
                <span className="text-slate-300">•</span>
                <span className="font-mono text-slate-600 font-medium">ID: #{campaign.id}</span>
                {campaign.scheduled_at && (
                  <>
                    <span className="text-slate-300">•</span>
                    <span className="text-amber-700 font-semibold">
                      Scheduled: {formatDate(campaign.scheduled_at)}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Right Action Buttons */}
          <div className="flex items-center gap-2 flex-wrap shrink-0">
            {/* DRAFT Actions */}
            {isDraft && isAdminOrOwner && (
              <>
                <Link
                  to={`/campaigns/${campaign.id}/edit`}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-xs font-semibold shadow-2xs transition-colors"
                >
                  <FileEdit className="h-3.5 w-3.5 text-slate-500" />
                  <span>Edit Draft</span>
                </Link>
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("schedule")}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-xs font-semibold shadow-2xs transition-colors cursor-pointer"
                >
                  <Calendar className="h-3.5 w-3.5 text-slate-500" />
                  <span>Schedule</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("launch")}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-2xs transition-colors cursor-pointer"
                >
                  <Send className="h-3.5 w-3.5" />
                  <span>Launch Now</span>
                </button>
              </>
            )}

            {/* SCHEDULED Actions */}
            {campaign.status === "SCHEDULED" && isAdminOrOwner && (
              <>
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("schedule")}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-xs font-semibold shadow-2xs transition-colors cursor-pointer"
                >
                  <Calendar className="h-3.5 w-3.5 text-slate-500" />
                  <span>Reschedule</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("launch")}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-2xs transition-colors cursor-pointer"
                >
                  <Send className="h-3.5 w-3.5" />
                  <span>Launch Now</span>
                </button>
                <button
                  type="button"
                  onClick={handleOpenCancelModal}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-50 border border-rose-200 hover:bg-rose-100 text-rose-700 text-xs font-semibold transition-colors shadow-2xs cursor-pointer"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  <span>Stop Campaign</span>
                </button>
              </>
            )}

            {/* RUNNING Actions */}
            {campaign.status === "RUNNING" && isAdminOrOwner && (
              <>
                <button
                  type="button"
                  onClick={() => pauseMutation.mutate()}
                  disabled={pauseMutation.isPending}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-200 hover:bg-amber-100 text-amber-700 text-xs font-semibold transition-colors shadow-2xs disabled:opacity-50 cursor-pointer"
                >
                  <PauseCircle className="h-3.5 w-3.5" />
                  <span>Pause</span>
                </button>
                <button
                  type="button"
                  onClick={handleOpenCancelModal}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-rose-50 border border-rose-200 hover:bg-rose-100 text-rose-700 text-xs font-semibold transition-colors shadow-2xs cursor-pointer"
                >
                  <XCircle className="h-3.5 w-3.5" />
                  <span>Cancel</span>
                </button>
              </>
            )}

            {/* PAUSED Actions */}
            {campaign.status === "PAUSED" && isAdminOrOwner && (
              <button
                type="button"
                onClick={() => resumeMutation.mutate()}
                disabled={resumeMutation.isPending}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 text-indigo-700 text-xs font-semibold transition-colors shadow-2xs disabled:opacity-50 cursor-pointer"
              >
                <PlayCircle className="h-3.5 w-3.5" />
                <span>Resume</span>
              </button>
            )}

            {/* ARCHIVED Actions */}
            {campaign.status === "ARCHIVED" && isAdminOrOwner && (
              <>
                <button
                  type="button"
                  onClick={handleOpenRestoreModal}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-indigo-200 hover:bg-indigo-50 text-indigo-600 text-xs font-semibold transition-colors shadow-2xs cursor-pointer"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  <span>Restore</span>
                </button>
                <button
                  type="button"
                  onClick={handleOpenDeleteModal}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-rose-200 hover:bg-rose-50 text-rose-600 text-xs font-semibold transition-colors shadow-2xs cursor-pointer"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  <span>Delete Permanently</span>
                </button>
              </>
            )}

            {/* Secondary 'More' Dropdown */}
            {isAdminOrOwner && campaign.status !== "ARCHIVED" && (
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setIsMoreMenuOpen((prev) => !prev)}
                  className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 text-xs font-semibold shadow-2xs transition-colors cursor-pointer"
                  aria-expanded={isMoreMenuOpen}
                  aria-label="More campaign actions"
                >
                  <span>More</span>
                  <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
                </button>

                {isMoreMenuOpen && (
                  <div
                    className="absolute right-0 mt-1.5 w-44 bg-white rounded-xl shadow-lg border border-slate-200 py-1 z-30 animate-in fade-in zoom-in-95 duration-100"
                    onMouseLeave={() => setIsMoreMenuOpen(false)}
                  >
                    {["RUNNING", "PAUSED", "SCHEDULED", "QUEUED"].includes(campaign.status) && (
                      <button
                        type="button"
                        onClick={handleOpenCancelModal}
                        className="w-full text-left px-3.5 py-2 text-xs font-medium text-rose-600 hover:bg-rose-50 flex items-center gap-2 cursor-pointer"
                      >
                        <XCircle className="h-3.5 w-3.5" />
                        <span>Cancel Campaign</span>
                      </button>
                    )}

                    {["DRAFT", "COMPLETED", "CANCELLED", "FAILED"].includes(campaign.status) && (
                      <button
                        type="button"
                        onClick={handleOpenArchiveModal}
                        className="w-full text-left px-3.5 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 flex items-center gap-2 cursor-pointer"
                      >
                        <Archive className="h-3.5 w-3.5 text-slate-400" />
                        <span>Archive Campaign</span>
                      </button>
                    )}

                    {["DRAFT", "COMPLETED", "CANCELLED", "FAILED"].includes(campaign.status) && (
                      <button
                        type="button"
                        onClick={handleOpenDeleteModal}
                        className="w-full text-left px-3.5 py-2 text-xs font-medium text-rose-600 hover:bg-rose-50 flex items-center gap-2 cursor-pointer border-t border-slate-100"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        <span>Delete Draft</span>
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </header>

      {/* 3. Compact 3-Tab Navigation Bar */}
      <div className="flex items-center justify-between border-b border-slate-200/80 gap-4 flex-wrap">
        <nav className="flex items-center gap-6" aria-label="Campaign Detail Tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={currentTab === "overview"}
            aria-controls="panel-overview"
            onClick={() => setActiveTab("overview")}
            className={`pb-2.5 text-xs sm:text-sm font-semibold transition-all relative cursor-pointer ${
              currentTab === "overview"
                ? "text-indigo-600 border-b-2 border-indigo-600"
                : "text-slate-500 hover:text-slate-900 border-b-2 border-transparent"
            }`}
          >
            Overview
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={currentTab === "sequence"}
            aria-controls="panel-sequence"
            onClick={() => setActiveTab("sequence")}
            className={`pb-2.5 text-xs sm:text-sm font-semibold transition-all relative cursor-pointer ${
              currentTab === "sequence"
                ? "text-indigo-600 border-b-2 border-indigo-600"
                : "text-slate-500 hover:text-slate-900 border-b-2 border-transparent"
            }`}
          >
            Email Sequence
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={currentTab === "analytics"}
            aria-controls="panel-analytics"
            onClick={() => setActiveTab("analytics")}
            className={`pb-2.5 text-xs sm:text-sm font-semibold transition-all relative cursor-pointer ${
              currentTab === "analytics"
                ? "text-indigo-600 border-b-2 border-indigo-600"
                : "text-slate-500 hover:text-slate-900 border-b-2 border-transparent"
            }`}
          >
            Analytics
          </button>
        </nav>

        {currentTab === "analytics" && (
          <div className="pb-1.5 flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-white border border-slate-200 text-xs text-slate-700 font-medium shadow-2xs" title="Metrics represent full campaign lifetime totals">
              <Calendar className="h-3 w-3 text-slate-400" />
              <span>Campaign Lifetime</span>
            </span>
          </div>
        )}
      </div>

      {/* =========================================================================
          TAB 1: OVERVIEW TAB CONTENT
          ========================================================================= */}
      {currentTab === "overview" && (
        <div className="space-y-4 sm:space-y-5">
          {/* Row 1: 4 Balanced Summary Cards (Sender, Schedule, Audience, Quick Stats) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-stretch">
            {/* Card 1: Sender Identity */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs flex flex-col justify-between space-y-3">
              <div>
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                      <Send className="h-3.5 w-3.5" />
                    </div>
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">Sender Identity</h3>
                  </div>
                  <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold">
                    Active
                  </span>
                </div>
                <div className="mt-2.5 space-y-1">
                  <p className="text-xs sm:text-sm font-semibold text-slate-900 truncate" title={senderName}>
                    {senderName}
                  </p>
                  <p className="text-xs text-slate-500 truncate" title={senderEmail}>
                    {senderEmail}
                  </p>
                  <div className="pt-2 flex items-center justify-between text-xs text-slate-500">
                    <span>Domain</span>
                    <span className="font-medium text-slate-800">{senderDomain}</span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>Account ID</span>
                    <span className="font-mono text-slate-700">#{campaign.email_account_id}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Card 2: Schedule & Timing */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs flex flex-col justify-between space-y-3">
              <div>
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                      <Clock className="h-3.5 w-3.5" />
                    </div>
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">Schedule & Timing</h3>
                  </div>
                  <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold">
                    {campaign.scheduled_at ? "Scheduled" : isDraft ? "On-Demand" : campaign.status}
                  </span>
                </div>
                <div className="mt-2.5 space-y-1">
                  <p className="text-xs sm:text-sm font-semibold text-slate-900 truncate">
                    {campaign.scheduled_at ? "Scheduled Dispatch" : isDraft ? "Manual Dispatch" : campaign.status}
                  </p>
                  <p className="text-[11px] text-slate-500 truncate">
                    {campaign.scheduled_at
                      ? `Execution set for ${formatDate(campaign.scheduled_at)}`
                      : isDraft
                      ? "Requires final review before queue ingestion."
                      : `Campaign in ${campaign.status} lifecycle`}
                  </p>
                  <div className="pt-2 flex items-center justify-between text-xs text-slate-500">
                    <span>Sending Interval</span>
                    <span className="font-medium text-slate-800">{formatSendInterval(campaign.send_interval_seconds)}</span>
                  </div>
                  {campaign.next_send_at && (
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span>Next Recipient</span>
                      <span className="font-medium text-slate-800">{formatDate(campaign.next_send_at)}</span>
                    </div>
                  )}
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>Sending Window</span>
                    <span className="font-medium text-slate-800" data-testid="detail-sending-window">
                      {formatSendingWindow(campaign.sending_window)}
                    </span>
                  </div>
                  {campaign.sending_window?.enabled && campaign.sending_window.timezone && (
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span>Timezone</span>
                      <span className="font-medium text-slate-800" data-testid="detail-timezone">
                        {campaign.sending_window.timezone}
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Card 3: Target Audience */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs flex flex-col justify-between space-y-3">
              <div>
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                      <Users className="h-3.5 w-3.5" />
                    </div>
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">Target Audience</h3>
                  </div>
                  <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold">
                    Verified
                  </span>
                </div>
                <div className="mt-2.5 space-y-1">
                  <p className="text-xl sm:text-2xl font-bold text-slate-900 leading-none">
                    {campaign.recipient_count.toLocaleString()}
                  </p>
                  <p className="text-[11px] text-slate-500">Total recipients</p>
                  <div className="pt-2 flex items-center justify-between text-xs text-slate-500">
                    <span>Scope</span>
                    <span className="font-medium text-slate-800">Company Isolated</span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>Status</span>
                    <span className="font-semibold text-indigo-600">Audience Configured</span>
                  </div>
                </div>
              </div>
              <div className="pt-1.5 border-t border-slate-100">
                <Link
                  to={`/campaigns/${campaign.id}/recipients`}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 hover:underline"
                >
                  <span>Manage Recipients</span>
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </div>

            {/* Card 4: Quick Stats (Last 7 days) */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs flex flex-col justify-between space-y-3">
              <div>
                <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                      <BarChart2 className="h-3.5 w-3.5" />
                    </div>
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">Quick Stats</h3>
                  </div>
                  <span className="text-[10px] font-medium text-slate-500 flex items-center gap-1 bg-slate-50 px-2 py-0.5 rounded border border-slate-100" title="Cumulative campaign lifetime metrics">
                    <span>Campaign Lifetime</span>
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 mt-2.5">
                  <div className="bg-slate-50/70 p-2 rounded-lg border border-slate-100">
                    <div className="flex items-center justify-between text-slate-400">
                      <span className="text-[10px] font-medium text-slate-500">Initial Sent</span>
                      <Send className="h-3 w-3 text-emerald-500" />
                    </div>
                    <p className="text-sm font-bold text-slate-900 mt-0.5">{initialSentCount}</p>
                  </div>

                  <div className="bg-slate-50/70 p-2 rounded-lg border border-slate-100">
                    <div className="flex items-center justify-between text-slate-400">
                      <span className="text-[10px] font-medium text-slate-500">Replied</span>
                      <Reply className="h-3 w-3 text-indigo-500" />
                    </div>
                    <div className="flex items-baseline gap-1 mt-0.5">
                      <p className="text-sm font-bold text-slate-900">{repliedCount}</p>
                      <span className="text-[10px] text-slate-400">{replyRate}%</span>
                    </div>
                  </div>

                  <div className="bg-slate-50/70 p-2 rounded-lg border border-slate-100">
                    <div className="flex items-center justify-between text-slate-400">
                      <span className="text-[10px] font-medium text-slate-500">Bounced</span>
                      <AlertTriangle className="h-3 w-3 text-rose-500" />
                    </div>
                    <div className="flex items-baseline gap-1 mt-0.5">
                      <p className="text-sm font-bold text-slate-900">{bouncedCount}</p>
                      <span className="text-[10px] text-slate-400">{bounceRate}%</span>
                    </div>
                  </div>

                  <div className="bg-slate-50/70 p-2 rounded-lg border border-slate-100">
                    <div className="flex items-center justify-between text-slate-400">
                      <span className="text-[10px] font-medium text-slate-500">Failed</span>
                      <AlertCircle className="h-3 w-3 text-amber-500" />
                    </div>
                    <div className="flex items-baseline gap-1 mt-0.5">
                      <p className="text-sm font-bold text-slate-900">{failedCount}</p>
                      <span className="text-[10px] text-slate-400">{failedRate}%</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Row 2: Email Sequence Timeline (Left) & Email Preview (Right) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5 items-start">
            {/* Left: Email Sequence Timeline */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs flex flex-col space-y-4">
              <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <Mail className="h-3.5 w-3.5" />
                  </div>
                  <h3 className="text-xs sm:text-sm font-bold text-slate-900">Email Sequence</h3>
                  <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-[10px] font-bold border border-indigo-100">
                    {totalStepsCount} Steps
                  </span>
                </div>

                {isDraft && isAdminOrOwner && (
                  <Link
                    to={`/campaigns/${campaign.id}/edit`}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 hover:underline"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Add Follow-Up</span>
                  </Link>
                )}
              </div>

              {/* Connected Timeline */}
              <div className="relative pl-7 space-y-4">
                {/* Vertical timeline line */}
                <div className="absolute left-2.5 top-3 bottom-3 w-0.5 bg-slate-200" />

                {/* Step 1: Initial Outreach */}
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setSelectedStepNumber(1)}
                    className={`absolute -left-7 top-1.5 w-5 h-5 rounded-full font-bold text-[10px] flex items-center justify-center z-10 transition-all cursor-pointer ${
                      selectedStepNumber === 1
                        ? "bg-indigo-600 text-white ring-4 ring-indigo-50"
                        : "bg-slate-200 text-slate-600 hover:bg-slate-300"
                    }`}
                  >
                    1
                  </button>

                  <div
                    onClick={() => setSelectedStepNumber(1)}
                    className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-1.5 ${
                      selectedStepNumber === 1
                        ? "bg-indigo-50/40 border-indigo-200/90 shadow-2xs"
                        : "bg-slate-50/60 border-slate-200/80 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <div className="flex items-center gap-2">
                        <Mail className="h-3.5 w-3.5 text-indigo-600" />
                        <span className="font-bold text-xs text-slate-900">Initial Outreach</span>
                        <span className="text-[10px] font-semibold text-emerald-600 flex items-center gap-0.5">
                          <Zap className="h-2.5 w-2.5 fill-emerald-600" /> Immediate
                        </span>
                        {step1Item?.is_active === false ? (
                          <span className="text-[10px] font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200" data-testid="step-1-status">
                            Inactive
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100" data-testid="step-1-status">
                            Active
                          </span>
                        )}
                      </div>
                    </div>
                    <p className="text-xs font-semibold text-slate-800 truncate">
                      <span>Subject: </span>
                      <span className="font-semibold text-slate-800">
                        {step1Item?.subject || "No subject set"}
                      </span>
                    </p>
                    <p className="text-[11px] text-slate-500 line-clamp-2 leading-relaxed">
                      {step1Excerpt}
                    </p>
                  </div>
                </div>

                {/* Step 2..N: Follow-up Steps */}
                {followupSteps.map((step, idx) => {
                  const isDays = step.delay_hours >= 24 && step.delay_hours % 24 === 0;
                  const delayText = isDays
                    ? `${step.delay_hours / 24} day${step.delay_hours / 24 > 1 ? "s" : ""}`
                    : `${step.delay_hours} hour${step.delay_hours > 1 ? "s" : ""}`;
                  const isSelected = selectedStepNumber === step.step_number;

                  return (
                    <div key={step.id || step.step_number || idx} className="relative">
                      <button
                        type="button"
                        onClick={() => setSelectedStepNumber(step.step_number)}
                        className={`absolute -left-7 top-1.5 w-5 h-5 rounded-full font-bold text-[10px] flex items-center justify-center z-10 transition-all cursor-pointer ${
                          isSelected
                            ? "bg-indigo-600 text-white ring-4 ring-indigo-50"
                            : "bg-slate-200 text-slate-600 hover:bg-slate-300"
                        }`}
                      >
                        {step.step_number}
                      </button>

                      <div
                        onClick={() => setSelectedStepNumber(step.step_number)}
                        className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-1.5 ${
                          isSelected
                            ? "bg-indigo-50/40 border-indigo-200/90 shadow-2xs"
                            : "bg-slate-50/60 border-slate-200/80 hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-2">
                            <Mail className="h-3.5 w-3.5 text-indigo-600" />
                            <span className="font-bold text-xs text-slate-900">
                              Follow-Up #{idx + 1}
                            </span>
                            <span className="text-[10px] text-slate-600 flex items-center gap-1 font-medium bg-white px-2 py-0.5 rounded border border-slate-200/60">
                              <Clock className="h-2.5 w-2.5 text-slate-400" />
                              <span>Waits {delayText} if no reply</span>
                            </span>
                            {step.is_active === false ? (
                              <span className="text-[10px] font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200" data-testid={`step-${step.step_number}-status`}>
                                Inactive
                              </span>
                            ) : (
                              <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100" data-testid={`step-${step.step_number}-status`}>
                                Active
                              </span>
                            )}
                          </div>
                        </div>
                        <p className="text-xs font-semibold text-slate-800 truncate">
                          Subject: {step.subject || `Re: ${campaign.subject || "Campaign"}`}
                        </p>
                        <p className="text-[11px] text-slate-500 line-clamp-2 leading-relaxed">
                          {step.body_text ||
                            (step.body_html
                              ? step.body_html.replace(/<[^>]+>/g, " ").trim()
                              : "No content provided.")}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Right: Email Preview Box */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs flex flex-col space-y-3.5">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <Eye className="h-3.5 w-3.5" />
                  </div>
                  <h3 className="text-xs sm:text-sm font-bold text-slate-900">Email Preview</h3>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  {/* Step Switcher Buttons */}
                  <div className="inline-flex p-0.5 rounded-lg bg-slate-100 text-xs font-medium border border-slate-200">
                    <button
                      type="button"
                      onClick={() => setSelectedStepNumber(1)}
                      className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                        selectedStepNumber === 1
                          ? "bg-indigo-600 text-white font-semibold shadow-2xs"
                          : "text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      Initial Outreach
                    </button>
                    {followupSteps.map((s, idx) => (
                      <button
                        key={s.step_number || idx}
                        type="button"
                        onClick={() => setSelectedStepNumber(s.step_number)}
                        className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                          selectedStepNumber === s.step_number
                            ? "bg-indigo-600 text-white font-semibold shadow-2xs"
                            : "text-slate-600 hover:text-slate-900"
                        }`}
                      >
                        Follow-Up #{idx + 1}
                      </button>
                    ))}
                  </div>

                  {/* Device Viewport Toggle */}
                  <div className="inline-flex p-0.5 rounded-lg bg-slate-100 text-slate-600 border border-slate-200">
                    <button
                      type="button"
                      onClick={() => setDeviceView("desktop")}
                      className={`p-1 rounded-md transition-all cursor-pointer ${
                        deviceView === "desktop" ? "bg-white text-slate-900 shadow-2xs" : "hover:text-slate-900"
                      }`}
                      title="Desktop Viewport"
                    >
                      <Monitor className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeviceView("mobile")}
                      className={`p-1 rounded-md transition-all cursor-pointer ${
                        deviceView === "mobile" ? "bg-white text-slate-900 shadow-2xs" : "hover:text-slate-900"
                      }`}
                      title="Mobile Viewport"
                    >
                      <Smartphone className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              {/* View Format Segmented Controls (Formatted, HTML, Plaintext) */}
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  <span className="text-xs font-semibold text-slate-500 uppercase shrink-0">Subject:</span>
                  <span className="text-xs sm:text-sm font-semibold text-slate-900 truncate">
                    {activeStepItem?.subject || "No subject set"}
                  </span>
                  <button
                    type="button"
                    onClick={handleCopySubject}
                    className="inline-flex items-center gap-1 p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                    title="Copy Subject Line"
                  >
                    {copiedSubject ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-emerald-600" />
                        <span className="text-[11px] font-semibold text-emerald-600">Copied!</span>
                      </>
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>

                <div className="inline-flex p-0.5 rounded-lg bg-slate-100 text-[11px] font-medium border border-slate-200 shrink-0">
                  <button
                    type="button"
                    onClick={() => setContentMode("preview")}
                    className={`px-2 py-0.5 rounded transition-all cursor-pointer ${
                      contentMode === "preview" ? "bg-white text-slate-900 font-semibold shadow-2xs" : "text-slate-600"
                    }`}
                  >
                    Formatted Preview
                  </button>
                  <button
                    type="button"
                    onClick={() => setContentMode("html")}
                    className={`px-2 py-0.5 rounded transition-all cursor-pointer ${
                      contentMode === "html" ? "bg-white text-slate-900 font-semibold shadow-2xs" : "text-slate-600"
                    }`}
                  >
                    HTML Source
                  </button>
                  <button
                    type="button"
                    onClick={() => setContentMode("plaintext")}
                    className={`px-2 py-0.5 rounded transition-all cursor-pointer ${
                      contentMode === "plaintext" ? "bg-white text-slate-900 font-semibold shadow-2xs" : "text-slate-600"
                    }`}
                  >
                    Plaintext Fallback
                  </button>
                </div>
              </div>

              {/* Rendered Preview Container Frame */}
              <div className="w-full flex justify-center flex-1 min-h-[360px] max-h-[480px]">
                <div
                  className={`w-full bg-white rounded-lg border border-slate-200/90 shadow-2xs overflow-hidden flex flex-col ${
                    deviceView === "mobile" ? "max-w-sm" : "w-full"
                  }`}
                >
                  {contentMode === "preview" && (
                    <div className="p-4 sm:p-5 overflow-y-auto flex-1 text-xs text-slate-800 leading-relaxed pulsemail-preview-canvas focus:outline-none [scrollbar-width:thin]">
                      {sanitizedActiveHtml ? (
                        <div dangerouslySetInnerHTML={{ __html: sanitizedActiveHtml }} />
                      ) : activeStepItem?.body_text ? (
                        <div className="whitespace-pre-wrap font-sans">{activeStepItem.body_text}</div>
                      ) : (
                        <div className="text-slate-400 italic text-center py-8">
                          No message body configured for this step.
                        </div>
                      )}
                    </div>
                  )}

                  {contentMode === "html" && (
                    <div className="bg-slate-900 text-slate-100 p-4 font-mono text-xs overflow-y-auto flex-1">
                      <div className="text-[10px] text-slate-400 pb-2 mb-2 border-b border-slate-800 flex justify-between">
                        <span>template_source.html</span>
                        <span>Safe Escaped View</span>
                      </div>
                      <pre className="whitespace-pre-wrap break-words text-slate-200">
                        <code>{activeStepItem?.body_html || "<!-- No HTML content configured -->"}</code>
                      </pre>
                    </div>
                  )}

                  {contentMode === "plaintext" && (
                    <div className="p-4 font-mono text-xs overflow-y-auto flex-1 space-y-2">
                      <div className="text-[10px] text-slate-400 pb-1.5 mb-1.5 border-b border-slate-100 flex justify-between">
                        <span>plaintext_fallback.txt</span>
                        <span>Whitespace Preserved</span>
                      </div>
                      <pre className="whitespace-pre-wrap font-sans text-slate-800">
                        {activeStepItem?.body_text || "(No plaintext body configured)"}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Row 3: Performance Overview (Left) & Step-Level Funnel (Right) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5 items-stretch">
            {/* Left: Performance Overview */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs space-y-4">
              <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
                <div>
                  <h2 className="sr-only">Delivery Breakdown & Telemetry</h2>
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                      <BarChart2 className="h-3.5 w-3.5" />
                    </div>
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">Performance Overview</h3>
                  </div>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Live recipient status counts aggregated across this campaign's audience.
                  </p>
                </div>
                <span className="text-[10px] font-medium text-slate-500 flex items-center gap-1 bg-slate-50 px-2 py-0.5 rounded border border-slate-100" title="Live aggregated campaign metrics across all recipients">
                  <span>Campaign Lifetime</span>
                </span>
              </div>

              {/* 5-Tile Status Metric Strip */}
              <div className="grid grid-cols-5 gap-2 text-center">
                <Link
                  to={`/campaigns/${campaign.id}/emails?status=recipients`}
                  className="bg-slate-50/70 hover:bg-indigo-50/60 hover:border-indigo-200 transition-all duration-150 p-2.5 rounded-lg border border-slate-100 block cursor-pointer group"
                  title="View all campaign recipients"
                >
                  <Users className="h-3.5 w-3.5 text-indigo-500 mx-auto mb-1 group-hover:scale-110 transition-transform" />
                  <p className="text-sm sm:text-base font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">{totalTarget}</p>
                  <p className="text-[10px] text-slate-500">Recipients</p>
                </Link>

                <Link
                  to={`/campaigns/${campaign.id}/emails?status=sent`}
                  className="bg-slate-50/70 hover:bg-emerald-50/60 hover:border-emerald-200 transition-all duration-150 p-2.5 rounded-lg border border-slate-100 block cursor-pointer group"
                  title="View successfully sent emails"
                >
                  <Send className="h-3.5 w-3.5 text-emerald-500 mx-auto mb-1 group-hover:scale-110 transition-transform" />
                  <p className="text-sm sm:text-base font-bold text-slate-900 group-hover:text-emerald-600 transition-colors" data-testid="telemetry-sent">
                    {totalSentCount}
                  </p>
                  <p className="text-[10px] text-slate-500">Delivered Emails</p>
                </Link>

                <Link
                  to={`/campaigns/${campaign.id}/emails?status=replies`}
                  className="bg-slate-50/70 hover:bg-indigo-50/60 hover:border-indigo-200 transition-all duration-150 p-2.5 rounded-lg border border-slate-100 block cursor-pointer group"
                  title="View incoming replies"
                >
                  <Reply className="h-3.5 w-3.5 text-indigo-600 mx-auto mb-1 group-hover:scale-110 transition-transform" />
                  <p className="text-sm sm:text-base font-bold text-slate-900 group-hover:text-indigo-600 transition-colors">{uniqueRepliedCount}</p>
                  <p className="text-[10px] text-slate-500">Replies {replyRate}%</p>
                </Link>

                <Link
                  to={`/campaigns/${campaign.id}/emails?status=bounced`}
                  className="bg-slate-50/70 hover:bg-rose-50/60 hover:border-rose-200 transition-all duration-150 p-2.5 rounded-lg border border-slate-100 block cursor-pointer group"
                  title="View bounced recipients"
                >
                  <AlertTriangle className="h-3.5 w-3.5 text-rose-500 mx-auto mb-1 group-hover:scale-110 transition-transform" />
                  <p className="text-sm sm:text-base font-bold text-slate-900 group-hover:text-rose-600 transition-colors" data-testid="telemetry-bounced">
                    {bouncedCount}
                  </p>
                  <p className="text-[10px] text-slate-500">Bounced {bounceRate}%</p>
                </Link>

                <Link
                  to={`/campaigns/${campaign.id}/emails?status=failed`}
                  className="bg-slate-50/70 hover:bg-amber-50/60 hover:border-amber-200 transition-all duration-150 p-2.5 rounded-lg border border-slate-100 block cursor-pointer group"
                  title="View failed deliveries"
                >
                  <AlertCircle className="h-3.5 w-3.5 text-amber-500 mx-auto mb-1 group-hover:scale-110 transition-transform" />
                  <p className="text-sm sm:text-base font-bold text-slate-900 group-hover:text-amber-600 transition-colors" data-testid="telemetry-failed">
                    {failedCount}
                  </p>
                  <p className="text-[10px] text-slate-500">Failed {failedRate}%</p>
                </Link>
              </div>

              {/* Hidden Telemetry Counters for Test Coverage */}
              <div className="sr-only">
                <span data-testid="telemetry-pending">{pendingCount}</span>
                <span data-testid="telemetry-suppressed">{suppressedCount}</span>
              </div>

              {/* Visual Progress Bar */}
              <div className="pt-1 space-y-1.5">
                <div className="flex items-center justify-between text-xs text-slate-500">
                  <span
                    className="cursor-help flex items-center gap-1"
                    title="Initial Audience Processing: Measures processing of the initial recipient audience (dispatched, suppressed, or failed), not total multi-step sequence delivery."
                  >
                    <span>Initial Dispatch Completion</span>
                  </span>
                  <span className="font-semibold text-indigo-600">{completionPercent}%</span>
                </div>
                <div
                  className="w-full bg-slate-100 rounded-full h-2 overflow-hidden flex"
                  data-testid="delivery-progress-bar"
                  role="progressbar"
                  aria-valuenow={completionPercent}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="bg-emerald-500 h-full transition-all duration-300 shrink-0"
                    style={{ width: `${totalTarget > 0 ? (initialSentCount / totalTarget) * 100 : 0}%` }}
                    title={`Sent: ${initialSentCount}`}
                  />
                  <div
                    className="bg-rose-500 h-full transition-all duration-300 shrink-0"
                    style={{ width: `${totalTarget > 0 ? (initialBounced / totalTarget) * 100 : 0}%` }}
                    title={`Bounced: ${initialBounced}`}
                  />
                  <div
                    className="bg-amber-500 h-full transition-all duration-300 shrink-0"
                    style={{ width: `${totalTarget > 0 ? (initialFailed / totalTarget) * 100 : 0}%` }}
                    title={`Failed: ${initialFailed}`}
                  />
                  <div
                    className="bg-slate-400 h-full transition-all duration-300 shrink-0"
                    style={{ width: `${totalTarget > 0 ? (initialSuppressed / totalTarget) * 100 : 0}%` }}
                    title={`Suppressed: ${initialSuppressed}`}
                  />
                </div>
              </div>
            </div>

            {/* Right: Step-Level Analytics Funnel Card */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs flex flex-col justify-between space-y-4">
              <div>
                <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                      <TrendingUp className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <div className="flex items-center gap-1.5">
                        <h3 className="text-xs sm:text-sm font-bold text-slate-900">
                          Step-Level Analytics Funnel
                        </h3>
                        <span className="px-2 py-0.2 rounded-full bg-indigo-50 text-indigo-700 text-[10px] font-bold border border-indigo-100">
                          {analytics?.steps?.length || totalStepsCount} Steps
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500">
                        Per-step conversion rates and delivery outcomes.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Compact Step Rows */}
                <div className="space-y-2 mt-3">
                  {(analytics?.steps && analytics.steps.length > 0 ? analytics.steps : [
                    {
                      step_number: 1,
                      subject: campaign.subject,
                      delivery_rate: sentRate,
                      reply_rate: replyRate,
                      bounce_rate: bounceRate,
                      failed_count: failedCount,
                    },
                    ...followupSteps.map((s, idx) => ({
                      step_number: s.step_number || idx + 2,
                      subject: s.subject || `Re: ${campaign.subject}`,
                      delivery_rate: 0,
                      reply_rate: 0,
                      bounce_rate: 0,
                      failed_count: 0,
                    })),
                  ]).map((stepItem: any, idx: number) => {
                    const stepNum = stepItem.step_number || idx + 1;
                    const stepTitle = stepNum === 1 ? "Initial Outreach" : `Follow-Up #${stepNum - 1}`;
                    const delRate = Math.round(stepItem.delivery_rate || 0);
                    const repRate = Math.round(stepItem.reply_rate || 0);
                    const bncRate = Math.round(stepItem.bounce_rate || 0);

                    return (
                      <div
                        key={stepNum}
                        className="p-2.5 rounded-lg bg-slate-50/70 border border-slate-200/70 flex items-center justify-between gap-3 text-xs flex-wrap"
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="px-1.5 py-0.5 rounded bg-slate-900 text-white font-bold text-[10px]">
                            Step {stepNum}
                          </span>
                          <span className="font-semibold text-slate-900 truncate">{stepTitle}</span>
                        </div>

                        <div className="flex items-center gap-3 text-[11px] text-slate-600 flex-wrap">
                          <span className="flex items-center gap-1 font-medium text-emerald-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            <span>Delivered {delRate}%</span>
                          </span>
                          <span className="flex items-center gap-1 font-medium text-indigo-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500" />
                            <span>Replied {repRate}%</span>
                          </span>
                          <span className="flex items-center gap-1 font-medium text-rose-700">
                            <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                            <span>Bounced {bncRate}%</span>
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="pt-2 border-t border-slate-100 text-center">
                <button
                  type="button"
                  onClick={() => setActiveTab("analytics")}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 hover:underline cursor-pointer"
                >
                  <span>View Detailed Analytics</span>
                  <ArrowRight className="h-3 w-3" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 2: EMAIL SEQUENCE TAB CONTENT
          ========================================================================= */}
      {currentTab === "sequence" && (
        <div className="space-y-4 sm:space-y-5">
          {/* Top Row: 3 Summary Cards */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Card 1: Sender Identity */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs space-y-2">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <Send className="h-3.5 w-3.5" />
                  </div>
                  <h3 className="text-xs sm:text-sm font-bold text-slate-900">Sender Identity</h3>
                </div>
                <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold">
                  Active
                </span>
              </div>
              <p className="text-xs sm:text-sm font-semibold text-slate-900 truncate">{senderName}</p>
              <p className="text-xs text-slate-500 truncate">{senderEmail}</p>
              <div className="pt-1 flex items-center justify-between text-xs text-slate-500">
                <span>Domain: {senderDomain}</span>
                <span>Account #{campaign.email_account_id}</span>
              </div>
            </div>

            {/* Card 2: Schedule & Timing */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs space-y-2">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <Clock className="h-3.5 w-3.5" />
                  </div>
                  <h3 className="text-xs sm:text-sm font-bold text-slate-900">Schedule & Timing</h3>
                </div>
                <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[10px] font-bold">
                  {campaign.scheduled_at ? "Scheduled" : isDraft ? "On-Demand" : campaign.status}
                </span>
              </div>
              <p className="text-xs sm:text-sm font-semibold text-slate-900 truncate">
                {campaign.scheduled_at ? "Scheduled Dispatch" : isDraft ? "Manual Dispatch" : campaign.status}
              </p>
              <p className="text-xs text-slate-500">
                {campaign.scheduled_at
                  ? `Execution set for ${formatDate(campaign.scheduled_at)}`
                  : isDraft
                  ? "Requires final review before queue ingestion."
                  : `Campaign in ${campaign.status} lifecycle`}
              </p>
              <div className="pt-1 flex items-center justify-between text-xs text-slate-500">
                <span>Interval: {formatSendInterval(campaign.send_interval_seconds)}</span>
                <span data-testid="sequence-sending-window">Window: {formatSendingWindow(campaign.sending_window)}</span>
              </div>
            </div>

            {/* Card 3: Target Audience */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs space-y-2">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <Users className="h-3.5 w-3.5" />
                  </div>
                  <h3 className="text-xs sm:text-sm font-bold text-slate-900">Target Audience</h3>
                </div>
                <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[10px] font-bold">
                  Verified
                </span>
              </div>
              <p className="text-xl font-bold text-slate-900 leading-none">
                {campaign.recipient_count.toLocaleString()}
              </p>
              <p className="text-xs text-slate-500">Total recipients</p>
              <div className="pt-1 flex items-center justify-between text-xs text-slate-500">
                <span>Scope: Company Isolated</span>
                <Link
                  to={`/campaigns/${campaign.id}/recipients`}
                  className="font-semibold text-indigo-600 hover:text-indigo-700 hover:underline"
                >
                  Audience Configured
                </Link>
              </div>
            </div>
          </div>

          {/* Full Sequence Timeline & Large Interactive Preview Frame */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
            {/* Left: Interactive Timeline with Excerpts */}
            <div className="bg-white rounded-xl p-5 border border-slate-200/90 shadow-2xs space-y-4">
              <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <Mail className="h-4 w-4 text-indigo-600" />
                  <h3 className="text-sm font-bold text-slate-900">Email Sequence</h3>
                  <span className="px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 text-xs font-semibold">
                    {totalStepsCount} Steps
                  </span>
                </div>
                {isDraft && isAdminOrOwner && (
                  <Link
                    to={`/campaigns/${campaign.id}/edit`}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700"
                  >
                    <Plus className="h-3.5 w-3.5" />
                    <span>Add Follow-Up</span>
                  </Link>
                )}
              </div>

              <div className="relative pl-7 space-y-4">
                <div className="absolute left-2.5 top-3 bottom-3 w-0.5 bg-slate-200" />

                {/* Step 1 */}
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setSelectedStepNumber(1)}
                    className={`absolute -left-7 top-1.5 w-5 h-5 rounded-full font-bold text-[10px] flex items-center justify-center z-10 transition-all cursor-pointer ${
                      selectedStepNumber === 1
                        ? "bg-indigo-600 text-white ring-4 ring-indigo-50"
                        : "bg-slate-200 text-slate-600 hover:bg-slate-300"
                    }`}
                  >
                    1
                  </button>
                  <div
                    onClick={() => setSelectedStepNumber(1)}
                    className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-1.5 ${
                      selectedStepNumber === 1
                        ? "bg-indigo-50/40 border-indigo-200/90 shadow-2xs"
                        : "bg-slate-50/60 border-slate-200/80 hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-xs text-slate-900">Initial Outreach</span>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-semibold text-emerald-600 flex items-center gap-0.5">
                          <Zap className="h-2.5 w-2.5 fill-emerald-600" /> Immediate
                        </span>
                        {step1Item?.is_active === false ? (
                          <span className="text-[10px] font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                            Inactive
                          </span>
                        ) : (
                          <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100">
                            Active
                          </span>
                        )}
                      </div>
                    </div>
                    <p className="text-xs font-semibold text-slate-800 truncate">
                      <span>Subject: </span>
                      <span className="font-semibold text-slate-800">
                        {step1Item?.subject || "No subject set"}
                      </span>
                    </p>
                    <p className="text-[11px] text-slate-500 line-clamp-3 leading-relaxed">
                      {step1Excerpt}
                    </p>
                  </div>
                </div>

                {/* Follow-up steps */}
                {followupSteps.map((step, idx) => {
                  const isDays = step.delay_hours >= 24 && step.delay_hours % 24 === 0;
                  const delayText = isDays
                    ? `${step.delay_hours / 24} day${step.delay_hours / 24 > 1 ? "s" : ""}`
                    : `${step.delay_hours} hour${step.delay_hours > 1 ? "s" : ""}`;
                  const isSelected = selectedStepNumber === step.step_number;

                  return (
                    <div key={step.id || step.step_number || idx} className="relative">
                      <button
                        type="button"
                        onClick={() => setSelectedStepNumber(step.step_number)}
                        className={`absolute -left-7 top-1.5 w-5 h-5 rounded-full font-bold text-[10px] flex items-center justify-center z-10 transition-all cursor-pointer ${
                          isSelected
                            ? "bg-indigo-600 text-white ring-4 ring-indigo-50"
                            : "bg-slate-200 text-slate-600 hover:bg-slate-300"
                        }`}
                      >
                        {step.step_number}
                      </button>
                      <div
                        onClick={() => setSelectedStepNumber(step.step_number)}
                        className={`p-3.5 rounded-xl border transition-all cursor-pointer space-y-1.5 ${
                          isSelected
                            ? "bg-indigo-50/40 border-indigo-200/90 shadow-2xs"
                            : "bg-slate-50/60 border-slate-200/80 hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-bold text-xs text-slate-900">
                            Follow-Up #{idx + 1} (Step {step.step_number})
                          </span>
                          <div className="flex items-center gap-1.5">
                            <span className="text-[10px] text-slate-600 font-medium bg-white px-2 py-0.5 rounded border border-slate-200">
                              Waits {delayText} if no reply
                            </span>
                            {step.is_active === false ? (
                              <span className="text-[10px] font-semibold text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                                Inactive
                              </span>
                            ) : (
                              <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-100">
                                Active
                              </span>
                            )}
                          </div>
                        </div>
                        <p className="text-xs font-semibold text-slate-800 truncate">
                          Subject: {step.subject || `Re: ${campaign.subject || "Campaign"}`}
                        </p>
                        <p className="text-[11px] text-slate-500 line-clamp-3 leading-relaxed">
                          {step.body_text ||
                            (step.body_html
                              ? step.body_html.replace(/<[^>]+>/g, " ").trim()
                              : "No content provided.")}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Right: Email Preview Panel */}
            <div className="bg-white rounded-xl p-5 border border-slate-200/90 shadow-2xs flex flex-col space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <Eye className="h-4 w-4 text-indigo-600" />
                  <h3 className="text-sm font-bold text-slate-900">Email Preview</h3>
                </div>

                <div className="flex items-center gap-2 flex-wrap">
                  <div className="inline-flex p-0.5 rounded-lg bg-slate-100 text-xs font-medium border border-slate-200">
                    <button
                      type="button"
                      onClick={() => setSelectedStepNumber(1)}
                      className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                        selectedStepNumber === 1
                          ? "bg-indigo-600 text-white font-semibold shadow-2xs"
                          : "text-slate-600 hover:text-slate-900"
                      }`}
                    >
                      Initial Outreach
                    </button>
                    {followupSteps.map((s, idx) => (
                      <button
                        key={s.step_number || idx}
                        type="button"
                        onClick={() => setSelectedStepNumber(s.step_number)}
                        className={`px-2.5 py-1 rounded-md transition-all cursor-pointer ${
                          selectedStepNumber === s.step_number
                            ? "bg-indigo-600 text-white font-semibold shadow-2xs"
                            : "text-slate-600 hover:text-slate-900"
                        }`}
                      >
                        Follow-Up #{idx + 1}
                      </button>
                    ))}
                  </div>

                  <div className="inline-flex p-0.5 rounded-lg bg-slate-100 text-slate-600 border border-slate-200">
                    <button
                      type="button"
                      onClick={() => setDeviceView("desktop")}
                      className={`p-1 rounded-md transition-all cursor-pointer ${
                        deviceView === "desktop" ? "bg-white text-slate-900 shadow-2xs" : "hover:text-slate-900"
                      }`}
                      title="Desktop Viewport"
                    >
                      <Monitor className="h-3.5 w-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeviceView("mobile")}
                      className={`p-1 rounded-md transition-all cursor-pointer ${
                        deviceView === "mobile" ? "bg-white text-slate-900 shadow-2xs" : "hover:text-slate-900"
                      }`}
                      title="Mobile Viewport"
                    >
                      <Smartphone className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Subject bar */}
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-1.5 min-w-0 flex-1">
                  <span className="text-xs font-semibold text-slate-500 uppercase shrink-0">Subject:</span>
                  <span className="text-xs sm:text-sm font-semibold text-slate-900 truncate">
                    {activeStepItem?.subject || "No subject set"}
                  </span>
                  <button
                    type="button"
                    onClick={handleCopySubject}
                    className="inline-flex items-center gap-1 p-1 rounded text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                    title="Copy Subject Line"
                  >
                    {copiedSubject ? (
                      <>
                        <Check className="h-3.5 w-3.5 text-emerald-600" />
                        <span className="text-[11px] font-semibold text-emerald-600">Copied!</span>
                      </>
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                  </button>
                </div>

                <div className="inline-flex p-0.5 rounded-lg bg-slate-100 text-[11px] font-medium border border-slate-200 shrink-0">
                  <button
                    type="button"
                    onClick={() => setContentMode("preview")}
                    className={`px-2 py-0.5 rounded transition-all cursor-pointer ${
                      contentMode === "preview" ? "bg-white text-slate-900 font-semibold shadow-2xs" : "text-slate-600"
                    }`}
                  >
                    Formatted Preview
                  </button>
                  <button
                    type="button"
                    onClick={() => setContentMode("html")}
                    className={`px-2 py-0.5 rounded transition-all cursor-pointer ${
                      contentMode === "html" ? "bg-white text-slate-900 font-semibold shadow-2xs" : "text-slate-600"
                    }`}
                  >
                    HTML Source
                  </button>
                  <button
                    type="button"
                    onClick={() => setContentMode("plaintext")}
                    className={`px-2 py-0.5 rounded transition-all cursor-pointer ${
                      contentMode === "plaintext" ? "bg-white text-slate-900 font-semibold shadow-2xs" : "text-slate-600"
                    }`}
                  >
                    Plaintext Fallback
                  </button>
                </div>
              </div>

              {/* Frame Container */}
              <div className="w-full flex justify-center flex-1 min-h-[320px] max-h-[460px]">
                <div
                  className={`w-full bg-white rounded-lg border border-slate-200/90 shadow-2xs overflow-hidden flex flex-col ${
                    deviceView === "mobile" ? "max-w-sm" : "w-full"
                  }`}
                >
                  {contentMode === "preview" && (
                    <div className="p-4 sm:p-5 overflow-y-auto flex-1 text-xs text-slate-800 leading-relaxed pulsemail-preview-canvas focus:outline-none [scrollbar-width:thin]">
                      {sanitizedActiveHtml ? (
                        <div dangerouslySetInnerHTML={{ __html: sanitizedActiveHtml }} />
                      ) : activeStepItem?.body_text ? (
                        <div className="whitespace-pre-wrap font-sans">{activeStepItem.body_text}</div>
                      ) : (
                        <div className="text-slate-400 italic text-center py-8">
                          No message body configured for this step.
                        </div>
                      )}
                    </div>
                  )}

                  {contentMode === "html" && (
                    <div className="bg-slate-900 text-slate-100 p-4 font-mono text-xs overflow-y-auto flex-1">
                      <div className="text-[10px] text-slate-400 pb-2 mb-2 border-b border-slate-800 flex justify-between">
                        <span>template_source.html</span>
                        <span>Safe Escaped View</span>
                      </div>
                      <pre className="whitespace-pre-wrap break-words text-slate-200">
                        <code>{activeStepItem?.body_html || "<!-- No HTML content configured -->"}</code>
                      </pre>
                    </div>
                  )}

                  {contentMode === "plaintext" && (
                    <div className="p-4 font-mono text-xs overflow-y-auto flex-1 space-y-2">
                      <div className="text-[10px] text-slate-400 pb-1.5 mb-1.5 border-b border-slate-100 flex justify-between">
                        <span>plaintext_fallback.txt</span>
                        <span>Whitespace Preserved</span>
                      </div>
                      <pre className="whitespace-pre-wrap font-sans text-slate-800">
                        {activeStepItem?.body_text || "(No plaintext body configured)"}
                      </pre>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* =========================================================================
          TAB 3: ANALYTICS TAB CONTENT
          ========================================================================= */}
      {currentTab === "analytics" && (
        <div className="space-y-4 sm:space-y-5">
          {/* Row 1: 6 KPI Metric Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-3.5">
            {/* Unique Recipients */}
            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs space-y-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                <Users className="h-4 w-4" />
              </div>
              <div>
                <p className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">
                  Unique Recipients
                </p>
                <p className="text-2xl font-bold text-slate-900 mt-0.5">{totalTarget}</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Total Recipients</p>
              </div>
            </div>

            {/* Initial Emails Sent */}
            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 flex items-center justify-center">
                  <Send className="h-4 w-4" />
                </div>
                <span className="text-xs font-bold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-full">
                  {sentRate}%
                </span>
              </div>
              <div>
                <p className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">Initial Sent</p>
                <p className="text-2xl font-bold text-slate-900 mt-0.5">{initialSentCount}</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Step 1 dispatches</p>
              </div>
            </div>

            {/* Follow-up Emails Sent */}
            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                  <Mail className="h-4 w-4" />
                </div>
              </div>
              <div>
                <p className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">Follow-ups Sent</p>
                <p className="text-2xl font-bold text-slate-900 mt-0.5">{followupSentCount}</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Step 2+ dispatches</p>
              </div>
            </div>

            {/* Total Emails Sent */}
            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-lg bg-violet-50 text-violet-600 flex items-center justify-center">
                  <TrendingUp className="h-4 w-4" />
                </div>
              </div>
              <div>
                <p className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">Total Sent</p>
                <p className="text-2xl font-bold text-slate-900 mt-0.5">{totalSentCount}</p>
                <p className="text-[11px] text-slate-400 mt-0.5">All sequence dispatches</p>
              </div>
            </div>

            {/* Unique Replies */}
            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                  <Reply className="h-4 w-4" />
                </div>
                <span className="text-xs font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-full">
                  {replyRate}%
                </span>
              </div>
              <div>
                <p className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">Unique Replies</p>
                <p className="text-2xl font-bold text-slate-900 mt-0.5">{uniqueRepliedCount}</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Responding recipients</p>
              </div>
            </div>

            {/* Bounced */}
            <div className="bg-white p-4 rounded-xl border border-slate-200/90 shadow-2xs space-y-2">
              <div className="flex items-center justify-between">
                <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 flex items-center justify-center">
                  <AlertTriangle className="h-4 w-4" />
                </div>
                <span className="text-xs font-bold text-rose-700 bg-rose-50 px-2 py-0.5 rounded-full">
                  {bounceRate}%
                </span>
              </div>
              <div>
                <p className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider">Bounced</p>
                <p className="text-2xl font-bold text-slate-900 mt-0.5">{bouncedCount}</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Hard / soft bounces</p>
              </div>
            </div>
          </div>

          {/* Row 2: Delivery Trend (Left) & Email Status Distribution (Right) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 sm:gap-5 items-stretch">
            {/* Delivery Trend (Approx 60% on desktop) */}
            <div className="lg:col-span-7 bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs space-y-3 flex flex-col justify-between">
              <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <TrendingUp className="h-3.5 w-3.5" />
                  </div>
                  <div>
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">Delivery Trend</h3>
                    <p className="text-[11px] text-slate-500">
                      Daily email dispatch, bounces, and unique replying recipients.
                    </p>
                  </div>
                </div>
                <span className="text-[11px] font-medium text-slate-500 flex items-center gap-0.5 px-2 py-1 rounded bg-slate-50 border border-slate-200/70" title="Cumulative campaign lifetime dispatch telemetry">
                  <span>Campaign Lifetime</span>
                </span>
              </div>

              {/* Delivery Trend Content: Chart if data exists, empty state otherwise */}
              {analytics?.delivery_trend && analytics.delivery_trend.length > 0 ? (
                <div className="w-full h-44 flex flex-col justify-between p-3 bg-slate-50/50 rounded-xl border border-slate-200" data-testid="delivery-trend-chart">
                  <div className="flex items-center justify-end gap-3 text-[11px]">
                    <div className="flex items-center gap-1.5 text-slate-600" title="Total messages dispatched on this date">
                      <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500 shrink-0" />
                      <span>Sent</span>
                    </div>
                    <div className="flex items-center gap-1.5 text-slate-600" title="Unique replying recipients recorded on this date">
                      <span className="w-2.5 h-2.5 rounded-sm bg-indigo-600 shrink-0" />
                      <span>Unique Replies</span>
                    </div>
                  </div>
                  <div className="flex-1 flex items-end justify-around gap-2 pt-2 pb-1">
                    {analytics.delivery_trend.map((pt) => {
                      const maxVal = Math.max(1, ...analytics.delivery_trend!.map((p) => Math.max(p.sent_count, p.replied_count)));
                      const sentH = Math.round((pt.sent_count / maxVal) * 85);
                      const repH = Math.round((pt.replied_count / maxVal) * 85);
                      return (
                        <div key={pt.date} className="flex-1 flex flex-col items-center gap-1 h-full justify-end max-w-[80px]">
                          <div className="flex items-end gap-1.5 w-full justify-center h-24">
                            <div
                              className="w-3.5 bg-emerald-500 rounded-t transition-all"
                              style={{ height: `${Math.max(6, sentH)}%` }}
                              title={`${pt.date}: ${pt.sent_count} sent`}
                            />
                            {pt.replied_count > 0 && (
                              <div
                                className="w-3.5 bg-indigo-600 rounded-t transition-all"
                                style={{ height: `${Math.max(6, repH)}%` }}
                                title={`${pt.date}: ${pt.replied_count} replied`}
                              />
                            )}
                          </div>
                          <span className="text-[10px] text-slate-500 font-medium truncate w-full text-center">
                            {pt.date.slice(5)}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <div className="w-full h-44 flex flex-col items-center justify-center text-center p-4 bg-slate-50/50 rounded-xl border border-dashed border-slate-200">
                  <div className="w-10 h-10 rounded-full bg-indigo-50 text-indigo-500 flex items-center justify-center mb-2">
                    <TrendingUp className="h-5 w-5" />
                  </div>
                  <p className="text-xs font-semibold text-slate-700">No time-series dispatch trend recorded</p>
                  <p className="text-[11px] text-slate-500 max-w-sm mt-1 leading-relaxed">
                    Daily time-series delivery tracking is not stored for this campaign. Overall deliverability is tracked in the KPI summary and Step Performance below.
                  </p>
                </div>
              )}
            </div>

            {/* Email Status Distribution (Approx 40% on desktop) */}
            <div className="lg:col-span-5 bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs space-y-3 flex flex-col justify-between">
              <div className="flex items-center justify-between pb-2.5 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <PieChart className="h-3.5 w-3.5" />
                  </div>
                  <h3 className="text-xs sm:text-sm font-bold text-slate-900">
                    Email Status Distribution
                  </h3>
                </div>
              </div>

              {/* Donut Chart and Legend */}
              <div className="flex items-center justify-center sm:justify-around gap-4 py-2 flex-wrap sm:flex-nowrap">
                {/* SVG Donut */}
                <div className="relative w-28 h-28 shrink-0 flex items-center justify-center">
                  <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                    {/* Background Circle */}
                    <circle
                      cx="18"
                      cy="18"
                      r="14"
                      fill="transparent"
                      stroke="#f1f5f9"
                      strokeWidth="4"
                    />
                    {totalTarget > 0 ? (
                      <>
                        {/* Sent segment */}
                        {sentCount > 0 && (
                          <circle
                            cx="18"
                            cy="18"
                            r="14"
                            fill="transparent"
                            stroke="#10b981"
                            strokeWidth="4"
                            strokeDasharray={`${Math.round((initialSentCount / totalTarget) * 88)} 88`}
                            strokeDashoffset="0"
                          />
                        )}
                        {/* Pending segment */}
                        {pendingCount > 0 && (
                          <circle
                            cx="18"
                            cy="18"
                            r="14"
                            fill="transparent"
                            stroke="#94a3b8"
                            strokeWidth="4"
                            strokeDasharray={`${Math.round((pendingCount / totalTarget) * 88)} 88`}
                            strokeDashoffset={`-${Math.round((initialSentCount / totalTarget) * 88)}`}
                          />
                        )}
                        {/* Bounced segment */}
                        {bouncedCount > 0 && (
                          <circle
                            cx="18"
                            cy="18"
                            r="14"
                            fill="transparent"
                            stroke="#f43f5e"
                            strokeWidth="4"
                            strokeDasharray={`${Math.round((bouncedCount / totalTarget) * 88)} 88`}
                            strokeDashoffset={`-${Math.round(((initialSentCount + pendingCount) / totalTarget) * 88)}`}
                          />
                        )}
                        {/* Failed segment */}
                        {failedCount > 0 && (
                          <circle
                            cx="18"
                            cy="18"
                            r="14"
                            fill="transparent"
                            stroke="#f59e0b"
                            strokeWidth="4"
                            strokeDasharray={`${Math.round((failedCount / totalTarget) * 88)} 88`}
                            strokeDashoffset={`-${Math.round(((initialSentCount + pendingCount + bouncedCount) / totalTarget) * 88)}`}
                          />
                        )}
                      </>
                    ) : (
                      <circle
                        cx="18"
                        cy="18"
                        r="14"
                        fill="transparent"
                        stroke="#e2e8f0"
                        strokeWidth="4"
                      />
                    )}
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
                    <span className="text-base font-bold text-slate-900 leading-none">{totalTarget}</span>
                    <span className="text-[10px] text-slate-500 font-medium">Total</span>
                  </div>
                </div>

                {/* Grouped Legend: Audience Status & Sequence Outcomes */}
                <div className="space-y-2.5 text-xs">
                  <div>
                    <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400">Audience Status</span>
                    <div className="space-y-1 mt-1">
                      <div className="flex items-center justify-between gap-4">
                        <span className="flex items-center gap-1.5 text-slate-600">
                          <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0" />
                          <span>Initial Sent</span>
                        </span>
                        <span className="font-semibold text-slate-900">{initialSentCount} ({sentRate}%)</span>
                      </div>
                      <div className="flex items-center justify-between gap-4">
                        <span className="flex items-center gap-1.5 text-slate-600">
                          <span className="w-2 h-2 rounded-full bg-slate-400 shrink-0" />
                          <span>Pending</span>
                        </span>
                        <span className="font-semibold text-slate-900">
                          {pendingCount} ({totalTarget > 0 ? Math.round((pendingCount / totalTarget) * 100) : 0}%)
                        </span>
                      </div>
                      <div className="flex items-center justify-between gap-4">
                        <span className="flex items-center gap-1.5 text-slate-600">
                          <span className="w-2 h-2 rounded-full bg-rose-500 shrink-0" />
                          <span>Bounced</span>
                        </span>
                        <span className="font-semibold text-slate-900">{bouncedCount} ({bounceRate}%)</span>
                      </div>
                      <div className="flex items-center justify-between gap-4">
                        <span className="flex items-center gap-1.5 text-slate-600">
                          <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
                          <span>Failed</span>
                        </span>
                        <span className="font-semibold text-slate-900">{failedCount} ({failedRate}%)</span>
                      </div>
                    </div>
                  </div>

                  <div className="pt-1.5 border-t border-slate-100">
                    <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400">Sequence Outcomes</span>
                    <div className="space-y-1 mt-1">
                      <div className="flex items-center justify-between gap-4">
                        <span className="flex items-center gap-1.5 text-slate-600">
                          <span className="w-2 h-2 rounded-full bg-blue-500 shrink-0" />
                          <span>Follow-ups Sent</span>
                        </span>
                        <span className="font-semibold text-slate-900">{followupSentCount}</span>
                      </div>
                      <div className="flex items-center justify-between gap-4">
                        <span className="flex items-center gap-1.5 text-slate-600">
                          <span className="w-2 h-2 rounded-full bg-indigo-500 shrink-0" />
                          <span>Unique Replies</span>
                        </span>
                        <span className="font-semibold text-slate-900">{uniqueRepliedCount} ({replyRate}%)</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Row 3: Full-Width Step Performance Table */}
          <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs space-y-3">
            <div className="flex items-center justify-between gap-2 pb-2.5 border-b border-slate-100 flex-wrap">
              <div className="flex items-center gap-2">
                <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                  <BarChart2 className="h-3.5 w-3.5" />
                </div>
                <div>
                  <h3 className="text-xs sm:text-sm font-bold text-slate-900">Step Performance</h3>
                  <p className="text-[11px] text-slate-500">
                    Delivery and engagement stats for each email in the sequence.
                  </p>
                </div>
              </div>

              <span className="text-[11px] font-medium text-slate-500 flex items-center gap-1 px-2 py-1 rounded bg-slate-50 border border-slate-200/70" title="Cumulative step conversion outcomes across all campaign recipients">
                <span>Campaign Lifetime</span>
              </span>
            </div>

            {/* Step Performance Table */}
            <div className="overflow-x-auto [scrollbar-width:thin]">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-100 text-[11px] text-slate-400 uppercase font-semibold">
                    <th className="py-2.5 px-3">Step</th>
                    <th className="py-2.5 px-3">Email Name</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3 text-center">Recipients</th>
                    <th className="py-2.5 px-3 text-center">Sent</th>
                    <th className="py-2.5 px-3 text-center">Replies</th>
                    <th className="py-2.5 px-3 text-center">Bounce Rate</th>
                    <th className="py-2.5 px-3 text-center">Failure Rate</th>
                    <th className="py-2.5 px-3" title="Estimated from successful SMTP dispatch minus detected bounces; actual mailbox receipt is not tracked.">Net Delivery Rate</th>
                    <th className="py-2.5 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 text-slate-700">
                  {(analytics?.steps && analytics.steps.length > 0 ? analytics.steps : [
                    {
                      step_number: 1,
                      subject: step1Item?.subject || campaign.subject,
                      delay_hours: 0,
                      is_active: step1Item?.is_active ?? true,
                      targeted_count: totalTarget,
                      sent_count: sentCount,
                      replied_count: repliedCount,
                      bounced_count: bouncedCount,
                      failed_count: failedCount,
                      delivery_rate: sentRate,
                      reply_rate: replyRate,
                      bounce_rate: bounceRate,
                    },
                    ...followupSteps.map((s, idx) => ({
                      step_number: s.step_number || idx + 2,
                      subject: s.subject || `Step ${s.step_number || idx + 2}`,
                      delay_hours: s.delay_hours,
                      is_active: s.is_active ?? true,
                      targeted_count: totalTarget,
                      sent_count: 0,
                      replied_count: 0,
                      bounced_count: 0,
                      failed_count: 0,
                      delivery_rate: 0,
                      reply_rate: 0,
                      bounce_rate: 0,
                    })),
                  ]).map((stepItem: any, idx: number) => {
                    const stepNum = stepItem.step_number || idx + 1;
                    const stepName = stepNum === 1 ? "Initial Outreach" : `Follow-Up #${stepNum - 1}`;
                    const stepActive =
                      stepItem.is_active !== undefined
                        ? stepItem.is_active !== false
                        : stepNum === 1
                        ? step1Item?.is_active !== false
                        : followupSteps.find((f) => f.step_number === stepNum)?.is_active !== false;
                    const sSent = stepItem.sent_count ?? 0;
                    const sBnc = stepItem.bounced_count ?? 0;
                    const sFail = stepItem.failed_count ?? 0;
                    const sReplied = stepItem.replied_count ?? 0;
                    const sDeliv = stepItem.delivered_count !== undefined ? stepItem.delivered_count : Math.max(0, sSent - sBnc);
                    const delRate = stepItem.delivery_rate !== undefined ? Math.round(stepItem.delivery_rate) : (sSent > 0 ? Math.round((sDeliv / sSent) * 100) : 0);
                    const bncRate = stepItem.bounce_rate !== undefined ? Math.round(stepItem.bounce_rate) : (sSent > 0 ? Math.round((sBnc / sSent) * 100) : 0);
                    const failRate = sSent > 0 ? Math.round((sFail / sSent) * 100) : 0;
                    const repRate = stepItem.reply_rate !== undefined ? Math.round(stepItem.reply_rate) : (sSent > 0 ? Math.round((sReplied / sSent) * 100) : 0);

                    return (
                      <tr key={stepNum} className="hover:bg-slate-50/70 transition-colors">
                        <td className="py-3 px-3">
                          <span className="w-5 h-5 rounded-full bg-indigo-600 text-white font-bold text-[10px] flex items-center justify-center">
                            {stepNum}
                          </span>
                        </td>
                        <td className="py-3 px-3">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-semibold text-slate-900">{stepName}</span>
                            {stepNum === 1 ? (
                              <span className="text-[10px] font-semibold text-emerald-600 flex items-center gap-0.5">
                                <Zap className="h-2.5 w-2.5 fill-emerald-600" /> Immediate
                              </span>
                            ) : (
                              <span className="text-[10px] text-slate-500 font-medium bg-slate-100 px-1.5 py-0.2 rounded">
                                Waits {stepItem.delay_hours !== undefined ? `${stepItem.delay_hours}h` : "1h"}
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-3 px-3">
                          {stepActive ? (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 select-none">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                              <span>{campaign.status === "DRAFT" ? "Pending" : "Active"}</span>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-neutral-100 text-neutral-600 border border-neutral-200 select-none">
                              <span className="w-1.5 h-1.5 rounded-full bg-neutral-400" />
                              <span>Inactive</span>
                            </span>
                          )}
                        </td>
                        <td className="py-3 px-3 text-center font-medium">{stepItem.targeted_count ?? totalTarget}</td>
                        <td className="py-3 px-3 text-center font-medium">{stepItem.sent_count ?? 0}</td>
                        <td className="py-3 px-3 text-center font-medium">
                          {stepItem.replied_count ?? 0} ({repRate}%)
                        </td>
                        <td className="py-3 px-3 text-center font-medium">
                          {stepItem.bounced_count ?? 0} ({bncRate}%)
                        </td>
                        <td className="py-3 px-3 text-center font-medium">
                          {stepItem.failed_count ?? 0} ({failRate}%)
                        </td>
                        <td className="py-3 px-3" title="Estimated from successful SMTP dispatch minus detected bounces; actual mailbox receipt is not tracked.">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-900 w-8">{delRate}%</span>
                            <div className="w-16 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                              <div
                                className="bg-indigo-600 h-full rounded-full"
                                style={{ width: `${delRate}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="py-3 px-3 text-right">
                          <button
                            type="button"
                            onClick={() => {
                              setSelectedStepNumber(stepNum);
                              setActiveTab("sequence");
                            }}
                            className="inline-flex items-center gap-1 text-[11px] font-semibold text-indigo-600 hover:text-indigo-700 hover:underline cursor-pointer"
                          >
                            <span>View Details</span>
                            <ArrowRight className="h-3 w-3" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Row 4: Recipient Engagement (Left) & Top Performing Insights (Right) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-5 items-stretch">
            {/* Recipient Engagement */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs space-y-3.5">
              <div className="flex items-center gap-2 pb-2.5 border-b border-slate-100">
                <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                  <Users className="h-3.5 w-3.5" />
                </div>
                <div>
                  <h3 className="text-xs sm:text-sm font-bold text-slate-900">Recipient Engagement</h3>
                  <p className="text-[11px] text-slate-500">How recipients are interacting with your emails.</p>
                </div>
              </div>

              {/* 4 Engagement Tiles with honest tracking states */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                <div className="bg-slate-50/70 p-2.5 rounded-lg border border-slate-100 text-center flex flex-col justify-between">
                  <div>
                    <Mail className="h-4 w-4 text-slate-400 mx-auto mb-1" />
                    <p className="text-sm font-bold text-slate-400">—</p>
                    <p className="text-[10px] text-slate-500 mt-0.5 font-medium">Opened</p>
                  </div>
                  <span className="inline-block mt-1 text-[9px] text-slate-400 font-semibold bg-slate-100 px-1.5 py-0.5 rounded">
                    Not Tracked
                  </span>
                </div>

                <div className="bg-slate-50/70 p-2.5 rounded-lg border border-slate-100 text-center flex flex-col justify-between">
                  <div>
                    <ExternalLink className="h-4 w-4 text-slate-400 mx-auto mb-1" />
                    <p className="text-sm font-bold text-slate-400">—</p>
                    <p className="text-[10px] text-slate-500 mt-0.5 font-medium">Clicked</p>
                  </div>
                  <span className="inline-block mt-1 text-[9px] text-slate-400 font-semibold bg-slate-100 px-1.5 py-0.5 rounded">
                    Not Tracked
                  </span>
                </div>

                <div className="bg-slate-50/70 p-2.5 rounded-lg border border-slate-100 text-center flex flex-col justify-between">
                  <div>
                    <Reply className="h-4 w-4 text-indigo-600 mx-auto mb-1" />
                    <p className="text-sm font-bold text-slate-900">{repliedCount}</p>
                    <p className="text-[10px] text-slate-600 mt-0.5 font-medium">Replied {replyRate}%</p>
                  </div>
                  <span className="inline-block mt-1 text-[9px] text-emerald-600 font-semibold bg-emerald-50 px-1.5 py-0.5 rounded">
                    Active Signal
                  </span>
                </div>

                <div className="bg-slate-50/70 p-2.5 rounded-lg border border-slate-100 text-center flex flex-col justify-between">
                  <div>
                    <XCircle className="h-4 w-4 text-slate-400 mx-auto mb-1" />
                    <p className="text-sm font-bold text-slate-400">—</p>
                    <p className="text-[10px] text-slate-500 mt-0.5 font-medium">Unsubscribed</p>
                  </div>
                  <span className="inline-block mt-1 text-[9px] text-slate-400 font-semibold bg-slate-100 px-1.5 py-0.5 rounded">
                    Not Tracked
                  </span>
                </div>
              </div>

              <p className="text-[10px] text-slate-400 italic">
                * Open, click, and direct unsubscribe tracking are omitted by design to maximize email deliverability and preserve recipient privacy.
              </p>
            </div>

            {/* Top Performing Insights */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/90 shadow-2xs space-y-3.5 flex flex-col justify-between">
              <div>
                <div className="flex items-center gap-2 pb-2.5 border-b border-slate-100">
                  <div className="w-7 h-7 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                    <Lightbulb className="h-3.5 w-3.5" />
                  </div>
                  <div>
                    <h3 className="text-xs sm:text-sm font-bold text-slate-900">Top Performing Insights</h3>
                    <p className="text-[11px] text-slate-500">Key insights from your campaign performance.</p>
                  </div>
                </div>

                <div className="mt-3 p-3.5 rounded-xl bg-indigo-50/40 border border-indigo-100 flex items-start gap-3">
                  <Info className="h-4 w-4 text-indigo-600 shrink-0 mt-0.5" />
                  <div className="space-y-0.5">
                    <p className="text-xs font-semibold text-indigo-900">
                      {sentCount === 0 ? "No data available yet" : "Campaign Performance Insight"}
                    </p>
                    <p className="text-[11px] text-indigo-700/90 leading-relaxed">
                      {initialSentCount === 0
                        ? "Your campaign hasn't been sent yet. Analytics will appear here after emails are dispatched."
                        : `Step 1 (Initial Outreach) has recorded ${initialSentCount} sends with ${uniqueRepliedCount} positive replies detected.`}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal for Cancel / Delete / Archive / Restore */}
      <CancelCampaignModal
        isOpen={modalState.isOpen}
        campaign={modalState.campaign}
        mode={modalState.mode}
        onClose={() => setModalState({ isOpen: false, campaign: null, mode: "cancel" })}
        onConfirm={handleConfirmModal}
        isLoading={
          cancelMutation.isPending ||
          deleteMutation.isPending ||
          archiveMutation.isPending ||
          restoreMutation.isPending
        }
      />

      {/* Preflight & Schedule / Launch Modal */}
      <CampaignPreflightModal
        isOpen={actionModalState.isOpen}
        mode={actionModalState.mode}
        campaign={campaign}
        preflight={actionModalState.preflight}
        isLoadingPreflight={actionModalState.isLoadingPreflight}
        preflightError={actionModalState.preflightError}
        onRetryPreflight={handleRetryPreflight}
        onClose={() => setActionModalState((prev) => ({ ...prev, isOpen: false }))}
        onConfirmLaunch={() => dispatchMutation.mutate()}
        onConfirmSchedule={(iso) => scheduleMutation.mutate(iso)}
        isSubmitting={dispatchMutation.isPending || scheduleMutation.isPending}
      />

      {/* Floating Notification Toast */}
      {toastMessage && (
        <div
          role="status"
          aria-live="polite"
          className="fixed bottom-6 right-6 z-50 bg-slate-900 text-white px-4 py-3 rounded-xl shadow-xl flex items-center gap-3 border border-slate-800 text-xs animate-in fade-in slide-in-from-bottom-2 duration-200"
        >
          {toastMessage.type === "success" ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
          ) : toastMessage.type === "info" ? (
            <AlertCircle className="h-4 w-4 text-sky-400 shrink-0" />
          ) : (
            <AlertCircle className="h-4 w-4 text-rose-400 shrink-0" />
          )}
          <span>{toastMessage.text}</span>
        </div>
      )}
    </div>
  );
};
