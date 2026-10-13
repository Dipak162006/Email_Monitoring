import React, { useState, useMemo } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
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
  Code,
  FileText,
  Copy,
  Check,
  Monitor,
  Smartphone,
  Eye,
} from "lucide-react";

import { useWorkspace } from "../hooks/useWorkspace";
import { campaignsApi, RequestError } from "../services/api";
import type { Campaign, CampaignDetail, CampaignPreflightResponse } from "../types/campaign";
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

export const CampaignDetailPage: React.FC = () => {
  const { campaignId } = useParams<{ campaignId: string }>();
  const campaignIdNum = Number(campaignId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentCompanyId, currentRole } = useWorkspace();

  // Preview controls
  const [contentMode, setContentMode] = useState<"preview" | "html" | "plaintext">("preview");
  const [deviceView, setDeviceView] = useState<"desktop" | "mobile">("desktop");
  const [copiedSubject, setCopiedSubject] = useState<boolean>(false);

  // Toast feedback state
  const [toastMessage, setToastMessage] = useState<{
    text: string;
    type: "success" | "error" | "info";
  } | null>(null);

  const showToast = (
    text: string,
    type: "success" | "error" | "info" = "success"
  ) => {
    setToastMessage({ text, type });
    setTimeout(() => {
      setToastMessage(null);
    }, 3500);
  };

  const isAdminOrOwner = currentRole === "OWNER" || currentRole === "ADMIN";

  // Modal state for cancel / delete
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

  const invalidateQueries = () => {
    queryClient.invalidateQueries({
      queryKey: ["campaigns", currentCompanyId, "detail", campaignIdNum],
    });
    queryClient.invalidateQueries({
      queryKey: ["campaigns", currentCompanyId],
    });
  };

  // Safe Sanitized HTML
  const sanitizedHtml = useMemo(() => {
    if (!campaign?.body_html) return null;
    return DOMPurify.sanitize(campaign.body_html, {
      ADD_TAGS: ["style"],
      ADD_ATTR: ["target"],
    });
  }, [campaign?.body_html]);

  // Detected Merge Tags in content
  const detectedMergeTags = useMemo(() => {
    const content = `${campaign?.subject || ""} ${campaign?.body_html || ""} ${campaign?.body_text || ""}`;
    const matches = content.match(/\{\{([a-zA-Z0-9_-]+)\}\}/g);
    if (!matches) return [];
    return Array.from(new Set(matches));
  }, [campaign?.subject, campaign?.body_html, campaign?.body_text]);

  const handleCopySubject = () => {
    if (!campaign?.subject) return;
    navigator.clipboard.writeText(campaign.subject).then(() => {
      setCopiedSubject(true);
      setTimeout(() => setCopiedSubject(false), 2000);
      showToast("Subject line copied to clipboard.");
    }).catch(() => {
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
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to dispatch campaign.";
      showToast(msg, "error");
    },
  });

  const scheduleMutation = useMutation({
    mutationFn: (scheduledAtIso: string) => {
      if (!currentCompanyId || !campaignIdNum) throw new Error("Missing parameters");
      return campaignsApi.scheduleCampaign(currentCompanyId, campaignIdNum, {
        scheduled_at: scheduledAtIso,
      });
    },
    onSuccess: (updated) => {
      invalidateQueries();
      setActionModalState((prev) => ({ ...prev, isOpen: false }));
      showToast(`Campaign scheduled for ${formatDate(updated.scheduled_at)}.`);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to schedule campaign.";
      showToast(msg, "error");
    },
  });

  // Lifecycle Mutations
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
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to pause campaign.";
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
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to resume campaign.";
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
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to cancel campaign.";
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
        err instanceof RequestError
          ? String(err.detail || err.message)
          : "Failed to delete campaign.";
      showToast(msg, "error");
    },
  });

  const handleOpenCancelModal = () => {
    if (!campaign) return;
    setModalState({ isOpen: true, campaign, mode: "cancel" });
  };

  const handleOpenDeleteModal = () => {
    if (!campaign) return;
    setModalState({ isOpen: true, campaign, mode: "delete" });
  };

  const handleConfirmModal = () => {
    if (modalState.mode === "cancel") {
      cancelMutation.mutate();
    } else {
      deleteMutation.mutate();
    }
  };

  // 1. Loading Skeleton State
  if (isLoading) {
    return (
      <div className="w-full max-w-7xl mx-auto min-w-0 px-4 sm:px-6 lg:px-8 py-6 space-y-6 box-border animate-pulse">
        <div className="flex items-center justify-between">
          <div className="h-4 bg-slate-200 rounded w-48"></div>
          <div className="h-8 bg-slate-200 rounded w-24"></div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
          <div className="h-8 bg-slate-200 rounded w-72"></div>
          <div className="h-4 bg-slate-200 rounded w-96"></div>
          <div className="flex gap-2 pt-2">
            <div className="h-9 bg-slate-200 rounded w-36"></div>
            <div className="h-9 bg-slate-200 rounded w-28"></div>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <div className="h-32 bg-white rounded-xl border border-slate-200 p-4"></div>
          <div className="h-32 bg-white rounded-xl border border-slate-200 p-4"></div>
          <div className="h-32 bg-white rounded-xl border border-slate-200 p-4"></div>
        </div>
        <div className="h-72 bg-white rounded-xl border border-slate-200 p-6"></div>
      </div>
    );
  }

  // 2. Error / Not Found State
  if (isError || !campaign) {
    const isNotFound =
      error instanceof RequestError ? error.status === 404 : false;

    return (
      <div className="w-full max-w-7xl mx-auto min-w-0 px-4 sm:px-6 lg:px-8 py-12 box-border">
        <div className="bg-white rounded-xl border border-slate-200 p-8 sm:p-12 text-center max-w-lg mx-auto shadow-sm space-y-4">
          <div className="w-14 h-14 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto">
            {isNotFound ? (
              <AlertTriangle className="h-7 w-7" />
            ) : (
              <AlertCircle className="h-7 w-7" />
            )}
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
  const senderEmail =
    campaign.email_account_address || `Account #${campaign.email_account_id}`;
  const senderDomain = senderEmail.includes("@") ? senderEmail.split("@")[1] : "—";
  const isDraft = campaign.status === "DRAFT";

  return (
    <div className="w-full max-w-7xl mx-auto min-w-0 px-4 sm:px-6 lg:px-8 py-6 space-y-6 box-border">
      {/* 1. Header Navigation & Utilities */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-1">
        <div className="flex items-center gap-2 min-w-0">
          <Link
            to="/campaigns"
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 hover:text-slate-900 font-medium text-xs sm:text-sm transition-colors shrink-0"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Back to Campaigns</span>
          </Link>
          <span className="text-slate-300">/</span>
          <nav className="flex items-center gap-1 text-xs sm:text-sm text-slate-500 truncate">
            <span className="text-slate-500">PulseMail</span>
            <span className="text-slate-300">/</span>
            <Link to="/campaigns" className="hover:text-indigo-600 transition-colors">
              Campaigns
            </Link>
            <span className="text-slate-300">/</span>
            <span className="text-slate-900 font-semibold truncate max-w-[200px] sm:max-w-md">
              {campaign.name}
            </span>
          </nav>
        </div>

        <div className="flex items-center gap-2 shrink-0 self-end sm:self-auto">
          <button
            type="button"
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 text-xs font-medium border border-slate-200/80 shadow-2xs transition-all disabled:opacity-50"
          >
            <RefreshCw
              className={`h-3.5 w-3.5 text-indigo-600 ${
                isFetching ? "animate-spin" : ""
              }`}
            />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </div>

      {/* 2. Spacious Campaign Header Card */}
      <section className="w-full bg-white rounded-xl p-5 md:p-6 lg:p-7 border border-slate-200/80 shadow-2xs min-w-0 space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-4 min-w-0">
          {/* Left: Title, Badges, Subject, Metadata */}
          <div className="space-y-3 max-w-3xl min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl sm:text-2xl lg:text-3xl font-bold text-slate-900 tracking-tight break-words">
                {campaign.name}
              </h1>
              <CampaignStatusBadge status={campaign.status} />
              <span className="px-2.5 py-0.5 rounded-full bg-indigo-50 text-indigo-700 font-semibold text-xs border border-indigo-100">
                {campaign.recipient_count.toLocaleString()} recipients
              </span>
            </div>

            {/* Subject Line Preview Strip with Copy Action */}
            <div className="flex items-center gap-2 p-2.5 rounded-lg bg-slate-50 border border-slate-200/60 max-w-2xl min-w-0">
              <Mail className="h-4 w-4 text-indigo-600 shrink-0" />
              <div className="min-w-0 flex-1 flex items-baseline gap-1.5">
                <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider shrink-0">
                  Subject:
                </span>
                <span className="font-medium text-slate-900 text-sm truncate block sm:inline">
                  "{campaign.subject || "No subject set"}"
                </span>
              </div>
              <button
                type="button"
                onClick={handleCopySubject}
                className="shrink-0 p-1 rounded hover:bg-slate-200/70 text-slate-500 hover:text-slate-800 transition-colors flex items-center gap-1"
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

            {/* Metadata Chips Row */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500 pt-0.5">
              <span>Created {formatDate(campaign.created_at)}</span>
              <span className="text-slate-300">•</span>
              <span>Last modified {formatDate(campaign.updated_at)}</span>
              <span className="text-slate-300">•</span>
              <span className="font-mono text-slate-700 font-medium">ID: #{campaign.id}</span>
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

          {/* Right Action Group: Non-cramped, generous padding & clear hierarchy */}
          <div className="flex flex-wrap items-center gap-2.5 shrink-0 pt-2 lg:pt-0">
            {/* DRAFT specific: Edit Draft, Schedule, Launch */}
            {isDraft && isAdminOrOwner && (
              <>
                <Link
                  to={`/campaigns/${campaign.id}/edit`}
                  className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200/80 font-semibold text-xs sm:text-sm shadow-2xs transition-colors"
                >
                  <FileEdit className="h-4 w-4 text-indigo-600" />
                  <span>Edit Draft</span>
                </Link>
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("schedule")}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200/80 font-semibold text-xs sm:text-sm shadow-2xs transition-colors"
                >
                  <Calendar className="h-4 w-4 text-slate-500" />
                  <span>Schedule</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("launch")}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white hover:bg-slate-50 text-indigo-600 border border-indigo-200 font-semibold text-xs sm:text-sm shadow-2xs transition-colors"
                >
                  <Send className="h-4 w-4 text-indigo-600" />
                  <span>Launch Now</span>
                </button>
              </>
            )}

            {/* RUNNING specific */}
            {campaign.status === "RUNNING" && isAdminOrOwner && (
              <>
                <button
                  type="button"
                  onClick={() => pauseMutation.mutate()}
                  disabled={pauseMutation.isPending}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-amber-50 border border-amber-200 hover:bg-amber-100 text-amber-700 text-xs sm:text-sm font-semibold transition-colors shadow-2xs disabled:opacity-50"
                >
                  <PauseCircle className="h-4 w-4" />
                  <span>Pause</span>
                </button>
                <button
                  type="button"
                  onClick={handleOpenCancelModal}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-rose-200 hover:bg-rose-50 text-rose-600 text-xs sm:text-sm font-semibold transition-colors shadow-2xs"
                >
                  <XCircle className="h-4 w-4" />
                  <span>Cancel</span>
                </button>
              </>
            )}

            {/* PAUSED specific */}
            {campaign.status === "PAUSED" && isAdminOrOwner && (
              <>
                <button
                  type="button"
                  onClick={() => resumeMutation.mutate()}
                  disabled={resumeMutation.isPending}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 text-indigo-700 text-xs sm:text-sm font-semibold transition-colors shadow-2xs disabled:opacity-50"
                >
                  <PlayCircle className="h-4 w-4" />
                  <span>Resume</span>
                </button>
                <button
                  type="button"
                  onClick={handleOpenCancelModal}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-rose-200 hover:bg-rose-50 text-rose-600 text-xs sm:text-sm font-semibold transition-colors shadow-2xs"
                >
                  <XCircle className="h-4 w-4" />
                  <span>Cancel</span>
                </button>
              </>
            )}

            {/* SCHEDULED specific: Reschedule, Launch Now & Cancel */}
            {campaign.status === "SCHEDULED" && isAdminOrOwner && (
              <>
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("schedule")}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white hover:bg-slate-50 text-slate-700 border border-slate-200/80 font-semibold text-xs sm:text-sm shadow-2xs transition-colors"
                >
                  <Calendar className="h-4 w-4 text-slate-500" />
                  <span>Reschedule</span>
                </button>
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("launch")}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white hover:bg-slate-50 text-indigo-600 border border-indigo-200 font-semibold text-xs sm:text-sm shadow-2xs transition-colors"
                >
                  <Send className="h-4 w-4 text-indigo-600" />
                  <span>Launch Now</span>
                </button>
                <button
                  type="button"
                  onClick={handleOpenCancelModal}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-rose-200 hover:bg-rose-50 text-rose-600 text-xs sm:text-sm font-semibold transition-colors shadow-2xs"
                >
                  <XCircle className="h-4 w-4" />
                  <span>Cancel</span>
                </button>
              </>
            )}

            {/* QUEUED specific: Cancel only */}
            {campaign.status === "QUEUED" && isAdminOrOwner && (
              <button
                type="button"
                onClick={handleOpenCancelModal}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-rose-200 hover:bg-rose-50 text-rose-600 text-xs sm:text-sm font-semibold transition-colors shadow-2xs"
              >
                <XCircle className="h-4 w-4" />
                <span>Cancel</span>
              </button>
            )}

            {/* Delete Campaign Action (DRAFT, COMPLETED, CANCELLED, FAILED) */}
            {["DRAFT", "COMPLETED", "CANCELLED", "FAILED"].includes(campaign.status) &&
              isAdminOrOwner && (
                <button
                  type="button"
                  onClick={handleOpenDeleteModal}
                  className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-rose-200 hover:bg-rose-50 text-rose-600 text-xs sm:text-sm font-semibold transition-colors shadow-2xs"
                >
                  <Trash2 className="h-4 w-4" />
                  <span>Delete</span>
                </button>
              )}

            {/* Primary Manage Recipients Button */}
            <Link
              to={`/campaigns/${campaign.id}/recipients`}
              className="inline-flex items-center gap-2 px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs sm:text-sm shadow-2xs hover:shadow transition-all"
            >
              <Users className="h-4 w-4" />
              <span>Manage Recipients</span>
            </Link>
          </div>
        </div>
      </section>

      {/* 3. Three-Column Balanced Information Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 min-w-0">
        {/* Card 1: Sender Identity */}
        <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-2xs flex flex-col justify-between space-y-4 min-w-0">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                  <Send className="h-4 w-4" />
                </div>
                <h2 className="text-sm font-bold text-slate-900">Sender Identity</h2>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[11px] font-semibold">
                Active
              </span>
            </div>

            <div className="mt-3 space-y-2">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                  Display Sender
                </p>
                <p className="text-base font-semibold text-slate-900 truncate mt-0.5" title={senderName}>
                  {senderName}
                </p>
                <p
                  className="font-mono text-xs text-slate-600 bg-slate-50 px-2.5 py-1 rounded-md mt-1 truncate border border-slate-100"
                  title={senderEmail}
                >
                  {senderEmail}
                </p>
              </div>

              <div className="pt-2 space-y-1.5 text-xs">
                <div className="flex items-center justify-between text-slate-500">
                  <span>Domain</span>
                  <span className="font-medium text-slate-900">{senderDomain}</span>
                </div>
                <div className="flex items-center justify-between text-slate-500">
                  <span>Account ID</span>
                  <span className="font-mono text-slate-700">#{campaign.email_account_id}</span>
                </div>
              </div>
            </div>
          </div>

          <div className="pt-2 border-t border-slate-100">
            {isAdminOrOwner ? (
              <Link
                to="/email-accounts"
                className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 hover:underline"
              >
                <span>View Sender Accounts</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            ) : (
              <span className="text-xs text-slate-400">Account verified</span>
            )}
          </div>
        </div>

        {/* Card 2: Schedule & Timing */}
        <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-2xs flex flex-col justify-between space-y-4 min-w-0">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                  <Clock className="h-4 w-4" />
                </div>
                <h2 className="text-sm font-bold text-slate-900">Schedule &amp; Timing</h2>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-semibold">
                {campaign.scheduled_at ? "Scheduled" : isDraft ? "On-Demand" : campaign.status}
              </span>
            </div>

            <div className="mt-3 space-y-2">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                  Dispatch Policy
                </p>
                <p className="text-base font-semibold text-slate-900 mt-0.5">
                  {campaign.scheduled_at
                    ? "Scheduled Dispatch"
                    : isDraft
                    ? "Manual Dispatch"
                    : `Lifecycle: ${campaign.status}`}
                </p>
                <p className="text-xs text-slate-500 mt-0.5">
                  {campaign.scheduled_at
                    ? `Launch time set for ${formatDate(campaign.scheduled_at)}.`
                    : isDraft
                    ? "Requires final review before queue ingestion."
                    : `Campaign currently in ${campaign.status} phase.`}
                </p>
              </div>

              <div className="pt-2 space-y-1.5 text-xs">
                <div className="flex items-center justify-between text-slate-500">
                  <span>Sending Interval</span>
                  <span className="text-slate-800 font-medium">
                    {formatSendInterval(campaign.send_interval_seconds)}
                  </span>
                </div>
                {campaign.next_send_at &&
                  (campaign.status === "RUNNING" || campaign.status === "QUEUED") && (
                    <div className="flex items-center justify-between text-slate-500">
                      <span>Next Recipient</span>
                      <span
                        className="text-indigo-600 font-semibold"
                        title="Estimated next recipient send; actual timing may vary with provider latency"
                      >
                        ~{formatDate(campaign.next_send_at)}
                      </span>
                    </div>
                  )}
                <div className="flex items-center justify-between text-slate-500">
                  <span>Created</span>
                  <span className="text-slate-800 font-medium">{formatDate(campaign.created_at)}</span>
                </div>
                {campaign.scheduled_at && (
                  <div className="flex items-center justify-between text-slate-500">
                    <span>Scheduled</span>
                    <span className="text-amber-700 font-semibold">{formatDate(campaign.scheduled_at)}</span>
                  </div>
                )}
                {campaign.started_at && (
                  <div className="flex items-center justify-between text-slate-500">
                    <span>Started</span>
                    <span className="text-slate-800 font-medium">{formatDate(campaign.started_at)}</span>
                  </div>
                )}
                {campaign.completed_at && (
                  <div className="flex items-center justify-between text-slate-500">
                    <span>Completed</span>
                    <span className="text-emerald-700 font-semibold">{formatDate(campaign.completed_at)}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="pt-2 border-t border-slate-100">
            {isDraft && isAdminOrOwner ? (
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("schedule")}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 hover:underline"
                >
                  <Calendar className="h-3.5 w-3.5" />
                  <span>Schedule Execution</span>
                </button>
                <span className="text-slate-300">•</span>
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("launch")}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 hover:underline"
                >
                  <Send className="h-3.5 w-3.5" />
                  <span>Launch Now</span>
                </button>
              </div>
            ) : campaign.status === "SCHEDULED" && isAdminOrOwner ? (
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("schedule")}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 hover:underline"
                >
                  <Calendar className="h-3.5 w-3.5" />
                  <span>Reschedule</span>
                </button>
                <span className="text-slate-300">•</span>
                <button
                  type="button"
                  onClick={() => handleOpenActionModal("launch")}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 hover:underline"
                >
                  <Send className="h-3.5 w-3.5" />
                  <span>Launch Now</span>
                </button>
              </div>
            ) : (
              <span className="text-xs text-slate-400">Timeline locked to lifecycle</span>
            )}
          </div>
        </div>

        {/* Card 3: Target Audience */}
        <div className="bg-white rounded-xl p-5 border border-slate-200/80 shadow-2xs flex flex-col justify-between space-y-4 min-w-0">
          <div>
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0">
                  <Users className="h-4 w-4" />
                </div>
                <h2 className="text-sm font-bold text-slate-900">Target Audience</h2>
              </div>
              <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-[11px] font-semibold">
                Verified
              </span>
            </div>

            <div className="mt-3 space-y-2">
              <div>
                <p className="text-[11px] uppercase tracking-wider text-slate-500 font-semibold">
                  Total Target List
                </p>
                <p className="text-3xl font-bold text-slate-900 tracking-tight leading-none mt-1">
                  {campaign.recipient_count.toLocaleString()}
                </p>
                <p className="text-xs text-slate-500 mt-1">
                  Audience records attached to this campaign
                </p>
              </div>

              <div className="pt-2 space-y-1.5 text-xs text-slate-500">
                <div className="flex items-center justify-between">
                  <span>Scope</span>
                  <span className="font-medium text-slate-800">Company Isolated</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Recipients Status</span>
                  <span className="font-semibold text-indigo-600">
                    {campaign.recipient_count > 0 ? "Audience Configured" : "Empty Audience"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div className="pt-2 border-t border-slate-100">
            <Link
              to={`/campaigns/${campaign.id}/recipients`}
              className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-700 hover:underline"
            >
              <span>View All {campaign.recipient_count.toLocaleString()} Recipients</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
      </div>

      {/* 4. Campaign Message Preview Section */}
      <div className="w-full bg-white rounded-xl p-5 md:p-6 lg:p-7 border border-slate-200/80 shadow-2xs space-y-5 min-w-0">
        {/* Content View Mode Toolbar */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div>
            <h2 className="text-base sm:text-lg font-bold text-slate-900">Campaign Message Preview</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Rendered with high-fidelity sanitization and merge variable detection.
            </p>
          </div>

          {/* Mode Segmented Controls & Device Switchers */}
          <div className="flex flex-wrap items-center gap-2">
            {/* View Format Segmented Controls */}
            <div className="inline-flex p-1 rounded-lg bg-slate-100 text-slate-600 border border-slate-200/70 text-xs font-medium">
              <button
                type="button"
                onClick={() => setContentMode("preview")}
                className={`px-3 py-1 rounded-md transition-all flex items-center gap-1.5 ${
                  contentMode === "preview"
                    ? "bg-white text-slate-900 font-semibold shadow-2xs"
                    : "hover:text-slate-900"
                }`}
              >
                <Eye className="h-3.5 w-3.5" />
                <span>Formatted Preview</span>
              </button>
              <button
                type="button"
                onClick={() => setContentMode("html")}
                className={`px-3 py-1 rounded-md transition-all flex items-center gap-1.5 ${
                  contentMode === "html"
                    ? "bg-white text-slate-900 font-semibold shadow-2xs"
                    : "hover:text-slate-900"
                }`}
              >
                <Code className="h-3.5 w-3.5" />
                <span>HTML Source</span>
              </button>
              <button
                type="button"
                onClick={() => setContentMode("plaintext")}
                className={`px-3 py-1 rounded-md transition-all flex items-center gap-1.5 ${
                  contentMode === "plaintext"
                    ? "bg-white text-slate-900 font-semibold shadow-2xs"
                    : "hover:text-slate-900"
                }`}
              >
                <FileText className="h-3.5 w-3.5" />
                <span>Plaintext Fallback</span>
              </button>
            </div>

            {/* Device Switcher */}
            <div className="inline-flex p-1 rounded-lg bg-slate-100 text-slate-600 border border-slate-200/70">
              <button
                type="button"
                onClick={() => setDeviceView("desktop")}
                className={`p-1.5 rounded-md transition-all ${
                  deviceView === "desktop"
                    ? "bg-white text-slate-900 shadow-2xs"
                    : "hover:text-slate-900"
                }`}
                title="Desktop Viewport"
              >
                <Monitor className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setDeviceView("mobile")}
                className={`p-1.5 rounded-md transition-all ${
                  deviceView === "mobile"
                    ? "bg-white text-slate-900 shadow-2xs"
                    : "hover:text-slate-900"
                }`}
                title="Mobile Viewport"
              >
                <Smartphone className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Preview Frame Container */}
        <div className="w-full flex justify-center min-w-0">
          <div
            className={`w-full transition-all duration-300 rounded-xl bg-slate-50/70 p-3 sm:p-5 border border-slate-200/80 space-y-4 min-w-0 ${
              deviceView === "mobile" ? "max-w-sm" : "max-w-4xl"
            }`}
          >
            {/* Mock Client Envelope Header */}
            <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/70 shadow-2xs space-y-3 min-w-0">
              <div className="grid grid-cols-1 gap-2 text-xs text-slate-800">
                <div className="flex items-center gap-2">
                  <span className="w-16 text-slate-400 font-semibold uppercase">From:</span>
                  <span className="font-semibold text-slate-900 truncate">{senderName}</span>
                  <span className="font-mono text-slate-500 truncate">&lt;{senderEmail}&gt;</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-16 text-slate-400 font-semibold uppercase">To:</span>
                  <span className="px-1.5 py-0.5 rounded bg-indigo-50 text-indigo-700 font-mono text-[11px] font-semibold border border-indigo-100">
                    {`{{first_name}}`}
                  </span>
                  <span className="font-mono text-slate-500 truncate">&lt;recipient@target.com&gt;</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-16 text-slate-400 font-semibold uppercase">Subject:</span>
                  <span className="font-semibold text-slate-900 truncate">
                    {campaign.subject || "(No subject set)"}
                  </span>
                </div>
              </div>

              {/* Merge Tag Info Strip */}
              <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-100 bg-slate-50/60 px-3 py-2 rounded-lg">
                <div className="flex flex-wrap items-center gap-1.5">
                  <Code className="h-3.5 w-3.5 text-indigo-600" />
                  <span className="text-xs font-semibold text-slate-700">Merge Variables Detected:</span>
                  {detectedMergeTags.length > 0 ? (
                    detectedMergeTags.map((tag) => (
                      <span
                        key={tag}
                        className="font-mono text-[11px] bg-white px-2 py-0.5 rounded text-indigo-600 font-semibold border border-indigo-100"
                      >
                        {tag}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-slate-400 italic">None detected</span>
                  )}
                </div>
                <span className="text-xs text-slate-400">Default fallback: 'Colleague'</span>
              </div>
            </div>

            {/* Active View 1: Formatted Preview */}
            {contentMode === "preview" && (
              <div className="bg-white rounded-xl p-5 md:p-6 border border-slate-200/70 shadow-2xs min-w-0">
                {sanitizedHtml ? (
                  <div
                    className="prose prose-sm max-w-none text-slate-800 leading-relaxed overflow-x-auto min-w-0 break-words"
                    dangerouslySetInnerHTML={{ __html: sanitizedHtml }}
                  />
                ) : campaign.body_text ? (
                  <pre className="font-mono text-xs text-slate-800 whitespace-pre-wrap leading-relaxed overflow-x-auto min-w-0 break-words">
                    {campaign.body_text}
                  </pre>
                ) : (
                  <p className="text-xs text-slate-400 italic text-center py-8">
                    No message body configured for this campaign.
                  </p>
                )}
              </div>
            )}

            {/* Active View 2: HTML Source */}
            {contentMode === "html" && (
              <div className="bg-slate-900 text-slate-100 rounded-xl p-4 sm:p-5 shadow-2xs font-mono text-xs overflow-x-auto min-w-0">
                <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800 text-[11px] text-slate-400 uppercase font-semibold">
                  <span>template_source.html</span>
                  <span>UTF-8 • Safe Escaped View</span>
                </div>
                <pre className="overflow-x-auto leading-5 text-slate-200 whitespace-pre-wrap break-words">
                  <code>{campaign.body_html || "<!-- No HTML content configured -->"}</code>
                </pre>
              </div>
            )}

            {/* Active View 3: Plaintext Fallback */}
            {contentMode === "plaintext" && (
              <div className="bg-white rounded-xl p-4 sm:p-5 border border-slate-200/70 shadow-2xs font-mono text-xs overflow-x-auto min-w-0 space-y-2">
                <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-100 text-[11px] text-slate-400 uppercase font-semibold">
                  <span>plaintext_fallback.txt</span>
                  <span>Whitespace Preserved</span>
                </div>
                <pre className="text-slate-800 whitespace-pre-wrap leading-6 break-words">
                  {campaign.body_text || "(No plaintext body configured)"}
                </pre>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 5. Recipient Quick Access Callout Strip */}
      <div className="w-full bg-white rounded-xl p-4 md:p-5 border border-slate-200/80 shadow-2xs flex flex-col sm:flex-row sm:items-center justify-between gap-4 min-w-0">
        <div className="flex items-center gap-3.5 min-w-0">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center shrink-0 shadow-2xs">
            <CheckCircle2 className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-bold text-slate-900 truncate">
              Audience Target Records
            </p>
            <p className="text-xs text-slate-500 truncate mt-0.5">
              {campaign.recipient_count.toLocaleString()} target records configured for this dispatch scope.
            </p>
          </div>
        </div>

        <Link
          to={`/campaigns/${campaign.id}/recipients`}
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-xs sm:text-sm shadow-2xs transition-colors shrink-0"
        >
          <span>Inspect Recipient Table</span>
          <span>→</span>
        </Link>
      </div>

      {/* Confirmation Modal for Cancel / Delete */}
      <CancelCampaignModal
        isOpen={modalState.isOpen}
        campaign={modalState.campaign}
        mode={modalState.mode}
        onClose={() => setModalState({ isOpen: false, campaign: null, mode: "cancel" })}
        onConfirm={handleConfirmModal}
        isLoading={cancelMutation.isPending || deleteMutation.isPending}
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
